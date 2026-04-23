"""Pack-owned reason codes for the contract-stub pack.

Rules (plan §6.2.1):
- pack-local codes MUST be disjoint from any other pack's non-shared codes
- codes are stable string literals; no free-form prose
- the closure test in ``chat_engine.reason_codes`` enforces disjointness at
  import time once the pack is registered in ``PACK_REASON_CODES``.
"""
from __future__ import annotations


CONTRACT_STUB_EMPTY_TEXT = 'CONTRACT_STUB_EMPTY_TEXT'
CONTRACT_STUB_TEXT_TOO_LONG = 'CONTRACT_STUB_TEXT_TOO_LONG'
CONTRACT_STUB_UNKNOWN_VARIANT = 'CONTRACT_STUB_UNKNOWN_VARIANT'


CONTRACT_STUB_PACK_REASON_CODES: frozenset[str] = frozenset({
    CONTRACT_STUB_EMPTY_TEXT,
    CONTRACT_STUB_TEXT_TOO_LONG,
    CONTRACT_STUB_UNKNOWN_VARIANT,
})
