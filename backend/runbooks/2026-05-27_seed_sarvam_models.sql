-- Seed Sarvam AI models into the platform model catalog + pricing.
-- Run AFTER deploy in each environment (local + prod). Not part of Alembic and
-- NOT a seed_defaults edit: Sarvam is absent from models.dev, so its capability
-- catalog + rate card are hand-seeded here and a models.dev refresh never touches
-- them (provider 'sarvam' is intentionally outside the refresh allowlist).
--
-- Capability gating reads analytics.ref_llm_models_catalog: text in/out + tool_call
-- + reasoning are true; structured_output is FALSE (Sarvam has no response_format),
-- so structured call sites correctly never offer Sarvam.
--
-- Pricing is Sarvam's published INR/1M-token rate card converted to USD at
-- 85 INR/USD (2026-05-27). compute_cost treats *_per_1m_usd as USD, so the spend
-- plane stays USD-consistent. Re-run safe (idempotent upserts). sarvam-m is a
-- legacy model with no published LLM rate card -> 0, flagged in notes.

-- ── Model catalog (capabilities) ────────────────────────────────────────────
INSERT INTO analytics.ref_llm_models_catalog (
    id, provider_key, provider, model_id, model, display_name, family,
    context_limit, output_limit,
    supports_reasoning, supports_tool_call, supports_attachment, supports_structured_output,
    modalities_input, modalities_output, open_weights, status,
    first_seen_at, last_seen_at
) VALUES
    (gen_random_uuid(), 'sarvam', 'sarvam', 'sarvam-105b', 'sarvam-105b',
     'Sarvam 105B', 'sarvam', 128000, NULL,
     true, true, false, false,
     ARRAY['text']::text[], ARRAY['text']::text[], false, 'active',
     now(), now()),
    (gen_random_uuid(), 'sarvam', 'sarvam', 'sarvam-30b', 'sarvam-30b',
     'Sarvam 30B', 'sarvam', 64000, NULL,
     true, true, false, false,
     ARRAY['text']::text[], ARRAY['text']::text[], false, 'active',
     now(), now()),
    (gen_random_uuid(), 'sarvam', 'sarvam', 'sarvam-m', 'sarvam-m',
     'Sarvam M', 'sarvam', 8192, NULL,
     true, true, false, false,
     ARRAY['text']::text[], ARRAY['text']::text[], true, 'active',
     now(), now())
ON CONFLICT (provider, model) DO UPDATE SET
    provider_key = EXCLUDED.provider_key,
    model_id = EXCLUDED.model_id,
    display_name = EXCLUDED.display_name,
    family = EXCLUDED.family,
    context_limit = EXCLUDED.context_limit,
    output_limit = EXCLUDED.output_limit,
    supports_reasoning = EXCLUDED.supports_reasoning,
    supports_tool_call = EXCLUDED.supports_tool_call,
    supports_attachment = EXCLUDED.supports_attachment,
    supports_structured_output = EXCLUDED.supports_structured_output,
    modalities_input = EXCLUDED.modalities_input,
    modalities_output = EXCLUDED.modalities_output,
    open_weights = EXCLUDED.open_weights,
    status = 'active',
    last_seen_at = now();

-- ── Pricing (USD/1M tokens, converted from INR @ 85) ────────────────────────
INSERT INTO analytics.ref_llm_model_pricing (
    id, provider, model, effective_from, effective_to,
    input_per_1m_usd, cached_read_per_1m_usd, output_per_1m_usd,
    currency, source, source_model_id, notes
) VALUES
    (gen_random_uuid(), 'sarvam', 'sarvam-105b', TIMESTAMPTZ '2026-05-27 00:00:00+00', NULL,
     0.047059, 0.029412, 0.188235,
     'USD', 'manual', 'sarvam-105b',
     'Sarvam published rate card INR 4 in / 2.5 cached / 16 out per 1M; USD @ 85 INR/USD on 2026-05-27'),
    (gen_random_uuid(), 'sarvam', 'sarvam-30b', TIMESTAMPTZ '2026-05-27 00:00:00+00', NULL,
     0.029412, 0.017647, 0.117647,
     'USD', 'manual', 'sarvam-30b',
     'Sarvam published rate card INR 2.5 in / 1.5 cached / 10 out per 1M; USD @ 85 INR/USD on 2026-05-27'),
    (gen_random_uuid(), 'sarvam', 'sarvam-m', TIMESTAMPTZ '2026-05-27 00:00:00+00', NULL,
     0, 0, 0,
     'USD', 'manual', 'sarvam-m',
     'Legacy model — no published LLM rate card as of 2026-05-27; update when Sarvam publishes one')
ON CONFLICT (provider, model, effective_from) DO UPDATE SET
    effective_to = EXCLUDED.effective_to,
    input_per_1m_usd = EXCLUDED.input_per_1m_usd,
    cached_read_per_1m_usd = EXCLUDED.cached_read_per_1m_usd,
    output_per_1m_usd = EXCLUDED.output_per_1m_usd,
    currency = EXCLUDED.currency,
    source = EXCLUDED.source,
    source_model_id = EXCLUDED.source_model_id,
    notes = EXCLUDED.notes;
