"""Phone E.164 normalization — shared util (moved from recipient_freezer)."""
from app.utils.phone import normalise_phone_e164


def test_normalise_phone_accepts_indian_local():
    assert normalise_phone_e164("9876543210", default_region="IN") == "+919876543210"


def test_normalise_phone_accepts_e164():
    assert normalise_phone_e164("+91 98765 43210") == "+919876543210"


def test_normalise_phone_returns_none_on_garbage():
    assert normalise_phone_e164("not-a-phone") is None


def test_normalise_phone_returns_none_on_empty():
    assert normalise_phone_e164("") is None
    assert normalise_phone_e164(None) is None


def test_normalise_phone_returns_none_on_invalid_e164():
    assert normalise_phone_e164("+1234") is None
