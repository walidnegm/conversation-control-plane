# Cyber Risk Assessment — SDK-shaped agent stub

**Status:** **Design stub only** for external adopters — **not** production product code.

This example shows how a **bounded** multi-turn specialist plugs into the Conversation Control Plane
(including **Model A L2** task identity + journal). It deliberately omits proprietary scoring,
tenant corpora, and product UI.

## Layered stack (where this fits)

| Layer | This example |
|---|---|
| **1 — In-agent execution** | Your LangGraph/tools/async job for discover/score (not shipped here) |
| **2 — Conversation control** | Ledger `kind=cyber_risk_assessment` + `decide_turn` sole-continue |
| **3 — Memory** | IR checkpoint in `active_task.payload`; domain results in *your* store |

## Control-plane contract (required)

- Ledger `active_task.kind = cyber_risk_assessment`
- Closed phases: `anchor → discover → project → verify → score → complete`
- Agent returns **`TaskTransitionRequest` / `AgentTurnResult` only** — `decide_turn` writes control keys
- **Model A L2:** immutable `task_id` on begin; `command_id` on lifecycle commands; COMPLETE ≠ ABANDON
  (journal event types `task_completed` vs `task_abandoned`)
- Heavy work runs as a **long-running async job** (202 + progress), not inline chat prose

## Multi-turn stream (do not skip)

After the entity is **pinned** (workflow/project id on the payload), **continue** turns must follow
[SDK §2.1 Multi-turn stream contract](../../docs/conversation-control-plane-sdk.md#21-multi-turn-stream-contract-every-sole-continue-kind):

1. **Phase owns dispatch** — do not re-run greenfield entity resolve while phase ∈ continue set  
2. **Pin owns identity** — payload ids only; ambient `last_read_*` is not sole authority  
3. **LLM owns continue meaning** — verify/refine labels; not keyword lists  
4. **Finite grammar only when armed** — bare `1` only if a pick menu was set  

Portable helpers (phase/pin gates): `reference/.../multi_turn_stream_contract.py`  
(`phase_allows_entity_resolve`, `sole_continue_blocks_entity_resolve`, `ledger_entity_pins`).

## Model A lifecycle (do not skip)

| Command | Projection | Journal event |
|---|---|---|
| Begin assessment | `begin_task` → `active_task.task_id` assigned | `task_began` |
| Continue VERIFY / score | `update_phase` (preserves `task_id`) | (optional progress events) |
| Save / finish | `complete_task(reason=complete)` | `task_completed` |
| Cancel / bail | `complete_task(reason=abandon)` | `task_abandoned` |

Host maps `AgentTurnResult.transition` via `apply_transition` / `apply_transition_request`
(or `finish_active_task` when the handler holds a context snapshot).

## What is included

| File | Purpose |
|---|---|
| `agent_stub.py` | `ConversationalAgent`-shaped skeleton + `TaskTransitionRequest` / `AgentTurnResult` |
| `assessment_ir.py` | Minimal typed IR (`cyber_risk_assessment_ir_v1`) — **stub fields only** |
| `decide_integration.md` | Where to add the `decide_turn` branch (copy pattern) |

## What is intentionally omitted (privacy / product)

- Production risk engines, catalogs, and tenant-specific grounding
- Product UI routes and admin tooling
- Internal epics, backlogs, and vendor secrets
- Full LangGraph subgraph (add in **your** host as Layer 1)

## Builder checklist

1. Register kind + closed phase enum  
2. `begin_task` when assessment starts; capture returned `task_id`; pin entity ids on resolve  
3. Gate continue with multi-turn helpers (no ambient sole id)  
4. Return `TaskTransitionRequest` with `task_id` + `command_id`; never write `active_task` from the agent  
5. Cancel → `abandon`; save → `complete` (distinct journal events)  
6. Pin tests: resume, complete, abandon, no auto-switch, detour stays resumable, **no re-resolve after pin**
