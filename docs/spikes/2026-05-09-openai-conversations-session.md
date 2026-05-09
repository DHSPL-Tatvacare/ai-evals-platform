# Sherlock v3 — `OpenAIConversationsSession` Phase-0 Spike

**Date opened:** 2026-05-09
**Owner:** pareekshith.bompally@tatvacare.in
**Spike harness:** `backend/scripts/spikes/conversations_session_spike.py`
**Reference:** `docs/specs/2026-04-26-sherlock-v3-architecture.md` §7
**Status:** OPEN — awaiting execution

---

## Why

The architecture spec D4 commits to `OpenAIConversationsSession` for Sherlock v3, but with a hard prerequisite: **prove it works for our deployment before P1 starts.** If any criterion fails, P1 falls back to the documented `previous_response_id` pattern (already in `openai_agents_adapter.py:560` and `report_builder/chat_handler.py:1430`) and the architecture spec's §11 wiring + §14 reconnect logic adjusts accordingly.

## Acceptance criteria — verbatim from §7

1. `OpenAIConversationsSession` instantiates against the configured Sherlock model using our existing API key + endpoint.
2. Multi-turn: 5 sequential `Runner.run` calls share state through the same `conversation_id`; the LLM remembers turn 1 in turn 5.
3. Token billing: input-token counts on turn N include cached-prefix discounts (verified via `usage` field).
4. Conversation object survives 24 h with no items written to it (no TTL).
5. Items persisted across worker process restarts (multi-worker safety check).

## How to run

```bash
cd backend
pyenv activate venv-python-ai-evals-arize

# Set the keys/model the spike will use. Match what production Sherlock will use.
export OPENAI_API_KEY=sk-...
export SHERLOCK_SUPERVISOR_MODEL=gpt-5.4-mini   # or whatever you intend to pin

# C1 + C2 + C3 — runs in ~2 min, costs roughly $0.05.
python scripts/spikes/conversations_session_spike.py quick

# C5 round-trip — seed then verify in two separate process invocations.
python scripts/spikes/conversations_session_spike.py c5-seed
# … exit, restart your shell or open a new terminal …
python scripts/spikes/conversations_session_spike.py c5-verify

# C4 — needs a 24h gap. Seed today, verify tomorrow.
python scripts/spikes/conversations_session_spike.py c4-seed
# … wait ≥24 h …
python scripts/spikes/conversations_session_spike.py c4-verify

# When done, drop the test conversations from your OpenAI org.
python scripts/spikes/conversations_session_spike.py cleanup
```

State persists at `/tmp/sherlock_v3_spike_state.json` between runs so C4/C5 can resume.

## Results

Paste the single-line `PASS / FAIL` summaries each subcommand prints. Add notes for anything surprising.

| # | Criterion | Result | Convo id | Notes |
|---|---|---|---|---|
| 1 | Instantiate + 1 turn |  |  |  |
| 2 | 5-turn recall |  |  |  |
| 3 | Cached-prefix discount visible |  |  | Cached tokens on turn 2/3: |
| 4 | 24h survival |  |  | Seeded at: <ts>; verified at: <ts>; age_h: |
| 5 | Cross-process resumption |  |  |  |

## Verdict

- [ ] **GO** — all 5 PASS. Architecture spec §11 wiring proceeds as written.
- [ ] **NO-GO** — at least one FAIL. P1 falls back to `previous_response_id`. Update §11 wiring + §14 reconnect to drop the Conversations API references.

## Decision

_Filled in after results land._

**Decided by:**
**Decided at:**
**P1 start date:**
