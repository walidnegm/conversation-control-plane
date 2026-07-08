# Cyber Risk Assessment — SDK-shaped agent stub

**Status:** Design stub for external adopters (not production Bot0 code).

This example shows how a **bounded** security-assessment specialist plugs into the
Conversation Control Plane:

- Ledger `active_task.kind = cyber_risk_assessment`
- Phases: `anchor → discover → project → verify → score → complete`
- Agent returns `TaskTransition` only — `decide_turn` writes control keys
- Heavy discovery/scoring runs as a **long-running async job** (202 + progress), not inline chat prose

## What is included

| File | Purpose |
|---|---|
| `agent_stub.py` | `ConversationalAgent` skeleton + `handle_turn` contract |
| `assessment_ir.py` | Minimal typed IR (`cyber_risk_assessment_ir_v1`) |
| `decide_integration.md` | Where to add the `decide_turn` branch (copy pattern) |

## What is intentionally omitted

- Bot0 `/risk` UI, grounding studio, and tenant corpus ingest
- Internal epics, backlog tables, and parametric scoring engine
- LangGraph subgraph implementation (Slice 2 — add in your host)

## Memory checklist (portable)

1. Register `pending_ref = cyber_risk:{conversation_id}`
2. Store checkpoint IR in `active_task.payload` (mid-term)
3. Persist confirmed assumptions in your long-term artifact store (not silent reuse)
4. Pin SDK §6 cases: resume, complete, no auto-switch, detour stays resumable