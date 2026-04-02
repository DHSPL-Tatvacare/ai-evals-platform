"""Helpers for explicit narrative contracts."""

from __future__ import annotations

from typing import TypeVar

from app.schemas.base import CamelModel

TContract = TypeVar('TContract', bound=CamelModel)


def contract_json_schema(model_cls: type[TContract]) -> dict:
    return model_cls.model_json_schema(by_alias=True)


def validate_contract_payload(
    model_cls: type[TContract],
    payload: dict,
) -> TContract:
    return model_cls.model_validate(payload)
