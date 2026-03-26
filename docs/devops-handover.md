# DevOps Handover — AI Evals Platform

**Date:** 2026-03-26
**Prepared by:** Engineering (PM)
**For:** DevOps / Cloud Engineer

---

## What This App Is

A multi-tenant AI evaluation platform used internally at TatvaCare. It evaluates LLM-based products (voice bots, chat agents, inside sales AI) against real call/conversation data.

Three services run together:

| Service | Role | Port |
|---|---|---|
| `frontend` | React SPA (nginx) | 80 |
| `backend` | FastAPI + job workers | 8721 |
| `postgres` | **Not in prod container** — use Azure PostgreSQL | — |

---

## Azure Services to Provision

Provision these before first deploy. All in the same resource group.

| Service | Azure Product | Recommended Tier | Notes |
|---|---|---|---|
| Container registry | Azure Container Registry (ACR) | Basic | Stores Docker images |
| App hosting | Azure App Service (Linux, Containers) | B2 or P1v3 | Multi-container via Docker Compose |
| Database | Azure Database for PostgreSQL – Flexible Server | Burstable B2ms | Enable SSL. Create DB: `ai_evals_platform` |
| File storage | Azure Blob Storage | Standard LRS | Create container: `evals-files` |
| Secrets | Azure Key Vault | Standard | Store all secrets listed below |

---

## Repository Structure (prod-relevant files)

```
Dockerfile.frontend.prod        ← builds React, serves via nginx
nginx.prod.conf                 ← nginx config (SPA + /api proxy)
backend/Dockerfile.prod         ← Python backend, production uvicorn
backend/entrypoint.sh           ← decodes Gemini service account at startup
docker-compose.prod.yml         ← the compose file App Service runs
.github/workflows/deploy.yml    ← CI/CD pipeline
```

The dev files (`Dockerfile.frontend`, `backend/Dockerfile`, `docker-compose.yml`) are unchanged and still used locally.

---

## CI/CD Pipeline

**Trigger:** Push a git tag matching `v*.*.*`

```bash
# How the PM triggers a production deploy:
git tag v1.2.0
git push origin v1.2.0
```

**What happens automatically:**
1. GitHub Actions builds `evals-backend` and `evals-frontend` Docker images
2. Images are pushed to ACR tagged as both `v1.2.0` and `latest`
3. `docker-compose.prod.yml` is deployed to Azure App Service

**GitHub repository secrets to configure** (Settings → Secrets and variables → Actions):

| Secret name | How to get it |
|---|---|
| `AZURE_CREDENTIALS` | `az ad sp create-for-rbac --name evals-deploy --role contributor --scopes /subscriptions/<sub>/resourceGroups/<rg> --sdk-auth` |
| `ACR_LOGIN_SERVER` | ACR resource → Login server (e.g. `myacr.azurecr.io`) |
| `ACR_USERNAME` | ACR resource → Access keys → Username |
| `ACR_PASSWORD` | ACR resource → Access keys → Password |
| `AZURE_RESOURCE_GROUP` | Your resource group name |
| `AZURE_WEBAPP_NAME` | Your App Service name |

---

## Environment Variables

Set all of these in **Azure App Service → Configuration → Application settings** (or Key Vault with App Service references). Never commit real values to git.

### Required — will crash on startup if missing

| Variable | Example / Notes |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host.postgres.database.azure.com:5432/ai_evals_platform?ssl=require` |
| `JWT_SECRET` | Generate with: `openssl rand -hex 32` |
| `ADMIN_EMAIL` | First admin user email (used only on first startup) |
| `ADMIN_PASSWORD` | First admin user password |
| `ADMIN_TENANT_NAME` | e.g. `Tatvacare` |
| `CORS_ORIGINS` | Public URL of the app, e.g. `https://evals.tatvacare.in` |
| `APP_BASE_URL` | Same as `CORS_ORIGINS` (used in invite link emails) |

### Required — Azure infrastructure

| Variable | Example / Notes |
|---|---|
| `AZURE_STORAGE_CONNECTION_STRING` | Blob Storage → Access keys → Connection string |
| `AZURE_STORAGE_CONTAINER` | `evals-files` (create this container in the storage account) |
| `ACR_LOGIN_SERVER` | e.g. `myacr.azurecr.io` (also used in compose file) |
| `IMAGE_TAG` | Set to `latest` in App Service config; GitHub Actions overrides per deploy |

### Required — Gemini / Vertex AI

The app uses a Google Cloud service account for Gemini on Vertex AI.
The service account JSON file **cannot be mounted as a file on App Service** — instead it is base64-encoded and passed as an env var. The entrypoint script decodes it at container startup.

| Variable | Notes |
|---|---|
| `GEMINI_AUTH_METHOD` | `service_account` |
| `GEMINI_SERVICE_ACCOUNT_JSON` | Base64-encoded content of `service-account.json`. Encode with: `base64 -i service-account.json` (macOS) or `base64 -w 0 service-account.json` (Linux) |
| `GEMINI_MODEL` | e.g. `gemini-2.5-pro` (can be left blank; users configure per-session) |

### Optional — other LLM providers (set only what you use)

| Variable | Notes |
|---|---|
| `OPENAI_API_KEY` | |
| `OPENAI_MODEL` | |
| `AZURE_OPENAI_API_KEY` | |
| `AZURE_OPENAI_ENDPOINT` | |
| `AZURE_OPENAI_API_VERSION` | Default: `2025-03-01-preview` |
| `AZURE_OPENAI_MODEL` | |
| `ANTHROPIC_API_KEY` | |
| `ANTHROPIC_MODEL` | |
| `DEFAULT_LLM_PROVIDER` | Default: `gemini` |
| `EVAL_TEMPERATURE` | Default: `0.1` |

### Optional — integrations

| Variable | Notes |
|---|---|
| `LSQ_BASE_URL` | LeadSquared API base URL (Inside Sales feature) |
| `LSQ_ACCESS_KEY` | LeadSquared access key |
| `LSQ_SECRET_KEY` | LeadSquared secret key |
| `KAIRA_API_URL` | Kaira adversarial testing API |
| `KAIRA_AUTH_TOKEN` | |
| `KAIRA_TEST_USER_ID` | |
| `ADMIN_TENANT_ALLOWED_DOMAINS` | Comma-separated, e.g. `@tatvacare.in,@tatva.com` |

---

## First-Time Setup Steps

1. **Provision Azure resources** (see table above)
2. **Create the Blob container** named `evals-files` in your storage account (set access to Private)
3. **Create the PostgreSQL database** named `ai_evals_platform` — the app creates all tables automatically on first startup
4. **Set all App Service environment variables** (Application settings)
5. **Configure GitHub Actions secrets** (see CI/CD section)
6. **Grant ACR pull permission to App Service:**
   ```bash
   az webapp config appsettings set \
     --resource-group <rg> --name <app-name> \
     --settings DOCKER_REGISTRY_SERVER_URL=https://<acr>.azurecr.io \
                DOCKER_REGISTRY_SERVER_USERNAME=<acr-username> \
                DOCKER_REGISTRY_SERVER_PASSWORD=<acr-password>
   ```
7. **Tag and push to trigger first deploy:**
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
8. **Verify** — `https://<app-url>/api/health` should return `{"status": "ok", "database": "connected"}`
9. **First login** — use `ADMIN_EMAIL` / `ADMIN_PASSWORD`. These only take effect if no users exist in the DB. After first login, rotate `ADMIN_PASSWORD`.

---

## App URL / Domain Setup

**Start with Azure's free subdomain — no DNS work needed:**
```
https://evals-app.azurewebsites.net
```
Set these two env vars to match before first deploy:
```
CORS_ORIGINS=https://evals-app.azurewebsites.net
APP_BASE_URL=https://evals-app.azurewebsites.net
```
`APP_BASE_URL` is prepended to every invite link the app generates. If it's wrong, invite links will point nowhere.

**Switching to a custom domain later (e.g. evals.tatvacare.in):**
1. Add a CNAME record in DNS: `evals.tatvacare.in` → `evals-app.azurewebsites.net`
2. Bind the custom domain in App Service → Custom domains
3. Update two env vars (no redeploy needed — container restarts automatically):
   ```
   CORS_ORIGINS=https://evals.tatvacare.in
   APP_BASE_URL=https://evals.tatvacare.in
   ```

**How to change any env var after deployment:**
- Portal: App Service → Configuration → Application settings → edit → Save
- CLI: `az webapp config appsettings set --resource-group <rg> --name <app-name> --settings KEY=value`

---

## Post-First-Login Checklist (PM to do, ~10 minutes)

After the app is live and you log in as admin for the first time:

- [ ] **Seed evaluators** for each app — the app auto-seeds prompts and schemas but NOT evaluators. Call these once:
  - `POST /api/evaluators/seed-defaults?appId=voice-rx`
  - `POST /api/evaluators/seed-defaults?appId=kaira-bot`
  - `POST /api/evaluators/seed-defaults?appId=inside-sales`
  - Easiest via the app's admin panel if it surfaces this, or via curl/Postman with your Bearer token.
- [ ] **Create roles** before inviting users — custom roles start with zero permissions and zero app access. Configure them first.
- [ ] **Create invite links** for your first users — there is no open signup. Every user needs an invite link generated by the admin.
- [ ] **Rotate admin password** — change the `ADMIN_PASSWORD` you gave DevOps via the profile/admin settings in the app.

---

## Ongoing Operations

**Deploy a new version:**
```bash
git tag v1.2.3
git push origin v1.2.3
```
GitHub Actions handles everything. Takes ~5-8 minutes.

**View logs:**
- App Service → Log stream (live)
- App Service → Diagnose and solve problems → Application logs

**Database access:**
- Use Azure Data Studio or psql with the Azure PostgreSQL connection string
- SSL is required: append `?ssl=require` to the connection string

**Scale up:**
- App Service → Scale up (App Service plan) — upgrade tier for more CPU/RAM
- App Service → Scale out — add instances for horizontal scale

---

## Network / Security Notes

- App Service should have **HTTPS only** enabled (App Service → TLS/SSL settings)
- If the app is internal-only, restrict access via App Service → Networking → Access restrictions (allow only your corporate IP range)
- PostgreSQL should have its firewall set to allow **only the App Service outbound IPs** (App Service → Properties → Outbound IP addresses)
- Blob Storage should remain **private** — the backend accesses it via connection string, never via public URLs
- All secrets should be stored in **Key Vault** and referenced via App Service Key Vault references rather than pasted directly into Application settings

---

## Questions

Contact the PM / engineering lead before changing:
- The `DATABASE_URL` format (the app uses `asyncpg` driver, not `psycopg2`)
- `FILE_STORAGE_TYPE` — only `local` and `azure_blob` are supported
- `GEMINI_AUTH_METHOD` — only `api_key` and `service_account` are supported
