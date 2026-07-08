# Control Plane SDK — Trace Export (OTel / Langfuse sample)

Status: Living (2026-07-06) — Phase 2 observability deliverable (SDK §15)  
Canonical field definitions: [SDK §11.1](conversation-control-plane-sdk.md#111-intent-router-layers-l0l4-and-per-turn-routing-trace)

The SDK **persists** routing traces; it does **not** ship a graph UI. Pipe stable JSON to your observability
vendor.

---

## 1. Canonical shape: `Bot0RoutingTrace`

Stored at `conversation_messages.route_data.routing` and emitted on SSE as `routing`.

| Field | Type | Meaning |
|---|---|---|
| `intent` | string | **Authoritative** dispatch agent after `decide_turn` (same as `agent`) |
| `agent` | string | Specialist or `bot0` that executed the turn |
| `mode` | string | `TurnPlan.mode` — e.g. `active_task`, `detour`, `resume`, `switch_confirm` |
| `layer` | string | Router stage (`l3_llm`, `l2_structural`, …) or `turn_plan:<mode>` |
| `confidence` | number | Router self-score when available (0–1) |
| `reason` | string | Human-readable precedence / `TurnPlan.reason` |
| `router_intent` | string? | Pre-`decide_turn` router label |
| `router_layer` | string? | L0–L4 stage code |
| `intent_source` | string? | Parsed from reason — `llm`, `heuristic`, `code`, … |
| `plan_summary` | string? | Short control-plane summary |
| `task_awaiting` | string? | Active task gate when relevant |
| `task_phase` | string? | Ledger phase projection |
| `task_kind` | string? | `workflow_build`, `drafting`, … |
| `dispatch` | string? | Code-owned path id when `decide_turn` skipped |
| `capability_key` | string? | Tool/capability surface |
| `skill_key` | string? | Classifier or tool skill key |
| `executor` | string? | Display label for executor strip |

TypeScript contract: `frontend/lib/api/bot0.ts` → `Bot0RoutingTrace`.  
Builder: `api/services/bot0.py` → `_routing_trace_from_turn_plan`, `_attach_routing_trace`.

---

## 2. Ledger events (companion stream)

Export platform events written on ledger mutations (same conversation_id):

| Event | When |
|---|---|
| `ledger_write` / task lifecycle | `begin_task`, `suspend_active`, `resume_task`, `complete_task` |
| `handoff_ping_pong_blocked` | Hot-potato guard fired |
| `ledger_agent_type_conflict` | `TurnPlan` disagreed with live router (telemetry) |
| `unexpected_skip_decide_turn` | Pre-decide short-circuit outside allow-list |

Join traces on `conversation_id` + message timestamp + `control_revision`.

---

## 3. Sample — Langfuse observation

Map each assistant message to one **trace**; router + decide + execute as **spans**:

```python
# Illustrative — adapt to your Langfuse client version.
def export_turn_to_langfuse(langfuse, *, conversation_id: str, message_id: str, routing: dict):
    trace = langfuse.trace(
        id=message_id,
        session_id=conversation_id,
        name="bot0.chat.turn",
        metadata={
            "control_revision": routing.get("control_revision"),
            "task_awaiting": routing.get("task_awaiting"),
        },
    )
    if routing.get("router_layer"):
        trace.span(
            name="router",
            metadata={
                "router_intent": routing.get("router_intent"),
                "router_layer": routing.get("router_layer"),
                "confidence": routing.get("confidence"),
            },
        )
    trace.span(
        name="decide_turn",
        metadata={
            "agent": routing.get("agent"),
            "mode": routing.get("mode"),
            "plan_summary": routing.get("plan_summary"),
            "intent_source": routing.get("intent_source"),
            "reason": routing.get("reason"),
        },
    )
    if routing.get("skill_key") or routing.get("dispatch"):
        trace.span(
            name="execute",
            metadata={
                "executor": routing.get("executor"),
                "dispatch": routing.get("dispatch"),
                "skill_key": routing.get("skill_key"),
            },
        )
```

**Dashboard ideas:** count loops (`plan_summary` contains `orientation` twice in a row); ping-pong rate
(`handoff_ping_pong_blocked`); skip-decide rate (`Skipped decide_turn` in `plan_summary`).

---

## 4. Sample — OpenTelemetry attributes

Attach to your existing HTTP span for `POST /api/bot0/chat`:

```python
# After _attach_routing_trace — illustrative OTel attrs.
ROUTING_ATTRS = (
    "bot0.routing.agent",
    "bot0.routing.mode",
    "bot0.routing.router_layer",
    "bot0.routing.router_intent",
    "bot0.routing.plan_summary",
    "bot0.routing.task_awaiting",
)

def annotate_span(span, routing: dict | None) -> None:
    if not routing:
        return
    span.set_attribute("bot0.routing.agent", routing.get("agent") or "")
    span.set_attribute("bot0.routing.mode", routing.get("mode") or "")
    span.set_attribute("bot0.routing.router_layer", routing.get("router_layer") or "")
    span.set_attribute("bot0.routing.router_intent", routing.get("router_intent") or "")
    span.set_attribute("bot0.routing.plan_summary", routing.get("plan_summary") or "")
    span.set_attribute("bot0.routing.task_awaiting", routing.get("task_awaiting") or "")
```

Grafana/Loki: query `{bot0.routing.plan_summary=~".*Skipped decide_turn.*"}` for gauntlet violations.

---

## 5. Regression pins

- `regression_suite/test_routing_trace_persistence.py`
- `regression_suite/test_bot0_widget_session_management.py` (routing strip labels)

---

## 6. Not in scope (deferred)

- In-house LangGraph Studio equivalent for control plane
- Standalone ledger timeline API (Phase 2 §15) — Bot0 admin Monitoring panel exists in monorepo only
