# Workflow

This project was built as a time-boxed take-home with AI used as an engineering accelerator, not as a substitute for product and technical judgment.

## Tools and models

- **OpenAI Codex desktop, GPT-5** was my primary coding harness. I used it to inspect the starter repository, turn the brief into a scoped implementation plan, edit code, run checks, and review failures.
- **Codex subagents, also GPT-5**, worked in parallel on bounded areas: the HTTP API and Pleco parser, the LiveKit voice agent, and submission documentation/sample data. Keeping ownership explicit let the work proceed concurrently without multiple agents editing the same files.
- **LiveKit Inference** supplies the runtime voice models:
  - Deepgram Nova-3 for streaming Mandarin speech-to-text.
  - Google Gemma 4 31B IT for tutoring and assessment.
  - Cartesia Sonic-3 with its Chinese Female Conversational preset for native Mandarin streaming text-to-speech.
- **Official documentation and targeted browser research** were used for volatile or provider-specific facts: current LiveKit model identifiers, Mandarin support, agent dispatch, turn handling, and token generation. I avoided relying on model memory for current SDK behavior.
- **Local command-line checks and Docker Compose** form the verification harness. Tests cover rule-based application logic; container checks verify the evaluator's actual startup path.

The only AI-generated visual is the social preview card (`public/og.png`), produced with Codex's built-in image-generation tool from the finished interface's typography, palette, and product copy, then checked for text accuracy. No user-supplied vocabulary or metadata is bundled. The included Pleco deck is synthetic.

The final image-generation prompt was:

> Use case: ads-marketing. Asset type: wide social preview card for a Mandarin learning web app, optimized for Slack, X, iMessage, and link unfurls. Primary request: create a polished editorial product card for Plecoach, an AI Mandarin voice tutor that turns Pleco flashcards into real conversation. Scene/backdrop: warm textured ivory paper with subtle jade-green concentric sound-wave rings and one coral-red speech-bubble accent; no device mockup and no screenshot collage. Subject: a confident minimal brand composition centered on a rounded jade conversation orb containing the single Chinese character “陪”, with a small coral speech marker containing “说”; a few tasteful flashcard chips reading “迷路 mílù”, “地图 dìtú”, and “计划 jìhuà”. Style/medium: premium flat editorial design, tactile paper texture, modern language-learning brand, restrained and sophisticated rather than playful cartoon. Composition/framing: landscape 1.91:1, strong hierarchy, generous negative space, all essential content inside safe margins. Lighting/mood: warm, encouraging, focused, human. Color palette: ivory #F7F3EB, ink #1E2A27, jade #176B5B, coral #E85E4F, pale jade #DCEBE5. Text (verbatim): “Plecoach” and “把认识的词，用成自己的话。”. Typography: bold contemporary sans serif for Plecoach; beautifully typeset simplified Chinese with exact punctuation; all text must be perfectly spelled and legible. Constraints: cohesive single social card, use only the exact specified words and characters, no logos from other companies, no English subtitle, no watermark, no gradients that reduce text legibility. Avoid: generic AI imagery, robots, brains, flags, maps, photos, phone frames, 3D mascots, clutter, extra text, incorrect Chinese characters.

## How I used AI

### 1. Resolve the product before writing code

I first used Codex as a product-thinking partner to remove ambiguity from the brief. The resulting constraints were:

- Web rather than native iOS, because the evaluator must be able to launch the whole submission with Docker Compose.
- Mandarin-only tutoring, with simpler Mandarin hints when needed.
- Fluency means demonstrated comprehension and correct contextual use. Pronunciation scoring is explicitly deferred.
- Existing Pleco statistics are only a scheduling prior. Plecoach reassesses conversational fluency from scratch.
- Pleco category paths must remain intact so a learner can target a branch of the imported deck.

This prevented the implementation from drifting into a generic voice chatbot.

### 2. Choose the voice architecture deliberately

I compared native speech-to-speech models with a cascaded LiveKit pipeline. I selected:

```text
Mandarin audio → Nova-3 STT → Gemma tutor → Sonic-3 TTS
```

A realtime speech-to-speech model could feel more natural, but the cascade produces an explicit transcript. That transcript is important evidence for deciding whether a learner understood and used a target word correctly, makes session state auditable, and is easier to debug in a short assignment. The model identifiers remain configuration rather than being embedded in product logic.

### 3. Inspect the real input shape safely

I inspected the element and attribute structure of the provided Pleco v2 XML export locally: headwords, numbered pinyin, category assignments, and score history. I did not copy its vocabulary or metadata into the repository. Instead, I created `samples/pleco-demo.xml` from scratch with 24 ordinary words, nested synthetic categories, and fabricated review histories.

### 4. Parallelize along architectural boundaries

I gave each subagent a narrow contract:

- API/parser: validation, category-tree construction, Redis persistence, and LiveKit access tokens.
- Voice agent: Mandarin prompt, LiveKit model pipeline, target-word assessment, and persistence hooks.
- Submission package: exact prompt, README, workflow disclosure, and synthetic sample data.
- Main thread: frontend integration, lesson-planning orchestration, Docker wiring, cross-component review, and final verification.

Agents shared the same workspace, so I used file ownership and short coordination messages to avoid conflicting edits. I reviewed the integrated result rather than accepting subagent output blindly.

### 5. Refine the backend boundary after integration

The integrated architecture review exposed one avoidable coupling: `Store.create_session` both decided what the lesson should contain and persisted it. I extracted that orchestration into `SessionPlanner`, injected it into the FastAPI application, and gave it a three-operation `SessionPlanningStore` protocol. Planning still happens entirely on the backend, but its decisions are now independently testable and no longer depend on FastAPI, Redis, LiveKit, or an LLM.

The refactor intentionally kept the HTTP contract and Redis key schema stable. `Store` remains responsible for data access and state mutations; `SessionPlanner` normalizes category selection, coordinates target rotation and language-profile rules, constructs the planned session, and asks the store to commit planning history plus the session together. A per-learner planner lock prevents same-process requests from racing, and `RedisStore` uses one transaction for the two keys. Planner behavior lives in `test_session_planner.py`, while the broader import → plan → assessment → re-import path remains an integration test.

### 6. Verify in layers

The intended verification order is:

1. Parse the synthetic XML and assert its card count, category hierarchy, and varied optional score histories.
2. Run backend tests for validation, deduplication, the planner/store boundary, category normalization, target rotation, language profiling, and mastery updates.
3. Run frontend static checks and a production build.
4. Validate the resolved Compose configuration.
5. Build and start the same Compose services described in the README.
6. Exercise health endpoints and the sample-deck flow.
7. With LiveKit credentials present, complete one manual microphone session and confirm interruption, transcript delivery, and Redis-backed assessment updates.

The final submission should report only checks that actually ran successfully; provider-backed voice verification is kept distinct from deterministic local tests.

## Review guardrails

- All secrets come from the root `.env`; only names and safe defaults appear in `.env.example`.
- Imported XML is treated as untrusted input and bounded before parsing.
- Personal Pleco exports stay outside the repository.
- Pleco review scores never directly become conversational mastery.
- Previewing a lesson updates target-rotation history, not mastery evidence.
- LLM assessments are stored with supporting context and can be revised by later evidence.
- I inspect the final diff for generated files, hardcoded credentials, stale TODOs, and claims not supported by a test or manual check.

## What I would automate next

With more time, I would add a recorded Mandarin audio fixture for repeatable end-to-end agent evaluation, a rubric-based regression set for comprehension/usage judgments, and CI that builds every image then runs the Compose smoke test on each pull request.
