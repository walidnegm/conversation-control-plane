# Control Plane SDK — Multi-Worker Scale Smoke (procedure)

Status: Living (2026-07-06) — enterprise unknowns (SDK §0.7, §15)  
**Artifact type:** runbook + regression pins — not a load-test framework.

---

## What we need to prove

Under multiple API/worker processes against one Postgres:

1. **At most one live turn** per conversation (`_turn_claim` reject-don't-queue)
2. **`control_revision` monotonic** — stale envelopes no-op
3. **Ledger writes serializable** — no interleaved `active_task` corruption
4. **Orphan claim steal** after worker death — thread unblocks

---

## Automated pins (run in CI today)

```bash
.bot0venv/bin/python -m pytest \
  regression_suite/test_conversation_staleness_slice6.py \
  regression_suite/test_control_plane_sdk_deliverables.py \
  regression_suite/test_decide_turn_control_plane.py \
  -q
```

Key modules: `ledger.claim_turn` / `renew_turn_claim` / `release_turn_claim`, `handoff_guard`,
`get_control_state` consistency test in `test_control_plane_sdk_deliverables`.

---

## Manual soak (staging / local multi-worker)

**Prereq:** `docker compose` with `api` scaled to 2+ workers OR staging ECS `desired_count ≥ 2`.

| Step | Action | Pass criterion |
|---|---|---|
| 1 | Open one conversation; send message A (long builder turn if possible) | 202/async or SSE starts |
| 2 | Within 2s send message B same thread | B gets `conversation_turn_in_flight` (or queued UX), not dual builder runs |
| 3 | Wait for A complete; send B again | B succeeds; `control_revision` incremented |
| 4 | Kill one worker mid-SSE (docker kill) | After orphan TTL (~steal seconds in §11.2), next message succeeds |
| 5 | Inspect `route_data.routing` on both turns | Distinct `plan_summary`; no duplicate `begin_task` without suspend |

Record: conversation_id, timestamps, `control_revision` before/after, any `handoff_ping_pong_blocked`.

---

## Open — full benchmark

Formal k6/locust harness with N tenants × M concurrent threads is **backlog** (SDK §15). This doc satisfies
the **procedure + unit/regression anchor** credibility gate until that lands.
