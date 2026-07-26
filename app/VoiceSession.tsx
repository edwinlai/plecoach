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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Card } from "./PlecoachApp";

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
  const [cards, setCards] = useState(plan.target_cards);
  const transcriptEnd = useRef<HTMLDivElement>(null);
  const status = statusCopy[state] ?? statusCopy.connecting;
  const handleAssessment = useCallback((message: { payload: Uint8Array }) => {
    try {
      const payload = JSON.parse(new TextDecoder().decode(message.payload)) as {
        type?: string;
        card_id?: string;
        comprehension?: number | null;
        independent_usage?: number | null;
        mastery?: { state?: Card["mastery_state"] };
      };
      if (payload.type !== "card_assessment" || !payload.card_id) return;
      setCards((current) =>
        current.map((card) =>
          card.card_id === payload.card_id
            ? {
                ...card,
                mastery_state: payload.mastery?.state ?? card.mastery_state,
                comprehension:
                  payload.comprehension ?? card.comprehension,
                independent_usage:
                  payload.independent_usage ?? card.independent_usage,
              }
            : card,
        ),
      );
    } catch {
      // Ignore unrelated or malformed packets; Redis polling remains the fallback.
    }
  }, []);
  useDataChannel("plecoach.card-assessment", handleAssessment);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [transcriptions]);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const response = await fetch(
          `${apiBase}/api/sessions/${encodeURIComponent(plan.session_id)}`,
        );
        if (!response.ok) return;
        const payload = (await response.json()) as {
          target_cards?: Card[];
          cards?: Card[];
        };
        const nextCards = payload.target_cards ?? payload.cards;
        if (!cancelled && Array.isArray(nextCards)) setCards(nextCards);
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
  }, [apiBase, plan.session_id]);

  const completedCount = useMemo(
    () =>
      cards.filter(
        (card) =>
          card.mastery_state === "practicing" ||
          card.mastery_state === "fluent" ||
          (card.comprehension ?? 0) > 0.55 ||
          (card.independent_usage ?? 0) > 0.55,
      ).length,
    [cards],
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
              const active =
                card.mastery_state === "practicing" ||
                card.mastery_state === "fluent" ||
                (card.comprehension ?? 0) > 0.55 ||
                (card.independent_usage ?? 0) > 0.55;
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
                    {active ? "已出现" : "待练习"}
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
        </aside>

        <main className="voice-stage">
          <div className={`tutor-orb state-${state}`}>
            <span className="orb-character">陪</span>
            <div className="orb-ring ring-one" />
            <div className="orb-ring ring-two" />
          </div>
          <div className="voice-status">
            <span className="status-pulse" />
            <strong>{status.zh}</strong>
            <small>{status.en}</small>
          </div>
          <BarVisualizer
            className="voice-visualizer"
            state={state}
            trackRef={audioTrack}
            barCount={7}
            options={{ minHeight: 12, maxHeight: 84 }}
          />
          {!agent && state !== "disconnected" ? (
            <p className="joining-note">正在邀请你的陪练老师加入房间…</p>
          ) : null}
          <VoiceAssistantControlBar
            className="voice-controls"
            controls={{ microphone: true, leave: false }}
          />
          <p className="mic-note">
            <Mic2 size={14} /> 可以随时打断老师，就像真实的对话一样
          </p>
        </main>

        <aside className="transcript-panel">
          <div className="session-panel-heading">
            <div>
              <p className="eyebrow">Live transcript</p>
              <h2>对话记录</h2>
            </div>
            <span className="transcript-live">
              <span className="live-dot" /> Live
            </span>
          </div>
          <div className="transcript-list" aria-live="polite">
            {transcriptions.length ? (
              transcriptions.map((item, index) => {
                const isTutor = item.participantInfo.identity === agent?.identity;
                return (
                  <article
                    key={`${item.participantInfo.identity}-${index}-${item.text}`}
                    className={isTutor ? "tutor-line" : "learner-line"}
                  >
                    <span>{isTutor ? "陪" : "你"}</span>
                    <div>
                      <small>{isTutor ? "陪练老师" : "你"}</small>
                      <p>{item.text}</p>
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
            <div ref={transcriptEnd} />
          </div>
          <div className="assessment-note">
            <Target size={16} />
            <p>
              Plecoach 会根据你是否理解并独立使用词汇来更新熟练度。
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
  onLeave,
}: {
  connection: ConnectionDetails;
  plan: SessionPlan;
  topic: string;
  apiBase: string;
  onLeave: () => void;
}) {
  const [roomError, setRoomError] = useState<string | null>(null);
  return (
    <LiveKitRoom
      token={connection.token}
      serverUrl={connection.server_url}
      connect
      audio
      video={false}
      onDisconnected={onLeave}
      onError={(error) => setRoomError(error.message)}
      data-lk-theme="default"
      className="livekit-root"
    >
      {roomError ? (
        <div className="room-error" role="alert">
          <CircleAlert size={18} />
          <span>{roomError}</span>
          <DisconnectButton onClick={onLeave}>Return to deck</DisconnectButton>
        </div>
      ) : null}
      <LiveConversation
        plan={plan}
        topic={topic}
        apiBase={apiBase}
        onLeave={onLeave}
      />
    </LiveKitRoom>
  );
}
