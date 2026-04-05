"""Dedicated job worker entrypoint."""

import asyncio
import logging

from app.config import settings
from app.database import engine
from app.startup_schema import bootstrap_database_schema
from app.services.job_worker import (
    recover_stale_jobs,
    recover_stale_eval_runs,
    recovery_loop,
    worker_loop,
)

logger = logging.getLogger(__name__)


def _validate_worker_config() -> None:
    if settings.JOB_HEARTBEAT_INTERVAL_SECONDS >= settings.JOB_LEASE_SECONDS:
        raise RuntimeError("JOB_HEARTBEAT_INTERVAL_SECONDS must be less than JOB_LEASE_SECONDS.")
    if settings.JOB_MAX_ATTEMPTS < 1:
        raise RuntimeError("JOB_MAX_ATTEMPTS must be at least 1.")
    if settings.JOB_RETRY_BASE_DELAY_SECONDS < 1:
        raise RuntimeError("JOB_RETRY_BASE_DELAY_SECONDS must be at least 1.")
    if settings.JOB_RETRY_MAX_DELAY_SECONDS < settings.JOB_RETRY_BASE_DELAY_SECONDS:
        raise RuntimeError("JOB_RETRY_MAX_DELAY_SECONDS must be greater than or equal to JOB_RETRY_BASE_DELAY_SECONDS.")
    if settings.JOB_TENANT_MAX_CONCURRENT < 1:
        raise RuntimeError("JOB_TENANT_MAX_CONCURRENT must be at least 1.")
    if settings.JOB_APP_MAX_CONCURRENT < 1:
        raise RuntimeError("JOB_APP_MAX_CONCURRENT must be at least 1.")
    if settings.JOB_USER_MAX_CONCURRENT < 1:
        raise RuntimeError("JOB_USER_MAX_CONCURRENT must be at least 1.")

async def run_worker() -> None:
    """Run recovery once, then start the worker and recovery loops."""
    _validate_worker_config()
    logger.info("Starting dedicated job worker process")
    await bootstrap_database_schema()
    await recover_stale_jobs()
    await recover_stale_eval_runs()

    worker_task = asyncio.create_task(worker_loop())
    recovery_task = asyncio.create_task(recovery_loop())

    try:
        await asyncio.gather(worker_task, recovery_task)
    finally:
        worker_task.cancel()
        recovery_task.cancel()
        await asyncio.gather(worker_task, recovery_task, return_exceptions=True)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_worker())
