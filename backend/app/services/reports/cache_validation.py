"""Shared validation helpers for cached report payloads."""

from __future__ import annotations

from collections.abc import Callable
import logging

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.base import CamelModel

logger = logging.getLogger(__name__)


def load_cached_payload_or_raise(
    loader: Callable[[dict], CamelModel],
    cached_data: dict,
    *,
    detail: str,
    log_message: str,
) -> CamelModel:
    try:
        return loader(cached_data)
    except ValidationError as exc:
        logger.warning(log_message)
        raise HTTPException(status_code=409, detail=detail) from exc


def partition_valid_single_run_payloads(
    runs_data: list[tuple[dict, dict]],
    payload_model: type[CamelModel],
) -> tuple[list[tuple[dict, dict]], int]:
    valid_runs_data: list[tuple[dict, dict]] = []
    invalid_count = 0

    for meta, data in runs_data:
        try:
            payload = payload_model.model_validate(data)
        except ValidationError:
            invalid_count += 1
            logger.warning(
                'Skipping outdated single-run report cache for run %s during cross-run refresh',
                meta.get('id', 'unknown'),
            )
            continue
        valid_runs_data.append((meta, payload.model_dump(by_alias=True)))

    return valid_runs_data, invalid_count
