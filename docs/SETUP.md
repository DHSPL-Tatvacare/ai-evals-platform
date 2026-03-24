# AI Evals Platform Setup

Two tracks:

1. **Local Development** — Docker Compose (recommended)
2. **Azure Production** — Container Apps + Static Web Apps + PostgreSQL Flexible Server

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

### Architecture overview

```
                    ┌──────────────────────────────────────┐
                    │           Azure Resource Group        │
                    │           rg-ai-evals                │
                    │                                      │
  Users ──HTTPS──▶  │  ┌─────────────────────┐            │
                    │  │  Static Web Apps     │            │
                    │  │  (React SPA)         │            │
                    │  │  - Vite build output  │            │
                    │  │  - /api/* → ACA proxy │            │
                    │  └────────┬────────────┘            │
                    │           │ /api/*                   │
                    │           ▼                          │
                    │  ┌─────────────────────┐            │
                    │  │  Container Apps      │            │
                    │  │  (FastAPI backend)   │            │
                    │  │  - 1–3 replicas      │            │
                    │  │  - Port 8721         │            │
                    │  └──┬──────────┬───────┘            │
                    │     │          │                     │
                    │     ▼          ▼                     │
                    │  ┌────────┐ ┌──────────┐            │
                    │  │ PG 16  │ │ Blob     │            │
                    │  │Flexible│ │ Storage  │            │
                    │  │ Server │ │ (files)  │            │
                    │  └────────┘ └──────────┘            │
                    └──────────────────────────────────────┘
                              │
                    External  │  LLM API calls
                              ▼
                    Gemini / OpenAI / Azure OpenAI / Anthropic
```

### Azure services used

| Component     | Azure Service                        | SKU / Tier       | Purpose                                     |
| ------------- | ------------------------------------ | ---------------- | ------------------------------------------- |
| Database      | Azure Database for PostgreSQL        | Burstable B1ms   | Application data (19 ORM tables)            |
| Backend API   | Azure Container Apps                 | Consumption      | FastAPI + background job worker             |
| Frontend      | Azure Static Web Apps                | Standard         | React SPA + /api proxy to backend           |
| File storage  | Azure Blob Storage                   | Standard LRS     | Uploaded audio, transcripts, JSON files     |
| Image registry| Azure Container Registry             | Basic            | Backend Docker images                       |
| Secrets       | Container Apps secrets               | Built-in         | JWT secret, DB credentials, API keys        |

### Prerequisites

- Azure CLI installed and logged in (`az login`)
- Node.js 20+ and npm installed
- Docker installed (for local image build, or use ACR build)
- Permission to create: resource group, PostgreSQL, storage, ACR, Container Apps, Static Web Apps

### Step 1 — Define deployment variables

Set these once in your shell session. Replace all `<placeholder>` values.

```bash
# Resource group
export RG="rg-ai-evals"
export LOCATION="eastus"

# PostgreSQL
export PG_SERVER="<globally-unique-pg-name>"          # e.g., evals-pg-prod
export PG_DB="ai_evals_platform"
export PG_ADMIN_USER="evals_admin"
export PG_ADMIN_PASSWORD="<strong-password-min-8>"    # URL-encode special chars later

# Blob Storage
export STORAGE_ACCOUNT="<globally-unique-storage>"    # e.g., evalsstorageprod (lowercase, no hyphens)
export STORAGE_CONTAINER="evals-files"

# Container Registry
export ACR_NAME="<globally-unique-acr>"               # e.g., evalscr

# Container Apps
export ACA_ENV="ai-evals-env"
export ACA_APP="ai-evals-backend"

# Static Web Apps
export SWA_NAME="<globally-unique-swa>"               # e.g., evals-frontend

# Auth
export JWT_SECRET="$(openssl rand -hex 32)"

# Admin bootstrap (first run only — creates initial tenant + owner account)
export ADMIN_EMAIL="admin@yourcompany.com"
export ADMIN_PASSWORD="<strong-admin-password>"
export ADMIN_TENANT_NAME="YourCompany"
export ADMIN_TENANT_ALLOWED_DOMAINS="@yourcompany.com"   # comma-separated, optional
```

### Step 2 — Create resource group

```bash
az group create --name "$RG" --location "$LOCATION"
```

### Step 3 — Create PostgreSQL Flexible Server

```bash
az postgres flexible-server create \
  --resource-group "$RG" \
  --name "$PG_SERVER" \
  --location "$LOCATION" \
  --admin-user "$PG_ADMIN_USER" \
  --admin-password "$PG_ADMIN_PASSWORD" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --version 16 \
  --storage-size 32 \
  --public-access 0.0.0.0

az postgres flexible-server db create \
  --resource-group "$RG" \
  --server-name "$PG_SERVER" \
  --database-name "$PG_DB"
```

Build the connection string (URL-encode the password if it has special characters):

```bash
export DATABASE_URL="postgresql+asyncpg://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${PG_SERVER}.postgres.database.azure.com:5432/${PG_DB}?ssl=require"
```

**Verify connectivity** (optional, from a machine with psql):

```bash
psql "host=${PG_SERVER}.postgres.database.azure.com port=5432 dbname=${PG_DB} user=${PG_ADMIN_USER} password=${PG_ADMIN_PASSWORD} sslmode=require"
```

### Step 4 — Create Blob Storage

```bash
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2

az storage container create \
  --name "$STORAGE_CONTAINER" \
  --account-name "$STORAGE_ACCOUNT"

export AZURE_STORAGE_CONNECTION_STRING=$(az storage account show-connection-string \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --query connectionString -o tsv)
```

### Step 5 — Create Container Registry and build backend image

Create the production Dockerfile first. This differs from the dev Dockerfile:
- No `--reload` flag
- 4 uvicorn workers
- Includes Playwright Chromium for PDF report export

```bash
cat > backend/Dockerfile.prod << 'PRODEOF'
FROM python:3.12-slim
WORKDIR /app

# System deps (PostgreSQL client, Playwright Chromium runtime libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libpango-1.0-0 libasound2 libxshmfence1 \
    fonts-noto-cjk fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .
RUN mkdir -p /app/uploads
EXPOSE 8721
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8721", "--workers", "4"]
PRODEOF
```

Create registry and build:

```bash
az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true

az acr build \
  --registry "$ACR_NAME" \
  --image evals-backend:latest \
  ./backend -f ./backend/Dockerfile.prod
```

### Step 6 — Deploy backend to Container Apps

```bash
# Create the Container Apps environment
az containerapp env create \
  --name "$ACA_ENV" \
  --resource-group "$RG" \
  --location "$LOCATION"

# Get ACR credentials
export ACR_PASSWORD=$(az acr credential show \
  --name "$ACR_NAME" \
  --query "passwords[0].value" -o tsv)

# Deploy the backend container
az containerapp create \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --environment "$ACA_ENV" \
  --image "${ACR_NAME}.azurecr.io/evals-backend:latest" \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-username "$ACR_NAME" \
  --registry-password "$ACR_PASSWORD" \
  --target-port 8721 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 1.0 \
  --memory 2Gi \
  --env-vars \
    DATABASE_URL="$DATABASE_URL" \
    JWT_SECRET="$JWT_SECRET" \
    FILE_STORAGE_TYPE=azure_blob \
    AZURE_STORAGE_CONNECTION_STRING="$AZURE_STORAGE_CONNECTION_STRING" \
    AZURE_STORAGE_CONTAINER="$STORAGE_CONTAINER" \
    CORS_ORIGINS="https://placeholder.azurestaticapps.net" \
    API_PORT=8721 \
    DEFAULT_LLM_PROVIDER=gemini \
    ADMIN_EMAIL="$ADMIN_EMAIL" \
    ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    ADMIN_TENANT_NAME="$ADMIN_TENANT_NAME" \
    ADMIN_TENANT_ALLOWED_DOMAINS="$ADMIN_TENANT_ALLOWED_DOMAINS"
```

Get the backend FQDN:

```bash
export BACKEND_FQDN=$(az containerapp show \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)

echo "Backend: https://${BACKEND_FQDN}"
```

**Verify backend health:**

```bash
curl "https://${BACKEND_FQDN}/api/health"
# Expected: {"status":"ok","database":"connected"}
```

### Step 7 — Move secrets out of env vars

Plain `--env-vars` are visible in the Azure Portal. Move sensitive values to Container Apps secrets:

```bash
# Create secrets
az containerapp secret set \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --secrets \
    jwt-secret="$JWT_SECRET" \
    database-url="$DATABASE_URL" \
    storage-conn-str="$AZURE_STORAGE_CONNECTION_STRING" \
    admin-password="$ADMIN_PASSWORD"

# Reference secrets in env vars (secretref: syntax)
az containerapp update \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --set-env-vars \
    JWT_SECRET=secretref:jwt-secret \
    DATABASE_URL=secretref:database-url \
    AZURE_STORAGE_CONNECTION_STRING=secretref:storage-conn-str \
    ADMIN_PASSWORD=secretref:admin-password
```

Add LLM API keys as secrets (add only the providers you use):

```bash
az containerapp secret set \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --secrets \
    gemini-api-key="<your-gemini-key>" \
    openai-api-key="<your-openai-key>"

az containerapp update \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --set-env-vars \
    GEMINI_API_KEY=secretref:gemini-api-key \
    OPENAI_API_KEY=secretref:openai-api-key
```

### Step 8 — Deploy frontend to Static Web Apps

Build the frontend:

```bash
npm ci
npm run build
```

Create the SWA routing config. This rewrites `/api/*` requests to the backend Container App:

```bash
cat > staticwebapp.config.json << SWAEOF
{
  "routes": [
    {
      "route": "/api/*",
      "rewrite": "https://${BACKEND_FQDN}/api/*"
    }
  ],
  "navigationFallback": {
    "rewrite": "/index.html",
    "exclude": ["/assets/*", "/guide/*"]
  },
  "globalHeaders": {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin"
  }
}
SWAEOF

cp staticwebapp.config.json dist/
```

Create and deploy:

```bash
az staticwebapp create \
  --name "$SWA_NAME" \
  --resource-group "$RG" \
  --location eastus2 \
  --sku Standard

export DEPLOY_TOKEN=$(az staticwebapp secrets list \
  --name "$SWA_NAME" \
  --resource-group "$RG" \
  --query "properties.apiKey" -o tsv)

npx @azure/static-web-apps-cli deploy ./dist --deployment-token "$DEPLOY_TOKEN"
```

Get the frontend hostname:

```bash
export FRONTEND_HOST=$(az staticwebapp show \
  --name "$SWA_NAME" \
  --resource-group "$RG" \
  --query defaultHostname -o tsv)

echo "Frontend: https://${FRONTEND_HOST}"
```

### Step 9 — Finalize CORS

Update the backend CORS to allow the actual frontend domain:

```bash
az containerapp update \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --set-env-vars CORS_ORIGINS="https://${FRONTEND_HOST}"
```

### Step 10 — Validate end-to-end

```bash
# Backend health
curl "https://${BACKEND_FQDN}/api/health"

# Frontend loads
curl -s "https://${FRONTEND_HOST}" | head -5
```

Then open `https://${FRONTEND_HOST}` in a browser:

1. Log in with the admin credentials from Step 1
2. Navigate to Settings, configure an LLM provider API key
3. Upload a test listing and run an evaluation
4. Check the interactive guide at `/guide`

---

## Post-deployment

### Custom domain + TLS

```bash
# Static Web Apps — custom domain
az staticwebapp hostname set \
  --name "$SWA_NAME" \
  --resource-group "$RG" \
  --hostname "evals.yourcompany.com"
# SWA provisions a free TLS certificate automatically

# Container Apps — custom domain (if backend needs its own)
az containerapp hostname add \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --hostname "api-evals.yourcompany.com"

# After adding the custom domain, update CORS:
az containerapp update \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --set-env-vars CORS_ORIGINS="https://evals.yourcompany.com"
```

### Restrict PostgreSQL access

After deployment, lock down the database to only allow Container Apps:

```bash
# Get the Container Apps outbound IPs
OUTBOUND_IPS=$(az containerapp show \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --query "properties.outboundIpAddresses" -o tsv)

# Remove the 0.0.0.0 rule and add specific IPs
az postgres flexible-server firewall-rule delete \
  --resource-group "$RG" \
  --name "$PG_SERVER" \
  --rule-name "AllowAll_0_0_0_0" --yes

# Add each outbound IP
for IP in $(echo "$OUTBOUND_IPS" | tr ',' '\n'); do
  RULE_NAME="aca-$(echo $IP | tr '.' '-')"
  az postgres flexible-server firewall-rule create \
    --resource-group "$RG" \
    --name "$PG_SERVER" \
    --rule-name "$RULE_NAME" \
    --start-ip-address "$IP" \
    --end-ip-address "$IP"
done
```

For tighter security, use VNet integration with private endpoints (see [Azure docs](https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom)).

### Monitoring and alerts

```bash
# Enable Container Apps system logs
az monitor diagnostic-settings create \
  --name "aca-logs" \
  --resource "/subscriptions/<sub>/resourceGroups/$RG/providers/Microsoft.App/containerApps/$ACA_APP" \
  --workspace "<log-analytics-workspace-id>" \
  --logs '[{"category":"ContainerAppSystemLogs","enabled":true},{"category":"ContainerAppConsoleLogs","enabled":true}]'

# PostgreSQL metrics are available in the Azure Portal under Monitoring > Metrics
# Key metrics to watch: active connections, CPU %, storage used
```

Recommended alerts:

| Metric                         | Threshold       | Action                |
| ------------------------------ | --------------- | --------------------- |
| Backend `/api/health` failure  | 3 consecutive   | Email + Slack webhook |
| PostgreSQL CPU > 80%           | 5 min sustained | Scale up SKU          |
| PostgreSQL storage > 80%       | —               | Increase storage      |
| Container App replica restarts | > 3 in 10 min   | Investigate logs      |

### Updating the deployment

**Backend update:**

```bash
# Rebuild and push new image
az acr build \
  --registry "$ACR_NAME" \
  --image evals-backend:latest \
  ./backend -f ./backend/Dockerfile.prod

# Restart the container app to pull the new image
az containerapp revision restart \
  --name "$ACA_APP" \
  --resource-group "$RG"
```

**Frontend update:**

```bash
npm ci
npm run build
cp staticwebapp.config.json dist/
npx @azure/static-web-apps-cli deploy ./dist --deployment-token "$DEPLOY_TOKEN"
```

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
| `GEMINI_SERVICE_ACCOUNT_PATH`        | If used  | —                    | Path to Vertex AI service account JSON          |
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
