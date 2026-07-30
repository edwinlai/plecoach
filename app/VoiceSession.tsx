"use client";

import {
  BarVisualizer,
  DisconnectButton,
  LiveKitRoom,
  RoomAudioRenderer,
  VoiceAssistantControlBar,
  useDataChannel,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import {
  ArrowLeft,
  Check,
  CircleAlert,
  MessageCircle,
  Mic2,
  Sparkles,
  Target,
} from "lucide-react";
import type { DisconnectReason } from "livekit-client";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Card } from "./PlecoachApp";
import {
  mergeLearnerSpokenTargetIds,
  normalizeFocusWordCard,
  type FocusWordCard,
} from "./focus-word-progress";
import { groupTranscriptTurns } from "./transcript-turns";
import { resolveRoomDisconnection } from "./voice-session-lifecycle";

interface ConnectionDetails {
  server_url: string;
  token: string;
  room_name: string;
  session_id: string;
}

interface SessionPlan {
  session_id: string;
  target_cards: Card[];
  topic_suggestions: string[];
}

const statusCopy: Record<string, { zh: string; en: string }> = {
  disconnected: { zh: "准备中", en: "Preparing" },
  connecting: { zh: "正在连接", en: "Connecting" },
  initializing: { zh: "老师马上来", en: "Tutor is joining" },
  listening: { zh: "我在听", en: "Listening" },
  thinking: { zh: "我想一想", en: "Thinking" },
  speaking: { zh: "轮到我说", en: "Speaking" },
};

const HAN_TRANSCRIPT = /\p{Script=Han}/u;
type TranscriptPinyinConverter = (text: string) => string;

function TranscriptPinyin({
  text,
  converter,
}: {
  text: string;
  converter: TranscriptPinyinConverter | null;
}) {
  const value = useMemo(() => converter?.(text) ?? "", [converter, text]);

  if (!HAN_TRANSCRIPT.test(text)) return null;

  return (
    <p className="transcript-pinyin" lang="zh-Latn-pinyin" aria-hidden="true">
      {value || "\u00a0"}
    </p>
  );
}

function LiveConversation({
  plan,
  topic,
  apiBase,
  onLeave,
}: {
  plan: SessionPlan;
  topic: string;
  apiBase: string;
  onLeave: () => void;
}) {
  const { state, audioTrack, agent } = useVoiceAssistant();
  const transcriptions = useTranscriptions();
  const transcriptTurns = useMemo(
    () => groupTranscriptTurns(transcriptions),
    [transcriptions],
  );
  const [cards, setCards] = useState<FocusWordCard[]>(() =>
    plan.target_cards.map(normalizeFocusWordCard),
  );
  const targetCardIds = useMemo(
    () =>
      new Set(
        plan.target_cards.map((card) => card.card_id).filter(Boolean),
      ),
    [plan.target_cards],
  );
  const [learnerSpokenTargetIds, setLearnerSpokenTargetIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [pinyinConverter, setPinyinConverter] =
    useState<TranscriptPinyinConverter | null>(null);
  const transcriptList = useRef<HTMLDivElement>(null);
  const followTranscript = useRef(true);
  const status = statusCopy[state] ?? statusCopy.connecting;
  const liveLabel =
    state === "disconnected"
      ? "Offline"
      : state === "connecting" || state === "initializing"
        ? "Connecting"
        : "Live";
  const handleProgress = useCallback(
    (message: { payload: Uint8Array }) => {
      try {
        const payload = JSON.parse(
          new TextDecoder().decode(message.payload),
        ) as {
          type?: string;
          card_id?: string;
          card_ids?: unknown;
          comprehension?: number | null;
          independent_usage?: number | null;
          mastery?: {
            state?: Card["mastery_state"];
            comprehension_score?: number | null;
            usage_score?: number | null;
          };
        };
        if (payload.type === "learner_spoken_targets") {
          setLearnerSpokenTargetIds((current) =>
            mergeLearnerSpokenTargetIds(
              current,
              payload.card_ids,
              targetCardIds,
            ),
          );
          return;
        }
        if (payload.type !== "card_assessment" || !payload.card_id) return;
        setCards((current) =>
          current.map((card) =>
            card.card_id === payload.card_id
              ? normalizeFocusWordCard({
                  ...card,
                  mastery_state:
                    payload.mastery?.state ?? card.mastery_state,
                  comprehension:
                    payload.mastery?.comprehension_score ??
                    payload.comprehension ??
                    card.comprehension,
                  independent_usage:
                    payload.mastery?.usage_score ??
                    payload.independent_usage ??
                    card.independent_usage,
                })
              : card,
          ),
        );
      } catch {
        // Ignore malformed packets; Redis polling remains the fallback.
      }
    },
    [targetCardIds],
  );
  useDataChannel("plecoach.card-assessment", handleProgress);

  useEffect(() => {
    let cancelled = false;
    void import("./transcript-pinyin")
      .then(({ toTranscriptPinyin }) => {
        if (!cancelled) {
          setPinyinConverter(() => toTranscriptPinyin);
        }
      })
      .catch(() => {
        // Hanzi remains usable if the optional pinyin chunk cannot be loaded.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const stickTranscriptToBottom = useCallback(() => {
    if (!followTranscript.current) return;
    const element = transcriptList.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, []);

  useLayoutEffect(() => {
    stickTranscriptToBottom();
  }, [pinyinConverter, stickTranscriptToBottom, transcriptTurns]);

  const handleTranscriptScroll = useCallback(() => {
    const element = transcriptList.current;
    if (!element) return;
    followTranscript.current =
      element.scrollHeight - element.scrollTop - element.clientHeight < 80;
  }, []);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const response = await fetch(
          `${apiBase}/api/sessions/${encodeURIComponent(plan.session_id)}`,
        );
        if (!response.ok) return;
        const payload = (await response.json()) as {
          target_cards?: Array<FocusWordCard | Record<string, unknown>>;
          cards?: Array<FocusWordCard | Record<string, unknown>>;
          learner_spoken_target_card_ids?: unknown;
        };
        const nextCards = payload.target_cards ?? payload.cards;
        if (cancelled) return;
        if (Array.isArray(nextCards)) {
          setCards(nextCards.map(normalizeFocusWordCard));
        }
        setLearnerSpokenTargetIds((current) =>
          mergeLearnerSpokenTargetIds(
            current,
            payload.learner_spoken_target_card_ids,
            targetCardIds,
          ),
        );
      } catch {
        // Voice should remain usable if progress refresh briefly fails.
      }
    };
    const timer = window.setInterval(refresh, 5000);
    void refresh();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [apiBase, plan.session_id, targetCardIds]);

  const completedCount = useMemo(
    () =>
      cards.filter((card) => learnerSpokenTargetIds.has(card.card_id)).length,
    [cards, learnerSpokenTargetIds],
  );

  return (
    <div className="voice-shell">
      <header className="voice-header">
        <div className="voice-brand">
          <span className="brand-mark small-mark">说</span>
          <span>
            Plecoach
            <small>Live Mandarin session</small>
          </span>
        </div>
        <div className="voice-topic">
          <MessageCircle size={15} />
          <span>{topic}</span>
        </div>
        <DisconnectButton className="end-session-button" onClick={onLeave}>
          <ArrowLeft size={16} /> End session
        </DisconnectButton>
      </header>

      <div className="voice-grid">
        <main className="transcript-panel">
          <div className="session-panel-heading">
            <div>
              <p className="eyebrow">Live transcript</p>
              <h1>对话记录</h1>
            </div>
            <span className="transcript-live">
              <span className="live-dot" aria-hidden="true" /> {liveLabel}
            </span>
          </div>
          <div
            className="transcript-list"
            role="log"
            aria-live="polite"
            aria-relevant="additions text"
            ref={transcriptList}
            onScroll={handleTranscriptScroll}
          >
            {transcriptTurns.length ? (
              transcriptTurns.map((turn) => {
                const isTutor = turn.participantIdentity === agent?.identity;
                return (
                  <article
                    key={turn.id}
                    className={isTutor ? "tutor-line" : "learner-line"}
                  >
                    <span aria-hidden="true">{isTutor ? "陪" : "你"}</span>
                    <div>
                      <small>{isTutor ? "陪练老师" : "你"}</small>
                      <p className="transcript-hanzi" lang="zh-CN">
                        {turn.text}
                      </p>
                      <TranscriptPinyin
                        text={turn.text}
                        converter={pinyinConverter}
                      />
                    </div>
                  </article>
                );
              })
            ) : (
              <div className="empty-transcript">
                <MessageCircle size={22} />
                <p>对话开始后，文字会出现在这里。</p>
              </div>
            )}
          </div>
          <div className="voice-dock">
            <div className="voice-status">
              <span className="status-pulse" />
              <span>
                <strong>{status.zh}</strong>
                <small>{status.en}</small>
              </span>
            </div>
            <div className="voice-signal">
              <BarVisualizer
                className="voice-visualizer"
                state={state}
                trackRef={audioTrack}
                barCount={7}
                options={{ minHeight: 8, maxHeight: 48 }}
              />
              {!agent && state !== "disconnected" ? (
                <p className="joining-note">
                  正在邀请你的陪练老师加入房间…
                </p>
              ) : (
                <p className="mic-note">
                  <Mic2 size={14} /> 可以随时打断老师，就像真实的对话一样
                </p>
              )}
            </div>
            <VoiceAssistantControlBar
              className="voice-controls"
              controls={{ microphone: true, leave: false }}
            />
          </div>
        </main>

        <aside className="session-words">
          <div className="session-panel-heading">
            <div>
              <p className="eyebrow">Words in focus</p>
              <h2>今日词汇</h2>
            </div>
            <span>
              {completedCount}/{cards.length}
            </span>
          </div>
          <div className="session-progress">
            <span
              style={{
                width: `${cards.length ? (completedCount / cards.length) * 100 : 0}%`,
              }}
            />
          </div>
          <div className="session-word-list">
            {cards.map((card) => {
              const active = learnerSpokenTargetIds.has(card.card_id);
              const pinyin = card.pinyin || "拼音未提供";
              const detailLabel = card.definition
                ? `拼音：${pinyin}。词义：${card.definition}`
                : `拼音：${pinyin}。词义未提供`;
              return (
                <article
                  key={card.card_id || card.simplified}
                  className={active ? "is-evidenced" : ""}
                >
                  <span className="session-word-state">
                    {active ? <Check size={13} strokeWidth={3} /> : null}
                  </span>
                  <div className="session-word-copy">
                    <strong>{card.simplified}</strong>
                    <span className="session-word-meta" aria-label={detailLabel}>
                      <span className="session-word-pinyin">{pinyin}</span>
                      {card.definition ? (
                        <>
                          <span
                            className="session-word-separator"
                            aria-hidden="true"
                          >
                            ·
                          </span>
                          <span
                            className="session-word-definition"
                            title={card.definition}
                          >
                            {card.definition}
                          </span>
                        </>
                      ) : null}
                    </span>
                  </div>
                  <span className="evidence-label">
                    {active ? "已说到" : "待练习"}
                  </span>
                </article>
              );
            })}
          </div>
          <div className="session-tip">
            <Sparkles size={16} />
            <p>
              不用刻意说出每个词。自然地回答老师的问题就好。
            </p>
          </div>
          <div className="assessment-note">
            <Target size={16} />
            <p>
              说到的词会在这里标记；理解和使用是否正确会另外更新熟练度。
            </p>
          </div>
        </aside>
      </div>
      <RoomAudioRenderer />
    </div>
  );
}

export function VoiceSession({
  connection,
  plan,
  topic,
  apiBase,
  onReconnect,
  onLeave,
}: {
  connection: ConnectionDetails;
  plan: SessionPlan;
  topic: string;
  apiBase: string;
  onReconnect: () => Promise<void>;
  onLeave: () => void;
}) {
  const [roomError, setRoomError] = useState<string | null>(null);
  const [roomAttempt, setRoomAttempt] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const connectedRef = useRef(false);
  const leaveRequestedRef = useRef(false);
  const leaveCommittedRef = useRef(false);
  const lastErrorRef = useRef<string | null>(null);

  const commitLeave = useCallback(() => {
    if (leaveCommittedRef.current) return;
    leaveCommittedRef.current = true;
    onLeave();
  }, [onLeave]);

  const requestLeave = useCallback(() => {
    leaveRequestedRef.current = true;
    commitLeave();
  }, [commitLeave]);

  const retryConnection = useCallback(async () => {
    setRetrying(true);
    try {
      await onReconnect();
      connectedRef.current = false;
      leaveRequestedRef.current = false;
      leaveCommittedRef.current = false;
      lastErrorRef.current = null;
      setRoomError(null);
      setRoomAttempt((attempt) => attempt + 1);
    } catch (error) {
      const message =
        error instanceof Error && error.message.trim()
          ? error.message
          : "Plecoach couldn’t request a fresh voice-room connection.";
      lastErrorRef.current = message;
      setRoomError(message);
    } finally {
      setRetrying(false);
    }
  }, [onReconnect]);

  const handleConnected = useCallback(() => {
    connectedRef.current = true;
    lastErrorRef.current = null;
    setRoomError(null);
  }, []);

  const handleError = useCallback((error: Error) => {
    const message =
      error.message.trim() ||
      "Plecoach encountered an error while opening the voice room.";
    lastErrorRef.current = message;
    setRoomError(message);
  }, []);

  const handleDisconnected = useCallback(
    (reason?: DisconnectReason) => {
      const disposition = resolveRoomDisconnection({
        userRequested: leaveRequestedRef.current,
        wasConnected: connectedRef.current,
        reason,
        priorError: lastErrorRef.current,
      });
      if (disposition.shouldExit) {
        commitLeave();
        return;
      }
      lastErrorRef.current = disposition.error;
      setRoomError(disposition.error);
    },
    [commitLeave],
  );

  return (
    <LiveKitRoom
      key={`${connection.session_id}-${roomAttempt}`}
      token={connection.token}
      serverUrl={connection.server_url}
      connect
      audio
      video={false}
      onConnected={handleConnected}
      onDisconnected={handleDisconnected}
      onError={handleError}
      data-lk-theme="default"
      className="livekit-root"
    >
      {roomError ? (
        <div
          className="room-error"
          role="alert"
          aria-live="assertive"
          aria-atomic="true"
        >
          <CircleAlert size={18} />
          <span>{roomError}</span>
          <span className="room-error-actions">
            <button
              type="button"
              onClick={() => void retryConnection()}
              disabled={retrying}
            >
              {retrying ? "Reconnecting…" : "Try again"}
            </button>
            <button type="button" onClick={requestLeave} disabled={retrying}>
              Return to deck
            </button>
          </span>
        </div>
      ) : null}
      <LiveConversation
        plan={plan}
        topic={topic}
        apiBase={apiBase}
        onLeave={requestLeave}
      />
    </LiveKitRoom>
  );
}
