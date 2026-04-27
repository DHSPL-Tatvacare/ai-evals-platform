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

## Phase status (during Alembic adoption)

This directory is being introduced incrementally per
`docs/plans/2026-04-24-implementation-sequence/phase-01-db-and-alembic-migration/11-execution-phases.md`.

- **Phase 0 (done):** drift audit, prod snapshot, model reconciliation. See `baseline/`.
- **Phase 1 (this commit):** scaffold only — `env.py`, `alembic.ini`, empty `versions/`. No migrations exist; `alembic current` returns nothing.
- **Phase 2:** add `versions/0001_baseline_prod.py` and stamp prod once.
- **Phase 3:** add catch-up migrations 0002, 0003 (planned in `baseline/follow_up_migrations.md`).
- **Phase 5:** wire `alembic upgrade head` into the boot path (`entrypoint.sh`).
- **Phase 6:** remove `bootstrap_database_schema()` from the FastAPI lifespan.
- **Phase 8:** delete `backend/app/startup_schema.py`.

Until Phase 5 lands, **nothing in the running app calls Alembic.** Schema is
still owned by `startup_schema.py`. This directory is inert scaffolding.

## Why this scaffold doesn't break prod

- `alembic.ini` and `env.py` are inert files. Nothing imports them at app boot.
- No revisions exist in `versions/`. `alembic upgrade head` (if run) would no-op.
- The model edits in Phase 0 are no-ops at runtime because `Base.metadata.create_all(checkfirst=True)` skips existing tables.

Phase 1 is safe to deploy. The behavior change starts in Phase 5.
