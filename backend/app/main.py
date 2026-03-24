"""FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, text

from app.config import settings
from app.database import engine, get_db, async_session
from app.models import Base
from app.models.user import RefreshToken

logger = logging.getLogger(__name__)


def _validate_startup_config() -> None:
    """Fail fast if critical config is missing."""
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET environment variable is required. Set it in .env.backend.")


async def _cleanup_expired_refresh_tokens() -> None:
    """Delete expired refresh tokens. Called from recovery loop."""
    async with async_session() as db:
        result = await db.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(timezone.utc))
        )
        if result.rowcount:
            await db.commit()
            logger.info("Cleaned up %d expired refresh tokens", result.rowcount)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup, start background worker."""
    _validate_startup_config()

    async with engine.begin() as conn:
        # Drop orphaned cache table (replaced by lsq_lead_cache)
        await conn.execute(text("DROP TABLE IF EXISTS lsq_call_cache"))
        await conn.run_sync(Base.metadata.create_all)

        # Add source_type column to schemas table if missing
        await conn.execute(
            text("""
                ALTER TABLE schemas ADD COLUMN IF NOT EXISTS source_type VARCHAR(20)
            """)
        )

        # Drop legacy report_cache column (now in evaluation_analytics table)
        await conn.execute(
            text("""
                ALTER TABLE eval_runs DROP COLUMN IF EXISTS report_cache
            """)
        )

    # Seed system tenant/user + default prompts/schemas, then bootstrap admin
    from app.services.seed_defaults import seed_all_defaults, seed_bootstrap_admin
    async with async_session() as session:
        await seed_all_defaults(session)
    await seed_bootstrap_admin()

    # Clean up any expired refresh tokens from previous run
    await _cleanup_expired_refresh_tokens()

    # Recover any jobs stuck in "running" from a previous crash,
    # then reconcile any eval_runs orphaned by the same crash
    from app.services.job_worker import recover_stale_jobs, recover_stale_eval_runs, worker_loop, recovery_loop
    await recover_stale_jobs()
    await recover_stale_eval_runs()

    # Start background job worker and periodic recovery loop
    worker_task = asyncio.create_task(worker_loop())
    recovery_task = asyncio.create_task(recovery_loop())

    yield

    # Cleanup
    worker_task.cancel()
    recovery_task.cancel()
    await engine.dispose()


app = FastAPI(
    title="AI Evals Platform API",
    version="1.0.0",
    description="Backend API for AI evaluation pipelines.",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """Verify API and database connectivity."""
    try:
        async for db in get_db():
            await db.execute(text("SELECT 1"))
            return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}


# Register routers
from app.routes.listings import router as listings_router
from app.routes.files import router as files_router
from app.routes.prompts import router as prompts_router
from app.routes.schemas import router as schemas_router
from app.routes.evaluators import router as evaluators_router
from app.routes.chat import router as chat_router
from app.routes.history import router as history_router
from app.routes.settings import router as settings_router
from app.routes.tags import router as tags_router
from app.routes.jobs import router as jobs_router
from app.routes.eval_runs import router as eval_runs_router, threads_router
from app.routes.llm import router as llm_router
from app.routes.adversarial_config import router as adversarial_config_router
from app.routes.admin import router as admin_router
from app.routes.reports import router as reports_router
from app.routes.auth import router as auth_router
from app.routes.inside_sales import router as inside_sales_router
app.include_router(auth_router)
app.include_router(listings_router)
app.include_router(files_router)
app.include_router(prompts_router)
app.include_router(schemas_router)
app.include_router(evaluators_router)
app.include_router(chat_router)
app.include_router(history_router)
app.include_router(settings_router)
app.include_router(tags_router)
app.include_router(jobs_router)
app.include_router(eval_runs_router)
app.include_router(threads_router)
app.include_router(llm_router)
app.include_router(adversarial_config_router)
app.include_router(admin_router)
app.include_router(reports_router)
app.include_router(inside_sales_router)
