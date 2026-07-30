# Plecoach

Plecoach turns a Pleco flashcard export into a real-time Mandarin conversation tutor. Instead of asking the learner to translate isolated cards, the tutor creates a natural conversation that surfaces selected vocabulary, notices whether the learner understands it, and looks for independent, contextually correct use.

The tutor speaks only Mandarin. When the learner is stuck, it stays in Mandarin and lowers the difficulty with simpler wording, an example, or a hint.

## Quick start

You need:

- Docker with Docker Compose
- A LiveKit Cloud project with Inference enabled
- A browser with microphone access

Create the root environment file:

```bash
cp .env.example .env
```

Add the three credentials from your LiveKit project:

```dotenv
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
```

Build and start the complete stack:

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). Upload a Pleco v2 XML export, or click **Try the sample deck** to load the same synthetic fixture available at [`samples/pleco-demo.xml`](samples/pleco-demo.xml). Select a category branch, review the target words, allow microphone access, and start speaking.

All required configuration is documented in [`.env.example`](.env.example). No provider key beyond the LiveKit project credentials is required for the default LiveKit Inference pipeline.

## What to try

The sample deck contains 24 synthetic cards under a preserved hierarchy:

```text
Plecoach Demo
├── 校园生活
│   ├── 课堂
│   └── 课后
├── 周末计划
│   ├── 餐厅
│   └── 公园
└── 重点复习
    └── 本周
```

Choose a leaf for a focused conversation or a parent branch for a wider one. Cards assigned to more than one category are included only once. The fabricated Pleco histories range from new to well reviewed, making the scheduling behavior visible without including anyone's personal data.

## Architecture

```text
┌──────────────────┐             ┌───────────────────┐
│ Browser frontend │──HTTP──────▶│ API / session svc │
│ upload + session │             │ XML, deck, tokens │
└────────┬─────────┘             └─────────┬─────────┘
         │ WebRTC                            │
         ▼                                   ▼
┌──────────────────┐              ┌───────────────────┐
│  LiveKit Cloud   │              │       Redis       │
│ rooms + media    │              │ deck + sessions   │
└────────┬─────────┘              │ transcript + skill│
         │                        └─────────▲─────────┘
         ▼                                  │
┌───────────────────────────────────────────┴─────────┐
│ LiveKit agent                                      │
│ Nova-3 STT → Gemma 4 31B tutor → Sonic-3 TTS      │
│ conversation orchestration + fluency observations  │
└─────────────────────────────────────────────────────┘
```

Docker Compose runs the web frontend, HTTP API, LiveKit agent worker, and Redis as separate services. LiveKit Cloud carries low-latency audio, room state, and agent participation; Redis is the backing state store shared by the stateless API and agent.

The boundaries are intentional:

- **Session management** imports decks, resolves category selection, chooses targets, and issues short-lived room access.
- **Conversation handling** owns transcript events, hints, target exposure, and fluency observations.
- **Voice/AI** is isolated behind the LiveKit agent and configurable model IDs.
- **State** is accessed through a small Redis repository layer rather than being embedded in route or prompt code.

## Learning model

Pleco's score, difficulty, correct/incorrect counts, and review history are imported as a **soft scheduling signal only**. A high flashcard score may make a word less urgent, but it never proves conversational fluency.

Planning history is stored separately from mastery. Recently proposed focus words receive a bounded cooldown so consecutive plans rotate through equally eligible cards; previewing or closing a plan never counts as learning evidence, and genuinely due weak words can still recur.

At session planning time, Plecoach also builds a conservative language profile from **every card in the selected folder**, not just the six difficult words chosen for assessment. Preserved HSK category assignments are de-duplicated per card and combined with a lower-median estimate so a few advanced words cannot raise the whole conversation. The target words may be challenging; surrounding vocabulary and grammar are kept one HSK band easier. Missing labels default to simple everyday Mandarin and adapt from the learner's actual responses rather than assuming advanced proficiency.

Plecoach starts conversational mastery as unassessed and gathers two kinds of evidence:

1. **Comprehension:** Did the learner respond in a way that shows they understood the word in context?
2. **Usage:** Did the learner use the word correctly and independently?

An answer after a hint can show progress, but it is weaker evidence than independent use. Later conversations can revise an earlier assessment. The learner sees an encouraging qualitative state rather than a brittle numeric score.

## Key decisions and tradeoffs

### A cascaded LiveKit pipeline

The default voice path is streaming Mandarin STT with Deepgram Nova-3, tutoring with Google Gemma 4 31B IT, and streaming Mandarin TTS with Cartesia Sonic-3, all through LiveKit Inference. Sonic-3 uses Cartesia's **Chinese Female Conversational** preset rather than a multilingual American voice, so the tutor speaks with native Mandarin cadence while retaining low-latency streaming and aligned transcripts.

A native speech-to-speech model could reduce latency and sound more expressive. The cascade was chosen because it produces an explicit transcript, which is useful evidence for vocabulary assessment, is visible to the learner, and makes incorrect judgments debuggable. The cost is an extra inference boundary and sensitivity to transcription errors.

The agent also uses LiveKit's multilingual turn detector, interruption handling, TTS-aligned transcripts, explicit room dispatch, and reliable data messages for assessment updates. Deepgram keyterms are populated from the six session words to improve recognition of the vocabulary that matters most.

### Conversation, not disguised flashcards

The tutor receives a small target set plus a language profile derived from the full selected folder. That profile gives Gemma concrete ceilings for sentences, Hanzi per sentence, clauses, grammar, and question count, plus a bounded set of easier deck words to prefer. Beginner profiles also slow the supported Cartesia voice and allow a longer pause before LiveKit decides the learner has finished speaking. After signs of confusion, the tutor immediately switches to very short concrete Mandarin and a simple either/or question; it only adds complexity after two clear, independent responses. The deterministic opening follows the same profile.

The tutor is asked to surface words naturally rather than march through a quiz. This is more engaging and tests transferable knowledge, but it makes coverage less deterministic. Numeric prompt limits are a strong behavioral constraint rather than a formal guarantee from the generative model, so they are backed by deterministic profile tests and should eventually be monitored against recorded tutor turns.

The planning screen shows an English gloss for each Mandarin topic and the exported Pleco definition beside each target word. This makes session setup legible without weakening the immersion rule: once the learner joins, every tutor utterance and explanation remains in Mandarin.

### Preserve Pleco structure

Category paths are preserved on import. Selecting a parent includes all descendants, and multiple selected branches form a deduplicated union. This respects the organization learners already invested in and lets a single deck drive very different conversations. It adds more import and selection logic than flattening every card into one list.

### Reassess rather than inherit mastery

Pleco statistics help order the first sessions, but Plecoach maintains its own evidence. Recognition in a flashcard test and spontaneous use in speech are different skills. The downside is that an experienced learner initially sees many cards as unassessed.

### Redis as the source of runtime state

Decks, category indexes, session targets, transcript/assessment events, and mastery records live in Redis. This directly satisfies the assignment and lets API and agent containers remain replaceable. For a larger long-lived product, Redis alone is not the ideal system of record; durable learner history would move to a relational database while Redis remained the hot session/cache layer.

### Scope kept intentionally narrow

This is a single-learner demo with no account system. Pronunciation and tone scoring are deferred: the current definition of fluency is semantic understanding plus correct contextual use. Both choices keep the take-home centered on a working LiveKit conversation and a defensible learning loop.

## Import behavior and privacy

- The importer accepts Pleco v2 XML and reads simplified/traditional headwords, numbered pinyin, exported `<defn>` text, category assignments, and optional score metadata.
- Pleco only writes usable definition text when **Card definitions** is enabled for custom cards and **Dictionary definitions** is enabled for dictionary-linked cards on the export screen. Without those options, an export may contain only device-specific `<dictref>` references; Plecoach can still import the words, but it has less context for disambiguating meanings.
- Category paths are derived from the slash-delimited Pleco assignment and retained as a tree.
- XML is validated and bounded before persistence; malformed or empty decks return a useful error.
- Re-importing merges cards by simplified headword plus pinyin, preserves Plecoach mastery, updates current Pleco metadata, and marks cards missing from the new file inactive instead of deleting them.
- The repository contains only a hand-authored synthetic fixture. Personal exports and root `.env` files should never be committed.

## Redis state

Redis stores four conceptual record groups:

- **Deck:** import metadata, normalized cards, and the category tree.
- **Learner mastery:** per-card comprehension/usage evidence and scheduling fields.
- **Session:** selected categories, the immutable language profile, deduplicated targets, room identity, status, and timestamps.
- **Conversation:** up to 200 ordered transcript turns plus assessment evidence inside the session record.

The current implementation uses `plecoach:learner:{learner_id}:deck` for the active deck and `plecoach:session:{session_id}` for a planned or active conversation. Session records expire after seven days by default; `SESSION_TTL_SECONDS` can change that. This makes API and agent workers horizontally replaceable without losing an active conversation.

## HTTP API

FastAPI exposes interactive documentation at [http://localhost:8000/docs](http://localhost:8000/docs) and these product endpoints:

- `GET /api/health`
- `POST /api/decks/import` with multipart `file` and `learner_id`
- `GET /api/decks/{learner_id}`
- `POST /api/sessions`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/connection`

The final endpoint returns a short-lived participant token and explicitly dispatches the configured `plecoach-tutor` agent to the session's LiveKit room.

## Scaling to 10,000 concurrent sessions

The first bottleneck would be voice inference and one active agent process per room, not XML parsing. I would:

- Run API and agent workers as separate autoscaled deployments; scale agents from LiveKit dispatch queue depth, active jobs, CPU, and memory.
- Use LiveKit Cloud's regional routing and place agent pools plus Redis close to the media region to reduce round trips.
- Move durable decks and mastery events to Postgres, keep Redis Cluster for active-session state, presence, rate limits, and hot target sets.
- Partition Redis keys by learner/session and avoid global scans; use bounded streams and TTLs for transcript/session data.
- Make assessment updates idempotent and append-only, then process mastery aggregation asynchronously so a slow write never blocks speech.
- Pre-warm agent workers, cap concurrent jobs per worker, and apply admission control/backpressure when inference capacity is saturated.
- Store full transcripts in cheaper object storage after a session and retain only summaries/evidence indexes in the transactional store.
- Add per-stage latency, turn-end, interruption, token, STT-confidence, and assessment metrics. Load-test room joins separately from paid model inference.

The current service boundaries already allow that evolution; the take-home intentionally uses one Redis instance and local Compose replicas.

## Development and verification

The deterministic checks should run without LiveKit credentials:

```bash
# Backend tests
docker compose run --rm api pytest

# Frontend checks
docker compose run --rm web npm test
```

For the evaluator path, build the images, start the stack, confirm service health, import the sample XML, and then run a short microphone conversation with valid LiveKit credentials.

See [workflow.md](workflow.md) for the AI-assisted development process and [PROMPT.md](PROMPT.md) for the original assignment.

## Video walkthrough

Before sharing the repository, record a short walkthrough that shows:

- `docker compose up --build` reaching a usable web app
- the one-click sample deck import
- a nested category selection and its six planned target words
- the browser joining a LiveKit room and the tutor speaking Mandarin
- one interrupted turn, the live transcript, and an updated word state

Add the final video link to the submission message or immediately below this checklist.
