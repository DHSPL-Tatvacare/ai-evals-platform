"""Tenant LLM provider env fallbacks must be gone; system SA survivor stays.

Phase 2 (2026-05-18) added Sherlock model env vars to the REMOVED list. Those
were never defined in ``Settings`` to begin with (the supervisor/specialist
helpers read ``os.getenv`` directly), so the assertion here is defensive — it
catches any attempt to bring them back as ``Settings`` fields.
"""
REMOVED = [
    "GEMINI_API_KEY", "GEMINI_AUTH_METHOD", "GEMINI_MODEL", "OPENAI_API_KEY",
    "OPENAI_MODEL", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_MODEL", "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL", "DEFAULT_LLM_PROVIDER", "EVAL_TEMPERATURE",
    "SHERLOCK_SUPERVISOR_MODEL", "SHERLOCK_SPECIALIST_MODEL",
]
KEPT = ["GEMINI_SERVICE_ACCOUNT_PATH", "LLM_CREDENTIAL_KEY", "ORCHESTRATION_CONNECTION_KEY"]


def test_removed_vars_absent():
    from app.config import Settings
    fields = set(Settings.model_fields.keys())
    for name in REMOVED:
        assert name not in fields, f"{name} should have been removed"


def test_kept_vars_present():
    from app.config import Settings
    fields = set(Settings.model_fields.keys())
    for name in KEPT:
        assert name in fields, f"{name} must remain"
