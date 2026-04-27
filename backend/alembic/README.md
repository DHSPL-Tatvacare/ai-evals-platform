# Alembic

Schema migrations for ai-evals-platform. Authoritative source of truth
for the database structure on every environment.

## Layout

```
backend/
├── alembic.ini              # config; sqlalchemy.url is intentionally blank
└── alembic/
    ├── env.py               # async env; reads DATABASE_URL from app.config.settings
    ├── script.py.mako       # template for new revisions
    ├── versions/            # revision files (none yet — added in Phase 2+)
    ├── baseline/            # Phase 0 audit + the prod schema snapshot
    │   ├── prod_schema_snapshot.sql
    │   ├── diff_*.sql
    │   ├── drift_report.md
    │   ├── drift_accepted.md
    │   └── follow_up_migrations.md
    └── README.md            # this file
```

## Day-to-day

All commands run from the `backend/` directory.

| Goal | Command |
|---|---|
| Show current revision in the connected DB | `alembic current` |
| Show full revision history | `alembic history --verbose` |
| Apply all pending migrations | `alembic upgrade head` |
| Roll back one revision | `alembic downgrade -1` |
| Generate a new migration draft from model changes | `alembic revision --autogenerate -m "<short message>"` |
| Generate an empty migration | `alembic revision -m "<short message>"` |
| Print the SQL a migration would emit (without running it) | `alembic upgrade head --sql` |

`DATABASE_URL` must be exported (or in `.env`) for any command that connects.

## Adding a schema change

1. Edit the model under `backend/app/models/`.
2. From `backend/`, run `alembic revision --autogenerate -m "<message>"`.
3. **Review the generated file by hand.** Autogenerate misses partial-index
   predicates, expression indexes, COMMENT ON COLUMN, and a few other things.
   Compare against `baseline/drift_accepted.md` for the patterns we expect
   autogenerate to skip.
4. Run `alembic upgrade head` against your local DB. Verify behavior.
5. Commit the model change AND the migration in the same commit.

## Adoption history

The Alembic adoption shipped in eight phases per
`docs/plans/2026-04-24-implementation-sequence/phase-01-db-and-alembic-migration/11-execution-phases.md`.
All phases are live on prod as of 2026-04-27. `bootstrap_database_schema`
and the legacy `backend/app/startup_schema.py` no longer exist. Schema
state is owned exclusively by `alembic_version` and the files in
`versions/`.

## Drift protection — manual, not CI

Phase 7 (a GitHub Actions workflow that runs `alembic check` on every PR
and fails on drift) was **not shipped** because the deploy pipeline is
not currently editable from this repo's contributors. That gap means a
developer can change a model file without a matching migration and
ship it; the drift will land on prod and become visible only when
something at request time hits the missing column or constraint.

**Manual mitigation:** before pushing any commit that touches a model
under `backend/app/models/`, run:

```bash
cd backend && alembic revision --autogenerate -m _drift_check_ \
  && rm versions/*_drift_check_.py
```

If autogenerate emits any operations, write the real migration. If it
emits nothing, you're clean.

Restore Phase 7 (`docs/plans/.../11-execution-phases.md` §7) when the
deploy pipeline opens up — the migration files are CI-ready.

Phase 1 is safe to deploy. The behavior change starts in Phase 5.
