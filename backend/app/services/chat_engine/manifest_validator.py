"""Cross-check manifests against live Postgres. Run at every backend/worker boot.

Refuses startup if any manifest declares a table or column that doesn't
actually exist in its effective schema. This is the one place drift between
the manifest (logical truth) and Postgres (physical truth) gets caught.

Roadmap 01 §9.6: each ``CatalogTable`` carries an ``effective_schema``
(``public`` until tables move). The validator queries ``information_schema``
per-table using that schema rather than a hard-coded ``'public'``.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_engine.manifest import AppManifest, load_all_manifests

logger = logging.getLogger(__name__)


class ManifestDriftError(RuntimeError):
    """Raised when a manifest contradicts live Postgres. Boot should abort."""


def validate_manifest_taxonomy(manifest: AppManifest, strict: bool = False) -> list[str]:
    """Return warnings for chart-contract taxonomy drift.

    - measure columns without ``semantic_type`` → warning.
    - role/``data_type`` contradictions (measure must be quantitative, temporal
      must be temporal) → error, raised in strict mode, appended in loose mode.
    """
    warnings: list[str] = []
    errors: list[str] = []
    for table_name, table in manifest.catalog_tables.items():
        for col_name, col in table.columns.items():
            qualified = f"{manifest.app_id}:{table_name}.{col_name}"
            if col.role == "measure" and col.semantic_type is None:
                warnings.append(f"{qualified}: measure missing semantic_type")
            if col.role == "measure" and col.data_type not in (None, "quantitative"):
                errors.append(
                    f"{qualified}: role=measure requires data_type=quantitative, "
                    f"got {col.data_type!r}"
                )
            if col.role == "temporal" and col.data_type not in (None, "temporal"):
                errors.append(
                    f"{qualified}: role=temporal requires data_type=temporal, "
                    f"got {col.data_type!r}"
                )
    if strict and errors:
        raise ValueError("; ".join(errors))
    return warnings + errors


async def _db_columns_for(
    db: AsyncSession, schema_name: str, table_name: str
) -> dict[str, str]:
    result = await db.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :t"
        ),
        {"schema": schema_name, "t": table_name},
    )
    return {row.column_name: row.data_type for row in result}


async def validate_manifest_against_postgres(
    manifest: AppManifest, db: AsyncSession
) -> None:
    """Validate every catalog table in the manifest against live Postgres.

    Each table is checked against its declared ``effective_schema``.
    Manifests that omit ``pg_schema`` resolve to ``DEFAULT_SCHEMA``
    (``public``) — Phase 1 behavior, identical to before.

    Phase 1 policy: a manifest entry whose declared physical reference
    cannot be resolved is fatal (boot blocks). Unqualified column refs
    *within manifest text* are not currently parsed here; that responsibility
    is Sherlock's during SQL validation. ``warnings`` are emitted (not
    raised) so callers can collect them without aborting boot when the
    drift is informational.
    """
    drift: list[str] = []
    warnings_out: list[str] = []
    for table_name, table in manifest.catalog_tables.items():
        schema_name = table.effective_schema
        if table.pg_schema is None:
            # Phase 1: unqualified manifests are expected. Warn so the
            # signal is visible in logs but never block boot.
            warnings_out.append(
                f"[{manifest.app_id}] table {table_name!r} has no pg_schema declared; "
                f"defaulting to {schema_name!r}"
            )
        db_cols = await _db_columns_for(db, schema_name, table_name)
        if not db_cols:
            drift.append(
                f"[{manifest.app_id}] table {schema_name}.{table_name!r} does not exist"
            )
            continue
        for col_name in table.columns:
            if col_name not in db_cols:
                drift.append(
                    f"[{manifest.app_id}] {schema_name}.{table_name}.{col_name!r} "
                    f"declared in manifest but not in information_schema.columns"
                )
    if warnings_out:
        for msg in warnings_out:
            logger.warning(msg)
    if drift:
        raise ManifestDriftError(
            f"Manifest drift detected ({len(drift)} issue(s)):\n  - "
            + "\n  - ".join(drift)
        )


async def run_manifest_validator(db: AsyncSession) -> None:
    """Validate every registered manifest.

    Raises ``ManifestDriftError`` on physical drift (boot-blocking) and
    ``ValueError`` on strict taxonomy violations. Loose taxonomy issues
    (missing ``semantic_type`` on measures) are logged as warnings.
    """
    manifests = load_all_manifests()
    for manifest in manifests.values():
        await validate_manifest_against_postgres(manifest, db)
        # strict=True raises on role/data_type contradictions; warnings
        # (e.g. missing semantic_type) are collected and logged non-fatally.
        taxonomy_issues = validate_manifest_taxonomy(manifest, strict=True)
        if taxonomy_issues:
            logger.warning(
                "Manifest %s: %d taxonomy warning(s): %s",
                manifest.app_id,
                len(taxonomy_issues),
                "; ".join(taxonomy_issues),
            )
        else:
            logger.info("Manifest %s: taxonomy validation OK", manifest.app_id)
