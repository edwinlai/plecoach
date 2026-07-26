# [General] Take-home Project

# Take-home Project

## The Challenge

Build a **real-time voice AI tutor** using LiveKit. The project should have a **backend** that powers the voice agent and a **frontend** that lets a user talk to it.

The tutor can teach anything — pick a subject you find fun or interesting. Beyond getting the core voice interaction working, use your product sense to decide what features make this a great tutoring experience and tell us about your choices in the README.

Additionally, you must include a file `workflow.md` that describes your workflow for completing the project. Please list any AI tools, specific models, harnesses, etc as well as a description of how you use them. Be specific! We want to understand how you use AI in your workflow to make you a faster and more productive engineer.

You can sign up for a free LiveKit account at https://cloud.livekit.io.

**Expected time: 2 hours.** We value working software over polish.

---

## Requirements

- Runnable using docker and docker-compose.
- use Redis as a backing state store for conversations.

---

## What We're Looking For

- **Working software** — We require services to be run with docker + docker compose. We should be able to clone your repo, add a `.env` file, then build and run the project with docker compose. **If we can't run your project, we cannot move forward.**
- **Clean architecture** — Clear separation of concerns between session management, conversation handling, and the voice/AI layer.
- **Tradeoff reasoning** — Use your README to briefly explain key decisions you made and why.
- **Scalability awareness** — You don't need to build for millions of users, but your README should briefly address: *What would you change if this needed to handle 10,000 concurrent sessions?*

---

## Submission Format

Submit a **git repository** (GitHub link or zip) containing:

1. **All source code** for frontend and backend.
2. **`PROMPT.md`** that contains this prompt exactly. 
3. **`README.md`** with:
   - Architecture overview (a short paragraph or simple diagram).
   - Key design decisions and tradeoffs.
   - A brief note on how you'd scale the system.
4. **`.env.example`** listing every environment variable needed to run the project (e.g., `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_URL`, LLM API keys, etc.). We will create our own `.env` from this template to run your project.
5. The project **must read all secrets and configuration from a `.env` file** in the project root. No hardcoded keys.
6. **`workflow.md`** describing your workflow, AI tools used, specific models, harnesses, and how you use them.
7. A short video walkthrough of the interface and agent functioning

---

## Guidance

- **Use AI tools freely.** We encourage using Claude, Cursor, Copilot, or any AI assistant. Use agents and create custom skills/automations where it helps. We care about the result and your ability to leverage tools effectively — not whether you typed every line by hand.
- **LiveKit has great docs.** Start with their Agents quickstart — it covers setting up a Python or Node voice agent quickly.

---

Good luck — we're excited to see what you build.
