# AI Evals Platform Setup

Two tracks:

1. **Local Development** — Docker Compose (recommended)
2. **Azure Production** — App Service + Docker Compose + PostgreSQL Flexible Server

---

## 1) Local Setup

### Prerequisites

- Docker Desktop installed and running
- Git installed
- At least one LLM API key (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`)

### Step 1 — Clone and enter the repo

```bash
git clone <repo-url>
cd ai-evals-platform
```

### Step 2 — Configure backend environment

```bash
cp .env.backend.example .env.backend
```

Edit `.env.backend`. Required settings:

```env
JWT_SECRET=<random-64-char-hex>        # generate: openssl rand -hex 32
DEFAULT_LLM_PROVIDER=gemini            # gemini | openai | azure_openai | anthropic
```

At least one LLM provider key:

```env
GEMINI_API_KEY=<your-key>
OPENAI_API_KEY=<your-key>
AZURE_OPENAI_API_KEY=<your-key>
ANTHROPIC_API_KEY=<your-key>
```

Optional — Gemini Vertex AI (service account auth for backend jobs):

```env
GEMINI_AUTH_METHOD=service_account
GEMINI_SERVICE_ACCOUNT_PATH=service-account.json
```

Optional — Azure OpenAI:

```env
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2025-03-01-preview
AZURE_OPENAI_MODEL=<deployment-name>
```

Optional — admin bootstrap (used only when DB has no users):

```env
ADMIN_EMAIL=admin@evals.local
ADMIN_PASSWORD=<strong-password>
ADMIN_TENANT_NAME=Default
ADMIN_TENANT_ALLOWED_DOMAINS=          # e.g., @company.com,@other.com
```

### Step 3 — Ensure service-account.json exists

Docker Compose mounts `./service-account.json` into the backend container. If you are not using Vertex AI, create a placeholder:

```bash
touch service-account.json
```

### Step 4 — Start all services

```bash
docker compose up --build
```

### Step 5 — Verify

| Service           | Container        | Port | URL                              |
| ----------------- | ---------------- | ---: | -------------------------------- |
| Frontend (Vite)   | `evals-frontend` | 5173 | http://localhost:5173             |
| Backend (FastAPI) | `evals-backend`  | 8721 | http://localhost:8721/api/health  |
| PostgreSQL 16     | `evals-postgres` | 5432 | n/a                              |

Expected health response:

```json
{ "status": "ok", "database": "connected" }
```

The interactive guide is available at http://localhost:5173/guide (built into the main app).

### Common local commands

```bash
docker compose down              # stop, keep DB data
docker compose down -v           # stop, wipe DB volume
docker compose logs -f backend   # tail backend logs
npm run dev:stack                # alias for docker compose up --build
npm run sync:guide               # regenerate guide data from backend source

# Database shell
docker exec -it evals-postgres psql -U evals_user -d ai_evals_platform
```

### Optional: run without Docker

Backend:

```bash
pyenv activate venv-python-ai-evals-arize
pip install -r backend/requirements.txt
PYTHONPATH=backend python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8721
```

Frontend (separate shell):

```bash
npm install
npm run dev
```

---

## 2) Azure Production Setup

> **Full step-by-step guide for DevOps:** see `docs/devops-handover.md`

### Architecture overview

```
                    ┌──────────────────────────────────────┐
                    │           Azure Resource Group        │
                    │                                      │
  Users ──HTTPS──▶  │  ┌─────────────────────────────┐    │
                    │  │  App Service (Linux)          │    │
                    │  │  docker-compose.prod.yml      │    │
                    │  │                               │    │
                    │  │  ┌──────────┐ ┌───────────┐  │    │
                    │  │  │ frontend │ │  backend  │  │    │
                    │  │  │  :80     │ │   :8721   │  │    │
                    │  │  │  nginx   │ │  FastAPI  │  │    │
                    │  │  │  React   │ │  workers  │  │    │
                    │  │  └──────────┘ └─────┬─────┘  │    │
                    │  └────────────────────-┼────────┘    │
                    │                        │             │
                    │     ┌──────────────────┼──────────┐  │
                    │     │                  │          │  │
                    │     ▼                  ▼          │  │
                    │  ┌────────┐       ┌──────────┐    │  │
                    │  │ PG 16  │       │ Blob     │    │  │
                    │  │Flexible│       │ Storage  │    │  │
                    │  │ Server │       │ (files)  │    │  │
                    │  └────────┘       └──────────┘    │  │
                    │                                   │  │
                    │  ┌────────┐  ┌────────────────┐   │  │
                    │  │  ACR   │  │   Key Vault    │   │  │
                    │  │(images)│  │  (secrets)     │   │  │
                    │  └────────┘  └────────────────┘   │  │
                    └───────────────────────────────────┘  │
                              │
                    External  │  LLM API calls
                              ▼
                    Gemini / OpenAI / Azure OpenAI / Anthropic
```

### Azure services used

| Component      | Azure Service                        | SKU / Tier       | Purpose                                     |
| -------------- | ------------------------------------ | ---------------- | ------------------------------------------- |
| App hosting    | Azure App Service (Linux, Containers)| B2 or P1v3       | Runs docker-compose.prod.yml (both containers) |
| Database       | Azure Database for PostgreSQL        | Burstable B2ms   | Application data                            |
| File storage   | Azure Blob Storage                   | Standard LRS     | Uploaded audio, transcripts, JSON files     |
| Image registry | Azure Container Registry             | Basic            | Docker images for frontend + backend        |
| Secrets        | Azure Key Vault                      | Standard         | JWT secret, DB credentials, API keys        |

### CI/CD pipeline

Deploys are triggered by git tag push — not by every commit to main.

```bash
git tag v1.2.0
git push origin v1.2.0
```

GitHub Actions (`.github/workflows/deploy.yml`) then:
1. Builds frontend + backend Docker images
2. Pushes both to ACR tagged as `v1.2.0` and `latest`
3. Deploys `docker-compose.prod.yml` to App Service

**Required GitHub repository secrets** (Settings → Secrets and variables → Actions):

| Secret | How to get it |
|---|---|
| `AZURE_CREDENTIALS` | `az ad sp create-for-rbac --name evals-deploy --role contributor --scopes /subscriptions/<sub>/resourceGroups/<rg> --sdk-auth` |
| `ACR_LOGIN_SERVER` | ACR resource → Login server |
| `ACR_USERNAME` | ACR resource → Access keys → Username |
| `ACR_PASSWORD` | ACR resource → Access keys → Password |
| `AZURE_RESOURCE_GROUP` | Your resource group name |
| `AZURE_WEBAPP_NAME` | Your App Service name |

### App URL

App Service provides a free default URL out of the box:
```
https://your-app-name.azurewebsites.net
```
Set `CORS_ORIGINS` and `APP_BASE_URL` env vars to match this URL before first deploy. To switch to a custom domain later (e.g. `evals.tatvacare.in`), update only these two env vars — no redeploy needed.

### Updating env vars after deployment

Env vars can be changed at any time without redeploying. Container restarts automatically (~30 seconds):
- **Portal:** App Service → Configuration → Application settings → edit → Save
- **CLI:** `az webapp config appsettings set --resource-group <rg> --name <app> --settings KEY=value`

### Step 1 — Define deployment variables

These are for reference only. The full step-by-step process is in `docs/devops-handover.md`.

```bash
export RG="rg-ai-evals"
export LOCATION="eastus"
export PG_SERVER="<globally-unique-pg-name>"         # e.g., evals-pg-prod
export PG_DB="ai_evals_platform"
export STORAGE_ACCOUNT="<globally-unique-storage>"   # lowercase, no hyphens
export STORAGE_CONTAINER="evals-files"
export ACR_NAME="<globally-unique-acr>"
export WEBAPP_NAME="<globally-unique-app-service>"
export JWT_SECRET="$(openssl rand -hex 32)"
export ADMIN_EMAIL="admin@tatvacare.in"
export ADMIN_PASSWORD="<strong-password>"
export ADMIN_TENANT_NAME="Tatvacare"
```

### Step 2 — Provision Azure resources (DevOps)

See `docs/devops-handover.md` for the complete setup. Summary:

1. Create resource group, ACR, App Service (Linux, B2), PostgreSQL Flexible Server, Blob Storage container
2. Configure all App Service Application Settings (env vars from the reference table below)
3. Set up GitHub Actions secrets in the repo
4. Grant App Service pull access to ACR

### Step 3 — First deploy

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions builds images, pushes to ACR, deploys to App Service. Takes ~5-8 minutes.

**Verify:**
```bash
curl "https://<your-app>.azurewebsites.net/api/health"
# Expected: {"status":"ok","database":"connected"}
```

### Step 4 — First login checklist

1. Log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`
2. Seed evaluators for each app (one-time, from admin panel or API):
   - `POST /api/evaluators/seed-defaults?appId=voice-rx`
   - `POST /api/evaluators/seed-defaults?appId=kaira-bot`
   - `POST /api/evaluators/seed-defaults?appId=inside-sales`
3. Create roles with appropriate permissions and app access before inviting users
4. Generate invite links for your first users
5. Rotate admin password

---

## Post-deployment

### Custom domain

Start with the free `azurewebsites.net` URL. When ready to switch to a custom domain (e.g. `evals.tatvacare.in`):

1. Add a CNAME in DNS: `evals.tatvacare.in` → `<app-name>.azurewebsites.net`
2. Bind custom domain in App Service → Custom domains
3. Update two env vars (no redeploy needed):
   ```bash
   az webapp config appsettings set \
     --resource-group "$RG" --name "$WEBAPP_NAME" \
     --settings CORS_ORIGINS=https://evals.tatvacare.in APP_BASE_URL=https://evals.tatvacare.in
   ```

### Restrict PostgreSQL access

After deployment, lock down the database to only allow App Service outbound IPs:

```bash
# Get App Service outbound IPs
OUTBOUND_IPS=$(az webapp show \
  --resource-group "$RG" --name "$WEBAPP_NAME" \
  --query outboundIpAddresses -o tsv)

# Add each outbound IP to PostgreSQL firewall
for IP in $(echo "$OUTBOUND_IPS" | tr ',' '\n'); do
  az postgres flexible-server firewall-rule create \
    --resource-group "$RG" --name "$PG_SERVER" \
    --rule-name "appservice-$(echo $IP | tr '.' '-')" \
    --start-ip-address "$IP" --end-ip-address "$IP"
done
```

### Monitoring

- **Logs:** App Service → Log stream (live) or Diagnose and solve problems → Application logs
- **Database:** Azure Portal → PostgreSQL resource → Monitoring → Metrics (CPU, connections, storage)

Recommended alerts:

| Metric                        | Threshold       | Action                |
| ----------------------------- | --------------- | --------------------- |
| Backend `/api/health` failure | 3 consecutive   | Email notification    |
| PostgreSQL CPU > 80%          | 5 min sustained | Scale up SKU          |
| PostgreSQL storage > 80%      | —               | Increase storage      |

### Deploying a new version

```bash
git tag v1.2.3
git push origin v1.2.3
```

GitHub Actions handles everything. No manual steps.

### Backup and disaster recovery

- **PostgreSQL**: Enable automated backups (7-day retention by default on Flexible Server). For longer retention or geo-redundant backups:

```bash
az postgres flexible-server update \
  --resource-group "$RG" \
  --name "$PG_SERVER" \
  --backup-retention 14
```

- **Blob Storage**: Enable soft delete for blobs (protects against accidental deletion):

```bash
az storage blob service-properties delete-policy update \
  --account-name "$STORAGE_ACCOUNT" \
  --enable true \
  --days-retained 7
```

- **Point-in-time restore**: PostgreSQL Flexible Server supports restore to any point within the retention window via Azure Portal or CLI.

### Cost estimation (approximate monthly, USD)

| Service                       | SKU                | Estimated Cost |
| ----------------------------- | ------------------ | -------------- |
| PostgreSQL Flexible Server    | Burstable B1ms     | ~$13           |
| Container Apps (1 replica)    | 1 vCPU / 2 GiB    | ~$36           |
| Static Web Apps               | Standard           | ~$9            |
| Blob Storage (< 10 GB)       | Standard LRS       | ~$0.25         |
| Container Registry            | Basic              | ~$5            |
| **Total (minimum)**           |                    | **~$63/month** |

Costs scale with Container Apps replicas, database compute tier, and storage volume. LLM API costs are separate and depend on usage.

---

## Environment variable reference

| Variable                             | Required | Default              | Description                                     |
| ------------------------------------ | -------- | -------------------- | ----------------------------------------------- |
| `DATABASE_URL`                       | Yes      | —                    | PostgreSQL async connection string              |
| `JWT_SECRET`                         | Yes      | —                    | 64-char hex for JWT signing                     |
| `DEFAULT_LLM_PROVIDER`              | Yes      | `gemini`             | Default LLM provider                            |
| `API_PORT`                           | No       | `8721`               | Backend listen port                             |
| `CORS_ORIGINS`                       | No       | `http://localhost:5173` | Comma-separated allowed origins              |
| `FILE_STORAGE_TYPE`                  | No       | `local`              | `local` or `azure_blob`                         |
| `FILE_STORAGE_PATH`                  | No       | `./backend/uploads`  | Local file storage path                         |
| `AZURE_STORAGE_CONNECTION_STRING`    | Prod     | —                    | Azure Blob connection string                    |
| `AZURE_STORAGE_CONTAINER`            | Prod     | `evals-files`        | Blob container name                             |
| `GEMINI_API_KEY`                     | If used  | —                    | Gemini Developer API key                        |
| `GEMINI_SERVICE_ACCOUNT_PATH`        | Local dev| —                    | Path to Vertex AI service account JSON (dev only) |
| `GEMINI_SERVICE_ACCOUNT_JSON`        | Prod     | —                    | Base64-encoded service account JSON (production) |
| `GEMINI_AUTH_METHOD`                 | No       | `api_key`            | `api_key` or `service_account`                  |
| `OPENAI_API_KEY`                     | If used  | —                    | OpenAI API key                                  |
| `AZURE_OPENAI_API_KEY`              | If used  | —                    | Azure OpenAI API key                            |
| `AZURE_OPENAI_ENDPOINT`             | If used  | —                    | Azure OpenAI endpoint URL                       |
| `AZURE_OPENAI_API_VERSION`          | No       | `2025-03-01-preview` | Azure OpenAI API version                        |
| `AZURE_OPENAI_MODEL`               | If used  | —                    | Azure OpenAI deployment name                    |
| `ANTHROPIC_API_KEY`                  | If used  | —                    | Anthropic API key                               |
| `ADMIN_EMAIL`                        | First run| `admin@evals.local`  | Bootstrap admin email                           |
| `ADMIN_PASSWORD`                     | First run| `changeme`           | Bootstrap admin password                        |
| `ADMIN_TENANT_NAME`                  | First run| `Default`            | Bootstrap tenant name                           |
| `ADMIN_TENANT_ALLOWED_DOMAINS`       | No       | —                    | Comma-separated email domains for signup        |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`    | No       | `15`                 | Access token lifetime                           |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS`      | No       | `7`                  | Refresh token lifetime                          |
| `KAIRA_API_URL`                      | If used  | —                    | Kaira API URL for adversarial testing           |
| `KAIRA_AUTH_TOKEN`                   | If used  | —                    | Kaira API auth token                            |
| `ADVERSARIAL_MAX_TURNS`              | No       | `10`                 | Max turns per adversarial conversation          |
| `ADVERSARIAL_TURN_DELAY`            | No       | `1.5`                | Seconds between adversarial turns               |
| `ADVERSARIAL_CASE_DELAY`            | No       | `3.0`                | Seconds between adversarial test cases          |
| `LSQ_BASE_URL`                       | If used  | —                    | LeadSquared API base URL (Inside Sales)         |
| `LSQ_ACCESS_KEY`                     | If used  | —                    | LeadSquared access key                          |
| `LSQ_SECRET_KEY`                     | If used  | —                    | LeadSquared secret key                          |
| `APP_BASE_URL`                       | Prod     | `http://localhost:5173` | Public app URL — used in invite link emails  |
