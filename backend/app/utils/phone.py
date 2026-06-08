"""Phone E.164 normalization, shared across orchestration + CRM."""
from __future__ import annotations

import phonenumbers


def normalise_phone_e164(raw: str | None, default_region: str = "IN") -> str | None:
    """Return the E.164 form of ``raw`` or ``None`` if it cannot be validated.

    Empty strings, ``None``, and unparseable inputs all return ``None``.
    """
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
