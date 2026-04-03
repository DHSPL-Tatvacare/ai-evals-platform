# AI Evals Platform

![React + TypeScript](https://img.shields.io/badge/React_19_+_TypeScript-61DAFB?logo=react&logoColor=white)
![FastAPI + Python](https://img.shields.io/badge/FastAPI_+_Python_3.12-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-4169E1?logo=postgresql&logoColor=white)
![Docker + Azure](https://img.shields.io/badge/Docker_+_Azure_App_Service-2496ED?logo=docker&logoColor=white)

AI Evals Platform is a multi-tenant evaluation system for production AI workflows. It gives product, QA, and operations teams a repeatable way to score outputs, review evidence, compare runs, and audit how AI behavior changes over time across clinical transcription, conversational AI, and inside-sales use cases.

## Workspaces

| Workspace | App ID | Primary use case |
| --- | --- | --- |
| Voice Rx | `voice-rx` | Medical transcription and structured extraction quality |
| Kaira Bot | `kaira-bot` | Chat quality, custom evaluators, batch thread evaluation, and adversarial testing |
| Inside Sales | `inside-sales` | LeadSquared-backed call quality evaluation and reporting |

## Stack

- Frontend: React 19, TypeScript, Vite 7, Tailwind CSS 4, Zustand
- Backend: FastAPI, SQLAlchemy, PostgreSQL, background job worker
- AI providers: Gemini, OpenAI, Azure OpenAI, Anthropic
- Deployment: Docker, Azure App Service, Azure Container Registry, Azure Database for PostgreSQL, Azure Blob Storage

## Quick start

```bash
cp .env.backend.example .env.backend
touch service-account.json
docker compose up --build
```

Local services:

| Service | URL / Port | Notes |
| --- | --- | --- |
| Frontend | http://localhost:5173 | React development server |
| Backend | http://localhost:8721/api/health | FastAPI API |
| PostgreSQL | localhost:5432 | Local database |
| Worker | no public port | Runs background jobs separately from the API container |

If you are using Gemini on Vertex AI with the Docker stack, point `GEMINI_SERVICE_ACCOUNT_PATH` at `/app/service-account.json`. If you are running the backend directly outside Docker, use the local file path instead. Otherwise, the placeholder file is enough to satisfy the Docker mount.

## Deployment model

Production deploys are tag-triggered through `.github/workflows/deploy.yml`. `docker-compose.prod.yml` runs three services on Azure App Service:

- `frontend` on port 80 behind nginx
- `backend` on port 8721
- `worker` as a dedicated background job process

Uploaded files are stored in Azure Blob Storage, and PostgreSQL runs outside the compose stack on Azure Database for PostgreSQL.

## Documentation

| Document | Purpose |
| --- | --- |
| [`docs/PROJECT 101.md`](docs/PROJECT%20101.md) | Product, architecture, workflows, and core abstractions |
| [`docs/SETUP.md`](docs/SETUP.md) | Local and production setup, environment variables, and operational commands |
| [`docs/devops-handover.md`](docs/devops-handover.md) | Production deployment handover for DevOps and cloud operations |
| [`AGENTS.md`](AGENTS.md) | Repository rules for coding agents |
| [`CLAUDE.md`](CLAUDE.md) | Claude-specific agent guide |
| [`.github/copilot-instructions.md`](.github/copilot-instructions.md) | Copilot-facing mirror of the agent guide |

## Repository layout

```text
backend/                  FastAPI app, ORM models, job worker, evaluators, and reports
src/                      React application, feature modules, stores, and shared services
docker-compose.yml        Local development stack
docker-compose.prod.yml   Production multi-container deployment
Dockerfile.frontend       Frontend development image
Dockerfile.frontend.prod  Frontend production image
backend/Dockerfile        Backend development image
backend/Dockerfile.prod   Backend production image
nginx.prod.conf           Production nginx config
```

## License

Proprietary. All rights reserved. Built by TatvaCare.
