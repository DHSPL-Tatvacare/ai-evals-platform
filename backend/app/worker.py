"""Dedicated job worker entrypoint."""

import asyncio
import logging

from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.services.job_worker import (
    recover_stale_jobs,
    recover_stale_eval_runs,
    recovery_loop,
    worker_loop,
)

logger = logging.getLogger(__name__)
WORKER_SCHEMA_WAIT_TIMEOUT_SECONDS = 60
WORKER_SCHEMA_WAIT_INTERVAL_SECONDS = 1


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


async def _wait_for_worker_schema(
    timeout_seconds: int = WORKER_SCHEMA_WAIT_TIMEOUT_SECONDS,
    poll_interval_seconds: int = WORKER_SCHEMA_WAIT_INTERVAL_SECONDS,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    has_logged_wait = False

    while True:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT
                        to_regclass('public.jobs') IS NOT NULL AS jobs_ready,
                        to_regclass('public.eval_runs') IS NOT NULL AS eval_runs_ready
                    """
                )
            )
            jobs_ready, eval_runs_ready = result.one()

        if jobs_ready and eval_runs_ready:
            if has_logged_wait:
                logger.info("Worker schema detected; continuing startup")
            return

        if not has_logged_wait:
            logger.info("Waiting for backend schema bootstrap before starting worker recovery")
            has_logged_wait = True

        if asyncio.get_running_loop().time() >= deadline:
            missing_tables: list[str] = []
            if not jobs_ready:
                missing_tables.append("jobs")
            if not eval_runs_ready:
                missing_tables.append("eval_runs")
            raise RuntimeError(
                f"Worker startup timed out waiting for database schema: {', '.join(missing_tables)}"
            )

        await asyncio.sleep(poll_interval_seconds)


async def run_worker() -> None:
    """Run recovery once, then start the worker and recovery loops."""
    _validate_worker_config()
    logger.info("Starting dedicated job worker process")
    await _wait_for_worker_schema()
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
