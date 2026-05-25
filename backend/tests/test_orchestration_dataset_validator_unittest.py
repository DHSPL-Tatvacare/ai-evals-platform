"""Unit tests for dataset_validator.validate_communication_key.

Mirrors the existing validate_headers id_column check: empty key rejected,
key-not-in-columns rejected with a stable, header-naming detail.
"""
from __future__ import annotations

import pytest

from app.services.orchestration.datasets.dataset_validator import (
    DatasetImportError,
    validate_communication_key,
)


def test_communication_key_empty_rejected():
    with pytest.raises(DatasetImportError) as exc:
        validate_communication_key("", ["phone", "name"])
    assert "communication_key is required" in str(exc.value)


def test_communication_key_not_in_columns_rejected():
    with pytest.raises(DatasetImportError) as exc:
        validate_communication_key("email", ["phone", "name"])
    assert "not present in file header" in str(exc.value)


def test_communication_key_present_passes():
    validate_communication_key("phone", ["phone", "name"])
