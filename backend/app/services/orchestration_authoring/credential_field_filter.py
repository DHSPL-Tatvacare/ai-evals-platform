"""Phase 3 — canonical credential field blocklist + recursive walker.

Decision §R5 forbids any tool result whose serialized JSON contains a
credential-shaped field. This module is the **single** owner of that
blocklist; other modules import from here. Adding a name here is the
only way the egress filter learns about a new credential field.

Two egress points use this module today:
  - `lookup_models.contains_credential_fields` (legacy nullable-return
    shim, retained so existing per-handler call sites inside the pack
    keep working without the refactor sprawl).
  - `orchestration_authoring_pack.build_outcome` (Phase 3 Step 4 —
    raises CredentialLeakError directly so the harness path can never
    leak a payload).
"""
from __future__ import annotations

from typing import Any, Sequence


# Decision §R5 — these are the field names that, at any nesting depth,
# constitute a credential leak. Match is case-insensitive on dict keys.
FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset({
    'api_key',
    'secret',
    'access_token',
    'config_encrypted',
    'password',
    'bearer',
    'webhook_token',
    'bolna_api_key',
    'wati_api_key',
})


class CredentialLeakError(Exception):
    """Raised by `assert_no_credentials` when a forbidden field is found.

    Carries the offending field name AND the full path through the
    payload so log lines can pinpoint where the leak originated. The
    message is human-readable but never surfaced to the chat — handlers
    map the exception onto the generic
    `reason_code='CREDENTIAL_LEAK_BLOCKED'` envelope instead.
    """

    def __init__(self, field_name: str, path: Sequence[str | int]) -> None:
        self.field_name = field_name
        self.path = list(path)
        path_str = '.'.join(str(p) for p in self.path) if self.path else '<root>'
        super().__init__(
            f'credential field {field_name!r} found at path {path_str}',
        )


def assert_no_credentials(
    payload: Any,
    *,
    _path: tuple[str | int, ...] = (),
) -> None:
    """Recursively walk ``payload`` raising on the FIRST forbidden field.

    Walks dicts via ``.items()`` and lists via ``enumerate``. Primitive
    values are skipped. Match against `FORBIDDEN_FIELD_NAMES` is
    case-insensitive on dict keys; list entries are walked but never
    matched as keys.

    Returns ``None`` on success. Raises `CredentialLeakError(field, path)`
    on the first hit.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and key.lower() in FORBIDDEN_FIELD_NAMES:
                raise CredentialLeakError(key, _path + (key,))
            assert_no_credentials(value, _path=_path + (str(key),))
        return
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            assert_no_credentials(item, _path=_path + (index,))
        return
    # Primitive — nothing to walk.
    return


__all__ = [
    'FORBIDDEN_FIELD_NAMES',
    'CredentialLeakError',
    'assert_no_credentials',
]
