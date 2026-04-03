#!/bin/sh
# Decode Gemini service account from env var (base64-encoded JSON) if provided.
# This avoids mounting a JSON file on Azure App Service.
if [ -n "$GEMINI_SERVICE_ACCOUNT_JSON" ]; then
    echo "$GEMINI_SERVICE_ACCOUNT_JSON" | base64 -d > /app/service-account.json
    export GEMINI_SERVICE_ACCOUNT_PATH=/app/service-account.json
fi

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8721
