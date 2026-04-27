#!/bin/sh
# Strict mode: any non-zero exit aborts boot. Without this, a failing
# alembic upgrade or service-account decode would silently fall through
# to uvicorn and serve traffic with broken state.
set -e

# Decode Gemini service account from env var (base64-encoded JSON) if provided.
# This avoids mounting a JSON file on Azure App Service.
if [ -n "$GEMINI_SERVICE_ACCOUNT_JSON" ]; then
    echo "$GEMINI_SERVICE_ACCOUNT_JSON" | base64 -d > /app/service-account.json
    export GEMINI_SERVICE_ACCOUNT_PATH=/app/service-account.json
fi

# Apply pending Alembic migrations before serving traffic. Defaults to "true"
# so the image just works without per-environment env-var changes.
#
# When backend and worker boot together (e.g. rolling deploy on Azure),
# both run this; alembic takes a row lock on alembic_version, the second
# arrival waits, then no-ops if already at head. Wasted seconds, not a
# correctness issue.
#
# Set RUN_MIGRATIONS=false on non-leader containers (typically the worker)
# once the deploy environment supports per-container env vars, to keep
# boot cleanly serial.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[entrypoint] alembic upgrade head"
    alembic upgrade head
fi

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8721
