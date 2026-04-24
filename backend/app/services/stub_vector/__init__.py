"""Stub vector-like capability pack (Phase 1 / M3 extensibility proof).

A deterministic, read-only, in-memory "vector-like" pack used to prove
that Sherlock's scoped-bundle layer genuinely composes new packs through
auto-discovery + ``App.config.chat.capabilities`` alone — no Harness
Core / Bundle / ScopeGuard edits required (plan §9, §10 M3).

This pack is intentionally trivial: no embeddings pipeline, no vector
DB, no background indexing, no external service. Think of it as the
shape a real vector / RAG / KG / clinical pack will take once it lands.
"""
