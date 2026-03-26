# AI Evals Platform

![React + TypeScript](https://img.shields.io/badge/React_19_+_TypeScript-61DAFB?logo=react&logoColor=white)
![Vite + Tailwind](https://img.shields.io/badge/Vite_7_+_Tailwind_v4-646CFF?logo=vite&logoColor=white)
![FastAPI + Python](https://img.shields.io/badge/FastAPI_+_Python_3.12-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-4169E1?logo=postgresql&logoColor=white)
![Docker + Azure](https://img.shields.io/badge/Docker_+_Azure_App_Service-2496ED?logo=docker&logoColor=white)

Full-stack evaluation platform for AI outputs in production clinical and conversational workflows. Gives QA teams a structured, reproducible way to measure, compare, and audit AI model performance — backed by versioned prompts/schemas, a background job pipeline, and a unified result store.

---

## Workspaces

| App | What it evaluates | How |
|-----|------------------|-----|
| **Voice Rx** | Medical transcription quality | Upload audio + reference transcript, two-call LLM pipeline (transcribe → critique) |
| **Kaira Bot** | Conversational AI quality | Bulk thread evaluation from CSV, custom evaluators, adversarial testing against live API |
| **Inside Sales** | AI-assisted sales calls | Pull from LeadSquared, multi-agent structured scoring, per-agent scorecards |

## Architecture

```
Browser (React SPA)              Server (FastAPI)                   Database
┌────────────────────┐  /api   ┌──────────────────────────┐      ┌──────────┐
│ Zustand (16 stores)│────────>│ 20 API routers            │─────>│          │
│ API client layer   │<────────│ 8 job handlers            │<─────│ Postgres │
│ cn() + Tailwind v4 │         │ 4 LLM providers           │      │ 28 tables│
└────────────────────┘         │ Rate-limited auth          │      └──────────┘
  dev :5173 / prod :80         └──────────────────────────┘
                                         :8721
```

**Key design decisions:**
- Frontend is a thin client — all LLM calls, evaluation logic, and persistence run on the backend
- Every long-running operation is a background job with polling, cancellation, and crash recovery
- Multi-tenant with RBAC — invite-only signup, role-based permissions, per-role app access
- LLM provider abstraction — runners never call SDKs directly

## Quick Start (Local)

```bash
cp .env.backend.example .env.backend    # add at least one LLM API key + JWT_SECRET
touch service-account.json              # placeholder if not using Vertex AI
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8721/api/health |
| PostgreSQL | localhost:5432 |

First login uses `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env.backend` (bootstrap admin, created on first startup if no users exist).

## Production Deployment (Azure)

Deployed via **Azure App Service** running `docker-compose.prod.yml`. CI/CD is tag-triggered — no deploys on every push.

```bash
git tag v1.2.0
git push origin v1.2.0
# GitHub Actions builds images → pushes to ACR → deploys to App Service
```

| Azure Service | Purpose |
|---------------|---------|
| App Service (Linux, Containers) | Runs frontend (nginx) + backend (uvicorn) |
| PostgreSQL Flexible Server | Application database |
| Blob Storage | Uploaded audio, transcripts, files |
| Container Registry (ACR) | Docker image storage |
| Key Vault | Secrets (JWT, API keys, service account) |

**Full setup guide for DevOps:** [`docs/devops-handover.md`](docs/devops-handover.md)

## Documentation

| Doc | Purpose |
|-----|---------|
| [`docs/PROJECT 101.md`](docs/PROJECT%20101.md) | Product overview, architecture, data flows |
| [`docs/SETUP.md`](docs/SETUP.md) | Local + Azure setup (step-by-step) |
| [`docs/devops-handover.md`](docs/devops-handover.md) | DevOps deployment brief (Azure services, env vars, CI/CD) |
| [`CLAUDE.md`](CLAUDE.md) | Claude agent coding guide |
| [`AGENTS.md`](AGENTS.md) | General agent coding guide |
| In-app guide (`/guide`) | Interactive architecture explorer (run `npm run sync:guide` to refresh) |

## Project Structure

```
├── src/                        # React frontend
│   ├── features/               # Domain modules (voiceRx, evalRuns, kaira, settings, admin, ...)
│   ├── components/ui/          # Shared UI primitives
│   ├── stores/                 # 16 Zustand stores
│   ├── services/api/           # HTTP client, job polling, resource APIs
│   └── services/logger/        # Structured logging (silent in production builds)
├── backend/
│   ├── app/main.py             # FastAPI app, router registration, lifespan
│   ├── app/models/             # 28 SQLAlchemy ORM models
│   ├── app/routes/             # 20 API routers
│   ├── app/services/evaluators/# LLM providers + evaluation runners
│   └── app/services/reports/   # Report aggregation, PDF generation
├── docker-compose.yml          # Local dev (hot-reload, source mounts)
├── docker-compose.prod.yml     # Production (baked images, no mounts)
├── Dockerfile.frontend.prod    # Multi-stage: npm build → nginx
├── backend/Dockerfile.prod     # Production uvicorn + Playwright
└── .github/workflows/deploy.yml# CI/CD: tag → ACR → App Service
```

## License

Proprietary. All rights reserved. Built by TatvaCare.
