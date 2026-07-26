"use client";

import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Clock3,
  FileUp,
  Folder,
  Layers3,
  LoaderCircle,
  MessageCircle,
  Mic2,
  RefreshCw,
  Sparkles,
  Target,
  UploadCloud,
  X,
} from "lucide-react";
import {
  ChangeEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { VoiceSession } from "./VoiceSession";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

type MasteryState = "unassessed" | "learning" | "practicing" | "fluent";

export interface Card {
  card_id: string;
  simplified: string;
  traditional?: string;
  pinyin: string;
  categories?: string[];
  mastery_state?: MasteryState;
  comprehension?: number;
  independent_usage?: number;
}

interface CategoryNode {
  name: string;
  path: string;
  card_count: number;
  children: CategoryNode[];
}

interface Deck {
  deck_id: string;
  name: string;
  card_count: number;
  category_tree: CategoryNode[];
  cards: Card[];
  mastery_summary?: Partial<Record<MasteryState, number>>;
  updated_at?: string;
}

interface SessionPlan {
  session_id: string;
  target_cards: Card[];
  topic_suggestions: string[];
  category_paths?: string[];
}

interface ConnectionDetails {
  server_url: string;
  token: string;
  room_name: string;
  session_id: string;
}

const stateLabels: Record<MasteryState, string> = {
  unassessed: "Unassessed",
  learning: "Learning",
  practicing: "Practicing",
  fluent: "Fluent",
};

function createLearnerId() {
  if (typeof window === "undefined") return "";
  const existing = window.localStorage.getItem("plecoach-learner-id");
  if (existing) return existing;
  const value = window.crypto?.randomUUID?.() ?? `learner-${Date.now()}`;
  window.localStorage.setItem("plecoach-learner-id", value);
  return value;
}

function normalizeCategory(node: Record<string, unknown>): CategoryNode {
  const children = Array.isArray(node.children)
    ? node.children.map((child) =>
        normalizeCategory(child as Record<string, unknown>),
      )
    : [];
  return {
    name: String(node.name ?? node.label ?? node.path ?? "Untitled"),
    path: String(node.path ?? node.name ?? ""),
    card_count: Number(node.card_count ?? node.count ?? 0),
    children,
  };
}

function normalizeCard(raw: Record<string, unknown>): Card {
  const nestedMastery =
    typeof raw.mastery === "object" && raw.mastery
      ? (raw.mastery as Record<string, unknown>)
      : {};
  const mastery = (raw.mastery_state ??
    nestedMastery.state ??
    raw.state ??
    "unassessed") as MasteryState;
  return {
    card_id: String(raw.card_id ?? raw.id ?? raw.pleco_id ?? ""),
    simplified: String(
      raw.simplified ?? raw.headword_simplified ?? raw.headword ?? "",
    ),
    traditional: raw.traditional
      ? String(raw.traditional)
      : raw.headword_traditional
        ? String(raw.headword_traditional)
        : undefined,
    pinyin: String(raw.pinyin ?? raw.pronunciation ?? ""),
    categories: Array.isArray(raw.categories)
      ? raw.categories.map(String)
      : undefined,
    mastery_state: Object.hasOwn(stateLabels, mastery)
      ? mastery
      : "unassessed",
    comprehension:
      typeof raw.comprehension === "number"
        ? raw.comprehension
        : typeof nestedMastery.comprehension_score === "number"
          ? nestedMastery.comprehension_score
          : undefined,
    independent_usage:
      typeof raw.independent_usage === "number"
        ? raw.independent_usage
        : typeof nestedMastery.usage_score === "number"
          ? nestedMastery.usage_score
        : undefined,
  };
}

function normalizeDeck(payload: Record<string, unknown>): Deck {
  const rawCards = Array.isArray(payload.cards) ? payload.cards : [];
  const rawTree = Array.isArray(payload.category_tree)
    ? payload.category_tree
    : Array.isArray(payload.categories)
      ? payload.categories
      : [];
  return {
    deck_id: String(payload.deck_id ?? payload.id ?? "current"),
    name: String(payload.name ?? payload.filename ?? "Pleco deck"),
    card_count: Number(payload.card_count ?? rawCards.length),
    category_tree: rawTree.map((item) =>
      normalizeCategory(item as Record<string, unknown>),
    ),
    cards: rawCards.map((item) =>
      normalizeCard(item as Record<string, unknown>),
    ),
    mastery_summary:
      typeof payload.mastery_summary === "object" && payload.mastery_summary
        ? (payload.mastery_summary as Deck["mastery_summary"])
        : undefined,
    updated_at: payload.updated_at ? String(payload.updated_at) : undefined,
  };
}

function normalizePlan(payload: Record<string, unknown>): SessionPlan {
  const rawCards = Array.isArray(payload.target_cards)
    ? payload.target_cards
    : Array.isArray(payload.cards)
      ? payload.cards
      : [];
  const topics = Array.isArray(payload.topic_suggestions)
    ? payload.topic_suggestions.map(String)
    : ["聊聊今天的生活", "一起计划一次旅行", "随便聊聊"];
  return {
    session_id: String(payload.session_id ?? payload.id ?? ""),
    target_cards: rawCards.map((item) =>
      normalizeCard(item as Record<string, unknown>),
    ),
    topic_suggestions: topics,
    category_paths: Array.isArray(payload.category_paths)
      ? payload.category_paths.map(String)
      : undefined,
  };
}

async function readJson(response: Response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof payload.detail === "string"
        ? payload.detail
        : "Something went wrong. Please try again.";
    throw new Error(detail);
  }
  return payload as Record<string, unknown>;
}

function Brand() {
  return (
    <div className="brand-lockup" aria-label="Plecoach home">
      <span className="brand-mark" aria-hidden="true">
        说
      </span>
      <span className="brand-word">
        Plecoach
        <small>Mandarin, made active</small>
      </span>
    </div>
  );
}

function CategoryBranch({
  node,
  selected,
  onToggle,
  depth = 0,
}: {
  node: CategoryNode;
  selected: Set<string>;
  onToggle: (path: string) => void;
  depth?: number;
}) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = node.children.length > 0;
  const checked = selected.has(node.path);
  return (
    <div className="category-branch">
      <div
        className={`category-row ${checked ? "is-selected" : ""}`}
        style={{ paddingLeft: `${10 + depth * 18}px` }}
      >
        <button
          type="button"
          className="tree-toggle"
          onClick={() => setOpen((value) => !value)}
          aria-label={`${open ? "Collapse" : "Expand"} ${node.name}`}
          disabled={!hasChildren}
        >
          {hasChildren ? (
            open ? (
              <ChevronDown size={14} />
            ) : (
              <ChevronRight size={14} />
            )
          ) : (
            <span className="tree-dot" />
          )}
        </button>
        <button
          type="button"
          className="category-select"
          onClick={() => onToggle(node.path)}
          aria-pressed={checked}
        >
          <span className="category-check">
            {checked ? <Check size={12} strokeWidth={3} /> : null}
          </span>
          <span className="category-name">{node.name}</span>
          <span className="category-count">{node.card_count}</span>
        </button>
      </div>
      {open && hasChildren ? (
        <div>
          {node.children.map((child) => (
            <CategoryBranch
              key={child.path}
              node={child}
              selected={selected}
              onToggle={onToggle}
              depth={depth + 1}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function WordChip({ card, compact = false }: { card: Card; compact?: boolean }) {
  return (
    <div className={`word-chip ${compact ? "is-compact" : ""}`}>
      <span className="word-hanzi">{card.simplified}</span>
      <span className="word-pinyin">{card.pinyin}</span>
    </div>
  );
}

function ImportPanel({
  onFile,
  onSample,
  busy,
  error,
}: {
  onFile: (file: File) => void;
  onSample: () => void;
  busy: boolean;
  error: string | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) onFile(file);
    event.target.value = "";
  };

  return (
    <section className="import-card" aria-labelledby="import-heading">
      <div className="import-icon">
        <UploadCloud size={25} />
      </div>
      <div>
        <p className="eyebrow">Start with words you already care about</p>
        <h2 id="import-heading">Bring your Pleco deck</h2>
        <p className="muted">
          Upload a Pleco XML export. Your folders and review history stay
          organized.
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".xml,text/xml,application/xml"
        className="sr-only"
        onChange={handleChange}
        aria-label="Choose a Pleco XML export"
      />
      <button
        className="primary-button full-button"
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
      >
        {busy ? (
          <LoaderCircle className="spin" size={18} />
        ) : (
          <FileUp size={18} />
        )}
        {busy ? "Importing deck…" : "Upload Pleco XML"}
      </button>
      <button
        type="button"
        className="text-button"
        onClick={onSample}
        disabled={busy}
      >
        Or try the sample deck <ArrowRight size={15} />
      </button>
      {error ? (
        <p className="inline-error" role="alert">
          <CircleAlert size={16} /> {error}
        </p>
      ) : null}
      <div className="privacy-note">
        <Check size={14} />
        Stored in your Redis-backed Plecoach workspace
      </div>
    </section>
  );
}

function EmptyExperience({
  onFile,
  onSample,
  busy,
  error,
}: {
  onFile: (file: File) => void;
  onSample: () => void;
  busy: boolean;
  error: string | null;
}) {
  return (
    <main className="landing-shell">
      <header className="landing-nav">
        <Brand />
        <span className="nav-note">
          <span className="live-dot" /> Powered by LiveKit
        </span>
      </header>
      <section className="hero-grid">
        <div className="hero-copy">
          <p className="eyebrow coral">Your flashcards, finally in context</p>
          <h1>
            把认识的词，
            <br />
            <em>用成自己的话。</em>
          </h1>
          <p className="hero-subtitle">
            Plecoach turns your Pleco vocabulary into a Mandarin conversation
            that meets you at exactly the right level.
          </p>
          <div className="hero-proof">
            <span>
              <MessageCircle size={17} /> Mandarin only
            </span>
            <span>
              <Target size={17} /> Context-aware review
            </span>
            <span>
              <RefreshCw size={17} /> Adapts every session
            </span>
          </div>
          <div className="conversation-preview" aria-hidden="true">
            <div className="avatar tutor-avatar">陪</div>
            <div className="preview-bubble">
              <small>陪练老师</small>
              你到了一个新城市，可是找不到酒店。你会怎么办？
              <span className="preview-target">迷路</span>
            </div>
          </div>
        </div>
        <ImportPanel
          onFile={onFile}
          onSample={onSample}
          busy={busy}
          error={error}
        />
      </section>
      <section className="landing-steps" aria-label="How Plecoach works">
        <article>
          <span>01</span>
          <div>
            <h3>Import your structure</h3>
            <p>Pleco folders, pinyin, and history come with you.</p>
          </div>
        </article>
        <article>
          <span>02</span>
          <div>
            <h3>Choose your focus</h3>
            <p>Target a lesson, folder, or whatever is due.</p>
          </div>
        </article>
        <article>
          <span>03</span>
          <div>
            <h3>Use it out loud</h3>
            <p>The tutor creates a reason to understand and respond.</p>
          </div>
        </article>
      </section>
    </main>
  );
}

function PlanDialog({
  plan,
  chosenTopic,
  onTopic,
  onClose,
  onStart,
  busy,
  error,
}: {
  plan: SessionPlan;
  chosenTopic: string;
  onTopic: (topic: string) => void;
  onClose: () => void;
  onStart: () => void;
  busy: boolean;
  error: string | null;
}) {
  return (
    <div className="dialog-backdrop" role="presentation">
      <section
        className="plan-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="plan-title"
      >
        <button
          type="button"
          className="dialog-close"
          onClick={onClose}
          aria-label="Close session plan"
        >
          <X size={20} />
        </button>
        <div className="dialog-kicker">
          <Sparkles size={16} /> Your conversation is ready
        </div>
        <h2 id="plan-title">Pick a scene to step into</h2>
        <p className="muted">
          The tutor will naturally create opportunities to understand and use
          these words—without turning the conversation into a quiz.
        </p>
        <div className="plan-section">
          <div className="section-heading">
            <span>Conversation topic</span>
            <small>Choose one</small>
          </div>
          <div className="topic-options">
            {plan.topic_suggestions.map((topic, index) => (
              <button
                type="button"
                key={topic}
                className={`topic-option ${
                  chosenTopic === topic ? "is-selected" : ""
                }`}
                onClick={() => onTopic(topic)}
              >
                <span className="topic-number">{index + 1}</span>
                <span>{topic}</span>
                <span className="topic-radio">
                  {chosenTopic === topic ? <Check size={13} /> : null}
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="plan-section">
          <div className="section-heading">
            <span>Words in focus</span>
            <small>{plan.target_cards.length} cards</small>
          </div>
          <div className="word-chip-grid">
            {plan.target_cards.map((card) => (
              <WordChip key={card.card_id || card.simplified} card={card} />
            ))}
          </div>
        </div>
        {error ? (
          <p className="inline-error" role="alert">
            <CircleAlert size={16} /> {error}
          </p>
        ) : null}
        <button
          type="button"
          className="primary-button full-button start-session-button"
          onClick={onStart}
          disabled={busy || !chosenTopic}
        >
          {busy ? <LoaderCircle className="spin" size={18} /> : <Mic2 size={18} />}
          {busy ? "Opening the room…" : "Start speaking"}
        </button>
        <p className="microcopy">Your microphone will turn on when you join.</p>
      </section>
    </div>
  );
}

function DeckDashboard({
  deck,
  selectedPaths,
  onTogglePath,
  onSelectAll,
  onPlan,
  onImport,
  planning,
  error,
}: {
  deck: Deck;
  selectedPaths: Set<string>;
  onTogglePath: (path: string) => void;
  onSelectAll: () => void;
  onPlan: () => void;
  onImport: (file: File) => void;
  planning: boolean;
  error: string | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const summary = useMemo(() => {
    const base = {
      unassessed: 0,
      learning: 0,
      practicing: 0,
      fluent: 0,
    };
    if (deck.mastery_summary) {
      return { ...base, ...deck.mastery_summary };
    }
    deck.cards.forEach((card) => {
      base[card.mastery_state ?? "unassessed"] += 1;
    });
    if (!deck.cards.length) base.unassessed = deck.card_count;
    return base;
  }, [deck]);
  const assessed =
    summary.learning + summary.practicing + summary.fluent;
  const progress = deck.card_count
    ? Math.round((summary.fluent / deck.card_count) * 100)
    : 0;
  const selectedLabel =
    selectedPaths.size === 0
      ? "All folders"
      : selectedPaths.size === 1
        ? "1 selected folder"
        : `${selectedPaths.size} selected folders`;
  const previewCards = deck.cards.slice(0, 8);

  return (
    <main className="app-shell">
      <header className="app-header">
        <Brand />
        <div className="header-actions">
          <span className="connection-pill">
            <span className="live-dot" /> Ready
          </span>
          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            accept=".xml,text/xml,application/xml"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onImport(file);
              event.target.value = "";
            }}
          />
          <button
            type="button"
            className="secondary-button"
            onClick={() => inputRef.current?.click()}
          >
            <FileUp size={16} /> Update deck
          </button>
        </div>
      </header>

      <section className="dashboard-intro">
        <div>
          <p className="eyebrow">欢迎回来 · Welcome back</p>
          <h1>What do you want to make active today?</h1>
          <p>
            Choose a Pleco folder. We’ll find the words that need a real
            conversation—not another flip of a card.
          </p>
        </div>
        <div className="deck-meta-card">
          <div className="deck-meta-icon">
            <BookOpen size={22} />
          </div>
          <div>
            <strong>{deck.name}</strong>
            <span>{deck.card_count.toLocaleString()} cards imported</span>
          </div>
          <div className="deck-progress-ring" style={{ "--progress": progress } as React.CSSProperties}>
            <span>{progress}%</span>
          </div>
        </div>
      </section>

      <section className="dashboard-grid">
        <aside className="folder-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Pleco structure</p>
              <h2>Choose folders</h2>
            </div>
            <Layers3 size={19} />
          </div>
          <button
            type="button"
            className={`all-folders-button ${
              selectedPaths.size === 0 ? "is-selected" : ""
            }`}
            onClick={onSelectAll}
          >
            <span className="folder-icon">
              <Folder size={16} />
            </span>
            <span>
              <strong>All flashcards</strong>
              <small>Everything in this export</small>
            </span>
            <span className="category-count">{deck.card_count}</span>
          </button>
          <div className="category-tree">
            {deck.category_tree.length ? (
              deck.category_tree.map((node) => (
                <CategoryBranch
                  key={node.path}
                  node={node}
                  selected={selectedPaths}
                  onToggle={onTogglePath}
                />
              ))
            ) : (
              <p className="empty-tree">No Pleco folders found in this export.</p>
            )}
          </div>
        </aside>

        <div className="practice-panel">
          <div className="practice-header">
            <div>
              <p className="eyebrow">Today’s practice</p>
              <h2>{selectedLabel}</h2>
            </div>
            <span className="adaptive-badge">
              <Sparkles size={14} /> Adaptive selection
            </span>
          </div>

          <div className="mastery-grid">
            <article>
              <span className="mastery-dot unassessed" />
              <small>Unassessed</small>
              <strong>{summary.unassessed}</strong>
              <p>Ready for a first conversation</p>
            </article>
            <article>
              <span className="mastery-dot learning" />
              <small>Learning</small>
              <strong>{summary.learning}</strong>
              <p>Understood with some support</p>
            </article>
            <article>
              <span className="mastery-dot practicing" />
              <small>Practicing</small>
              <strong>{summary.practicing}</strong>
              <p>Used correctly, building confidence</p>
            </article>
            <article>
              <span className="mastery-dot fluent" />
              <small>Fluent</small>
              <strong>{summary.fluent}</strong>
              <p>Independent across conversations</p>
            </article>
          </div>

          <div className="selection-explainer">
            <div className="selection-icon">
              <Target size={21} />
            </div>
            <div>
              <strong>We’ll choose six cards when you continue</strong>
              <p>
                Unassessed and weak words come first. Pleco statistics are only
                a soft signal; speaking evidence decides fluency.
              </p>
            </div>
          </div>

          {previewCards.length ? (
            <div className="deck-glimpse">
              <div className="section-heading">
                <span>A glimpse of this deck</span>
                <small>{assessed} assessed in Plecoach</small>
              </div>
              <div className="word-chip-grid">
                {previewCards.map((card) => (
                  <WordChip key={card.card_id || card.simplified} card={card} compact />
                ))}
              </div>
            </div>
          ) : null}

          {error ? (
            <p className="inline-error" role="alert">
              <CircleAlert size={16} /> {error}
            </p>
          ) : null}

          <button
            type="button"
            className="primary-button plan-button"
            onClick={onPlan}
            disabled={planning}
          >
            {planning ? (
              <LoaderCircle className="spin" size={18} />
            ) : (
              <MessageCircle size={18} />
            )}
            {planning ? "Planning your session…" : "Plan a conversation"}
            {!planning ? <ArrowRight size={18} /> : null}
          </button>
          <p className="plan-note">
            <Clock3 size={14} /> About 8 minutes · Mandarin only
          </p>
        </div>
      </section>
    </main>
  );
}

export function PlecoachApp() {
  const [learnerId] = useState(createLearnerId);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<SessionPlan | null>(null);
  const [chosenTopic, setChosenTopic] = useState("");
  const [connection, setConnection] = useState<ConnectionDetails | null>(null);

  const loadDeck = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE}/api/decks/${encodeURIComponent(id)}`,
      );
      if (response.status === 404) {
        setDeck(null);
        return;
      }
      const payload = await readJson(response);
      setDeck(normalizeDeck(payload));
    } catch (requestError) {
      setDeck(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The Plecoach service is not available yet.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Loading after mount is required because the learner ID is device-local.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (learnerId) void loadDeck(learnerId);
  }, [learnerId, loadDeck]);

  const importDeck = useCallback(
    async (file: File) => {
      if (!learnerId) return;
      setImporting(true);
      setError(null);
      try {
        const body = new FormData();
        body.append("file", file);
        body.append("learner_id", learnerId);
        const response = await fetch(`${API_BASE}/api/decks/import`, {
          method: "POST",
          body,
        });
        await readJson(response);
        await loadDeck(learnerId);
        setSelectedPaths(new Set());
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "We couldn’t import that Pleco export.",
        );
      } finally {
        setImporting(false);
      }
    },
    [learnerId, loadDeck],
  );

  const importSample = useCallback(async () => {
    setImporting(true);
    setError(null);
    try {
      const response = await fetch("/samples/pleco-demo.xml");
      if (!response.ok) throw new Error("The sample deck could not be loaded.");
      const blob = await response.blob();
      await importDeck(
        new File([blob], "plecoach-sample.xml", { type: "application/xml" }),
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The sample deck could not be loaded.",
      );
      setImporting(false);
    }
  }, [importDeck]);

  const togglePath = (path: string) => {
    setSelectedPaths((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const createPlan = async () => {
    setPlanning(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/sessions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          learner_id: learnerId,
          category_paths: Array.from(selectedPaths),
          target_count: 6,
        }),
      });
      const payload = await readJson(response);
      const nextPlan = normalizePlan(payload);
      setPlan(nextPlan);
      setChosenTopic(nextPlan.topic_suggestions[0] ?? "随便聊聊");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "We couldn’t plan this session.",
      );
    } finally {
      setPlanning(false);
    }
  };

  const startSession = async () => {
    if (!plan) return;
    setConnecting(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE}/api/sessions/${encodeURIComponent(plan.session_id)}/connection`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            participant_identity: learnerId,
            participant_name: "Learner",
            topic: chosenTopic,
          }),
        },
      );
      const payload = await readJson(response);
      setConnection({
        server_url: String(payload.server_url ?? payload.url ?? ""),
        token: String(payload.token ?? payload.participant_token ?? ""),
        room_name: String(payload.room_name ?? ""),
        session_id: String(payload.session_id ?? plan.session_id),
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "We couldn’t open the LiveKit room.",
      );
    } finally {
      setConnecting(false);
    }
  };

  if (loading) {
    return (
      <main className="loading-screen" aria-live="polite">
        <Brand />
        <LoaderCircle className="spin" size={24} />
        <p>正在准备你的词卡…</p>
      </main>
    );
  }

  if (connection && plan) {
    return (
      <VoiceSession
        connection={connection}
        plan={plan}
        topic={chosenTopic}
        apiBase={API_BASE}
        onLeave={() => {
          setConnection(null);
          setPlan(null);
          void loadDeck(learnerId);
        }}
      />
    );
  }

  if (!deck) {
    return (
      <EmptyExperience
        onFile={importDeck}
        onSample={importSample}
        busy={importing}
        error={error}
      />
    );
  }

  return (
    <>
      <DeckDashboard
        deck={deck}
        selectedPaths={selectedPaths}
        onTogglePath={togglePath}
        onSelectAll={() => setSelectedPaths(new Set())}
        onPlan={createPlan}
        onImport={importDeck}
        planning={planning || importing}
        error={error}
      />
      {plan ? (
        <PlanDialog
          plan={plan}
          chosenTopic={chosenTopic}
          onTopic={setChosenTopic}
          onClose={() => {
            setPlan(null);
            setError(null);
          }}
          onStart={startSession}
          busy={connecting}
          error={error}
        />
      ) : null}
    </>
  );
}
