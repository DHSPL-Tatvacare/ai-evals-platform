# AI Evals Platform

Full-stack evaluation system for AI outputs in production clinical and conversational workflows. Gives QA teams a structured, reproducible way to measure, compare, and audit AI model performance with a versioned prompt/schema system, background job pipeline, and unified result store.

Two active workspaces: Voice Rx (medical transcription evaluation) and Kaira Bot (conversational AI evaluation).

## Tech Stack

- Frontend: React 19, TypeScript (strict), Vite 7, Tailwind v4, Zustand (14 stores)
- Backend: FastAPI, async SQLAlchemy 2, asyncpg, Python 3.12
- Database: PostgreSQL 16 with JSONB
- LLM Providers: Gemini (Vertex AI + API key), OpenAI, Azure OpenAI, Anthropic
- Execution: Background job worker — 7 registered handlers, cooperative cancellation, crash recovery
- Deployment: Docker Compose (local), Azure Container Apps + Static Web Apps (production)

## Quick Start (Local)

```bash
cp .env.backend.example .env.backend
# Edit .env.backend — add at least GEMINI_API_KEY or OPENAI_API_KEY
touch service-account.json
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend health: http://localhost:8721/api/health

## Documentation

- Product overview, architecture, data flows: `docs/PROJECT 101.md`
- Full setup guide (local + Azure): `docs/SETUP.md`
- Agent coding guide: `AGENTS.md`
- Claude coding guide: `CLAUDE.md`
- Interactive architecture guide: `docs/guide/index.html` (run with `npm run dev:guide`)

## License

Proprietary. All rights reserved. Built by TatvaCare.
