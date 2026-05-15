"""Orchestration authoring capability pack — Sherlock-on-Builder Phase 1.

Owner of the `orchestration.authoring` pack: tool_specs, tool_handlers,
artifact contracts, reason codes. The v3 `authoring_specialist` agent
imports from this module to construct its FunctionTool list (one source
of truth, two consumers).

See:
  - docs/plans/sherlock-future-plan.md (capability-pack rail)
  - Designs/sherlock-builder-implementation-plan.md (Phase 1)
  - Decisions/2026-05-10-tenant-app-permission-rules.md (R1–R10)
"""
