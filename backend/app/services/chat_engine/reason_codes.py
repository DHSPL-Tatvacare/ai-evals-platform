"""Pack-scoped reason-code registries for Sherlock tool outcomes — Phase 2.

Rules (plan §6.2.1):

1. Only codes listed in ``HARNESS_SHARED_REASON_CODES`` may appear in more
   than one pack.
2. Every other pack-local frozenset MUST be pairwise disjoint.
3. Harness Core may emit only codes from ``HARNESS_SHARED_REASON_CODES``;
   all domain-specific codes belong to exactly one pack.
4. Phase 2's closure test asserts that every ``outcome.reason_code`` value
   emitted by pack code lives inside that pack's registered frozenset.

No free-form prose is allowed in ``reason_code``. Emit one of the stable
string literals below, or ``None`` when no deterministic code applies.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Harness-shared codes (plan §6.2.1, "Harness-owned shared set")
# ---------------------------------------------------------------------------

MALFORMED_ARGS = 'MALFORMED_ARGS'
TOOL_TIMEOUT = 'TOOL_TIMEOUT'
TOOL_UNAVAILABLE = 'TOOL_UNAVAILABLE'
PERMISSION_DENIED = 'PERMISSION_DENIED'
# Phase 7: emitted by ``capability_pack.submit_pack_job`` when the platform
# jobs pipeline refuses the submission (unknown job_type, missing metadata,
# etc.). Shared because any pack that uses ``submit_pack_job`` may surface it.
JOB_SUBMISSION_FAILED = 'JOB_SUBMISSION_FAILED'

HARNESS_SHARED_REASON_CODES: frozenset[str] = frozenset({
    MALFORMED_ARGS,
    TOOL_TIMEOUT,
    TOOL_UNAVAILABLE,
    PERMISSION_DENIED,
    JOB_SUBMISSION_FAILED,
})

# ---------------------------------------------------------------------------
# Analytics pack — chart gate outcomes (promoted from chart_contract.py)
# ---------------------------------------------------------------------------

CG_EMPTY = 'CG_EMPTY'
CG_SINGLE_VALUE = 'CG_SINGLE_VALUE'
CG_FIELD_CARD = 'CG_FIELD_CARD'
CG_NO_MEASURE = 'CG_NO_MEASURE'
CG_ALL_IDS = 'CG_ALL_IDS'
CG_DEGENERATE_MEASURE = 'CG_DEGENERATE_MEASURE'
CG_HIGH_CARD = 'CG_HIGH_CARD'
CG_EMIT_FAILED = 'CG_EMIT_FAILED'

ANALYTICS_CHART_REASON_CODES: frozenset[str] = frozenset({
    CG_EMPTY,
    CG_SINGLE_VALUE,
    CG_FIELD_CARD,
    CG_NO_MEASURE,
    CG_ALL_IDS,
    CG_DEGENERATE_MEASURE,
    CG_HIGH_CARD,
    CG_EMIT_FAILED,
})

# ---------------------------------------------------------------------------
# Analytics pack — inner SQL-agent outcomes (Phase 2 NEW; replace prose)
# ---------------------------------------------------------------------------

SQL_UNKNOWN_COLUMN = 'SQL_UNKNOWN_COLUMN'
SQL_UNKNOWN_TABLE = 'SQL_UNKNOWN_TABLE'
SQL_SECURITY_REJECTED = 'SQL_SECURITY_REJECTED'
SQL_VALIDATION_FAILED = 'SQL_VALIDATION_FAILED'
SQL_INVALID_OUTPUT_ALIAS_CONTRACT = 'SQL_INVALID_OUTPUT_ALIAS_CONTRACT'
SQL_EXECUTION_ERROR = 'SQL_EXECUTION_ERROR'

ANALYTICS_SQL_REASON_CODES: frozenset[str] = frozenset({
    SQL_UNKNOWN_COLUMN,
    SQL_UNKNOWN_TABLE,
    SQL_SECURITY_REJECTED,
    SQL_VALIDATION_FAILED,
    SQL_INVALID_OUTPUT_ALIAS_CONTRACT,
    SQL_EXECUTION_ERROR,
})

# ---------------------------------------------------------------------------
# Analytics pack — entity-resolution / discovery outcomes
# ---------------------------------------------------------------------------

ENTITY_AMBIGUOUS = 'ENTITY_AMBIGUOUS'
ENTITY_NOT_FOUND = 'ENTITY_NOT_FOUND'
ENTITY_OUT_OF_SCOPE = 'ENTITY_OUT_OF_SCOPE'
DISCOVER_CACHE_STALE = 'DISCOVER_CACHE_STALE'

ANALYTICS_ENTITY_REASON_CODES: frozenset[str] = frozenset({
    ENTITY_AMBIGUOUS,
    ENTITY_NOT_FOUND,
    ENTITY_OUT_OF_SCOPE,
    DISCOVER_CACHE_STALE,
})

# Aggregate: the full analytics-pack reason code set (plan §6.4)
ANALYTICS_REASON_CODES: frozenset[str] = (
    ANALYTICS_CHART_REASON_CODES
    | ANALYTICS_SQL_REASON_CODES
    | ANALYTICS_ENTITY_REASON_CODES
    | HARNESS_SHARED_REASON_CODES
)

# ---------------------------------------------------------------------------
# Report-builder pack
# ---------------------------------------------------------------------------

BLUEPRINT_INVALID_SCHEMA = 'BLUEPRINT_INVALID_SCHEMA'
BLUEPRINT_MISSING_REQUIRED_BLOCK = 'BLUEPRINT_MISSING_REQUIRED_BLOCK'
BLUEPRINT_UNKNOWN_BLOCK_TYPE = 'BLUEPRINT_UNKNOWN_BLOCK_TYPE'
BLUEPRINT_SAVE_CONFLICT = 'BLUEPRINT_SAVE_CONFLICT'

REPORT_BUILDER_BLUEPRINT_REASON_CODES: frozenset[str] = frozenset({
    BLUEPRINT_INVALID_SCHEMA,
    BLUEPRINT_MISSING_REQUIRED_BLOCK,
    BLUEPRINT_UNKNOWN_BLOCK_TYPE,
    BLUEPRINT_SAVE_CONFLICT,
})

REPORT_BUILDER_REASON_CODES: frozenset[str] = (
    REPORT_BUILDER_BLUEPRINT_REASON_CODES
    | HARNESS_SHARED_REASON_CODES
)

# ---------------------------------------------------------------------------
# Pack id -> pack-owned reason code set (registry for closure test)
# ---------------------------------------------------------------------------

PACK_REASON_CODES: dict[str, frozenset[str]] = {
    'analytics': ANALYTICS_REASON_CODES,
    'report_builder': REPORT_BUILDER_REASON_CODES,
}


def _assert_disjoint_pack_ownership() -> None:
    """Module-load guard: every non-shared pack code has exactly one owner.

    Runs once at import. Matches Phase 2's closure-test intent at module
    scope so accidental double-ownership blocks boot, not just CI.
    """
    items = list(PACK_REASON_CODES.items())
    for i, (pack_a, codes_a) in enumerate(items):
        local_a = codes_a - HARNESS_SHARED_REASON_CODES
        for pack_b, codes_b in items[i + 1:]:
            local_b = codes_b - HARNESS_SHARED_REASON_CODES
            overlap = local_a & local_b
            if overlap:
                raise RuntimeError(
                    f"reason-code ownership collision between '{pack_a}' "
                    f"and '{pack_b}': {sorted(overlap)} must live in only "
                    f"one pack (or in HARNESS_SHARED_REASON_CODES)."
                )


_assert_disjoint_pack_ownership()
