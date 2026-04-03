# DevOps Handover - AI Evals Platform

This handover is for the engineer responsible for production deployment and ongoing operations. It is intentionally self-contained and reflects the current repository state.

---

## 1. Production system summary

AI Evals Platform is deployed as a multi-container application with separate API and worker processes.

### Production services

`docker-compose.prod.yml` defines:

| Service | Image | Port | Purpose |
| --- | --- | --- | --- |
| `frontend` | `${ACR_LOGIN_SERVER}/evals-frontend:${IMAGE_TAG}` | 80 | nginx serving the SPA and proxying `/api/*` |
| `backend` | `${ACR_LOGIN_SERVER}/evals-backend:${IMAGE_TAG}` | 8721 | FastAPI API |
| `worker` | `${ACR_LOGIN_SERVER}/evals-backend:${IMAGE_TAG}` | none | Dedicated background job worker |

Production infrastructure outside the compose file:

| Component | Azure service |
| --- | --- |
| Image registry | Azure Container Registry |
| App hosting | Azure App Service (Linux, multi-container) |
| Database | Azure Database for PostgreSQL |
| File storage | Azure Blob Storage |
| Secret storage | Azure Key Vault (recommended) |

There is no PostgreSQL container in production.

---

## 2. Repo files that matter for deployment

| File | Why it matters |
| --- | --- |
| `.github/workflows/deploy.yml` | GitHub Actions pipeline for build and deploy |
| `docker-compose.prod.yml` | Production service definition |
| `backend/Dockerfile.prod` | Backend production image build |
| `Dockerfile.frontend.prod` | Frontend production image build |
| `backend/entrypoint.sh` | Decodes Gemini service account JSON in production |
| `nginx.prod.conf` | SPA hosting and `/api/*` reverse proxy |
| `backend/app/config.py` | Runtime application configuration surface |

---

## 3. CI/CD behavior

### Trigger

Production deploys are triggered by pushing a semantic version tag:

```bash
git tag v1.2.0
git push origin v1.2.0
```

### Current workflow behavior

The workflow in `.github/workflows/deploy.yml`:

1. checks out the repository
2. extracts the git tag into `IMAGE_TAG`
3. logs in to Azure Container Registry
4. builds and pushes:
   - `evals-backend:<tag>`
   - `evals-backend:latest`
   - `evals-frontend:<tag>`
   - `evals-frontend:latest`
5. deploys `docker-compose.prod.yml` to Azure App Service

### GitHub secrets used by the current workflow

| Secret | Required by current workflow |
| --- | --- |
| `AZURE_CREDENTIALS` | yes |
| `ACR_LOGIN_SERVER` | yes |
| `ACR_USERNAME` | yes |
| `ACR_PASSWORD` | yes |
| `AZURE_WEBAPP_NAME` | yes |

`AZURE_RESOURCE_GROUP` is not currently used by the workflow. Keep it as an operational convenience only if your team wants it for manual scripts.

---

## 4. Azure resources to provision

Provision these before the first production deploy:

| Resource | Purpose |
| --- | --- |
| Azure Container Registry | Stores frontend and backend images |
| Azure App Service (Linux) | Runs the production compose file |
| Azure Database for PostgreSQL | Application database |
| Azure Storage Account + blob container | Uploaded files |
| Azure Key Vault | Secret management |

Recommended blob container name: `evals-files`

Recommended database name: `ai_evals_platform`

---

## 5. Runtime configuration

### Required application settings

These should be present in App Service configuration before the first live deploy:

| Variable | Notes |
| --- | --- |
| `DATABASE_URL` | PostgreSQL async connection string |
| `FILE_STORAGE_TYPE` | Set to `azure_blob` in production |
| `AZURE_STORAGE_CONNECTION_STRING` | Blob Storage connection string |
| `AZURE_STORAGE_CONTAINER` | Usually `evals-files` |
| `CORS_ORIGINS` | Public allowed origin list |
| `APP_BASE_URL` | Public base URL used in generated links |
| `JWT_SECRET` | Required JWT signing secret |
| `JOB_RUN_EMBEDDED_WORKER` | Set to `false` because production has a dedicated worker service |

Bootstrap values for first startup against an empty database:

| Variable | Notes |
| --- | --- |
| `ADMIN_EMAIL` | Initial admin login |
| `ADMIN_PASSWORD` | Initial admin password |
| `ADMIN_TENANT_NAME` | Initial tenant name |
| `ADMIN_TENANT_ALLOWED_DOMAINS` | Optional comma-separated domain allowlist |

### LLM provider settings

Set only the providers you intend to use, but make sure at least one usable provider exists.

| Provider | Variables |
| --- | --- |
| Gemini | `GEMINI_API_KEY`, `GEMINI_AUTH_METHOD`, `GEMINI_SERVICE_ACCOUNT_PATH`, `GEMINI_MODEL` |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_MODEL` |
| Anthropic | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |

Shared provider settings:

- `DEFAULT_LLM_PROVIDER`
- `EVAL_TEMPERATURE`

### Gemini on Vertex AI in production

Production uses `GEMINI_SERVICE_ACCOUNT_JSON`, which is decoded by `backend/entrypoint.sh` into `/app/service-account.json`. For that mode:

| Variable | Value |
| --- | --- |
| `GEMINI_AUTH_METHOD` | `service_account` |
| `GEMINI_SERVICE_ACCOUNT_JSON` | base64-encoded service account JSON |

`GEMINI_SERVICE_ACCOUNT_JSON` is not defined in `config.py`, but it is part of the real production runtime path because the entrypoint script consumes it.

### Optional integration settings

| Area | Variables |
| --- | --- |
| Kaira | `KAIRA_API_URL`, `KAIRA_AUTH_TOKEN`, `KAIRA_TEST_USER_ID` |
| LeadSquared | `LSQ_BASE_URL`, `LSQ_ACCESS_KEY`, `LSQ_SECRET_KEY` |
| Adversarial tuning | `ADVERSARIAL_MAX_TURNS`, `ADVERSARIAL_TURN_DELAY`, `ADVERSARIAL_CASE_DELAY` |
| Auth tuning | `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`, `AUTH_RATE_LIMIT` |
| Upload controls | `MAX_UPLOAD_SIZE_MB`, `ALLOWED_UPLOAD_MIMES` |
| Job tuning | all `JOB_*` variables from `backend/app/config.py` |

### Deploy-time variables

These are used to render the production compose file rather than by the FastAPI settings object:

| Variable | Used by |
| --- | --- |
| `ACR_LOGIN_SERVER` | image references in `docker-compose.prod.yml` |
| `IMAGE_TAG` | image tag selection in `docker-compose.prod.yml` |

In the current workflow, GitHub Actions injects both values during deployment.

---

## 6. Operational behavior you should know

### Worker model

The API and worker are separate processes in production.

- `backend` serves HTTP traffic
- `worker` runs `python -m app.worker`
- both containers share the same runtime configuration surface

The worker supports:

- queue classes: `interactive`, `standard`, `bulk`
- priorities
- heartbeats and leases
- retry scheduling
- stale job recovery
- orphaned eval-run reconciliation
- per-tenant, per-app, and per-user concurrency controls

### File handling

- production file storage should be Azure Blob Storage
- nginx accepts request bodies up to 100 MB
- the backend enforces upload validation using `MAX_UPLOAD_SIZE_MB` and `ALLOWED_UPLOAD_MIMES`

### Public routing

- nginx listens on port 80
- `/api/*` proxies to `backend:8721`
- SPA routes fall back to `index.html`

---

## 7. First deployment checklist

1. provision Azure resources
2. create the Blob container
3. create the PostgreSQL database
4. configure App Service settings
5. add GitHub repository secrets
6. push a version tag
7. confirm `/api/health` responds successfully
8. perform first admin login
9. seed evaluators per app if needed
10. rotate bootstrap credentials

Evaluator seeding endpoints:

```text
POST /api/evaluators/seed-defaults?appId=voice-rx
POST /api/evaluators/seed-defaults?appId=kaira-bot
POST /api/evaluators/seed-defaults?appId=inside-sales
```

---

## 8. Verification and troubleshooting

### Health check

```bash
curl "https://<your-app>.azurewebsites.net/api/health"
```

Expected result:

```json
{"status":"ok","database":"connected"}
```

### What to check if jobs are not progressing

1. confirm the `worker` container is present in the deployed compose stack
2. confirm `JOB_RUN_EMBEDDED_WORKER=false`
3. confirm the worker has the same database and storage settings as the API
4. inspect App Service logs for the `worker` process
5. inspect `/api/admin` operational surfaces if your deployment exposes them to administrators

### What to check if file-backed workflows fail

1. confirm `FILE_STORAGE_TYPE=azure_blob`
2. confirm the storage connection string is valid
3. confirm the blob container exists
4. confirm request sizes fit under nginx and backend limits

### What to check if Vertex AI-backed Gemini flows fail

1. confirm `GEMINI_AUTH_METHOD=service_account`
2. confirm `GEMINI_SERVICE_ACCOUNT_JSON` is valid base64 for a real service account JSON file
3. confirm the decoded file is available as `/app/service-account.json` inside the backend and worker containers

---

## 9. Handy commands

```bash
# Trigger a deploy
git tag v1.2.3
git push origin v1.2.3

# Health check
curl "https://<your-app>.azurewebsites.net/api/health"

# Update App Service settings manually
az webapp config appsettings set \
  --resource-group <resource-group> \
  --name <webapp-name> \
  --settings KEY=value
```
