-- Seed LeadSquared as CRM ProviderConnection #1 (Leg 3, Phase 1, task 1.3).
-- Promotes the platform-wide env creds (LSQ_ACCESS_KEY / LSQ_SECRET_KEY / LSQ_BASE_URL)
-- into a per-tenant Fernet-encrypted orchestration.provider_connections row, so CRM creds
-- become a connection — not env vars. Behaviour change: env creds → per-tenant connection.
-- Run AFTER deploy in each environment that uses inside-sales. NOT seed_defaults (per-tenant
-- config never belongs in a platform-wide seed). Re-run safe (idempotent).
--
-- config_encrypted is a Fernet blob, which SQL cannot produce — generate it with the EXISTING
-- crypto helper (no creds are pasted; they are read from the container's own env), then pass it
-- in. In the backend container:
--
--   docker exec evals-backend python -c "import base64, os; \
--     from app.services.orchestration.connections.crypto import encrypt; \
--     print(base64.b64encode(encrypt({ \
--       'access_key':  os.environ['LSQ_ACCESS_KEY'], \
--       'secret_key':  os.environ['LSQ_SECRET_KEY'], \
--       'region_host': os.environ.get('LSQ_BASE_URL', 'https://api-in21.leadsquared.com/v2'), \
--     })).decode())"
--
-- Find the inputs (the tenant that already owns inside-sales data, and an admin user to own the row):
--   SELECT DISTINCT tenant_id FROM analytics.dim_lead WHERE app_id = 'inside-sales';
--   SELECT id FROM platform.users WHERE ... ;   -- an admin in that tenant
--
-- Then run (psql vars; nothing hardcoded here):
--   psql "$DSN" \
--     -v config_b64="<paste base64 blob>" \
--     -v tenant_id="<tenant uuid>" \
--     -v created_by="<admin user uuid>" \
--     -f backend/runbooks/2026-06-08_seed_lsq_connection.sql

-- 1) The connection (idempotent on the scope+provider+name unique constraint).
INSERT INTO orchestration.provider_connections (
    id, tenant_id, app_id, provider, name,
    config_encrypted, visibility, active, created_by
) VALUES (
    gen_random_uuid(), :'tenant_id'::uuid, 'inside-sales', 'lsq', 'LeadSquared',
    decode(:'config_b64', 'base64'), 'PRIVATE', true, :'created_by'::uuid
)
ON CONFLICT ON CONSTRAINT uq_provider_connections_scope_provider_name DO NOTHING;

-- 2) Surface the CRM experience for the app (App.config flag; the mapping itself lives in
--    platform.crm_field_map, never in App.config).
UPDATE platform.applications
SET config = coalesce(config, '{}'::jsonb) || '{"hasCrm": true}'::jsonb
WHERE slug = 'inside-sales';
