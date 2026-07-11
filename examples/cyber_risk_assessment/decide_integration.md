# decide_turn + host wiring (copy pattern)

## 0. Register KindSpec (once at process start)

```python
from examples.cyber_risk_assessment.kind_spec import register_in, CYBER_RISK_KIND_SPEC

KIND_REGISTRY: dict = {}
register_in(KIND_REGISTRY)
# portable: merge into conversation_control.kind_spec.KIND_REGISTRY
```

## 1. Sole-continue branch in `decide_turn`

After front-door detour precedence, before generic fallthrough:

```python
if _active_kind == "cyber_risk_assessment":
    active_task_obj = ActiveTask(**{
        k: v for k, v in current_active.items() if k in ACTIVE_FIELDS
    })
    # Perceive relative intent via bounded classifier — never keyword routing on query.
    if intent == "abandon":
        complete_task(
            db, tenant_id, conversation_id,
            agent="bot0",
            reason="abandon",
            task_id=current_active.get("task_id"),
            command_id=new_command_id(),
        )
        return TurnPlan(agent="bot0", mode="command", reason="cyber_risk_assessment abandoned")
    if intent == "detour":
        return TurnPlan(agent="bot0", mode="detour", task=active_task_obj, reason="cyber_risk detour")
    return TurnPlan(
        agent="cyber_risk_assessment",
        mode="active_task",
        task=active_task_obj,
        reason="cyber risk assessment in progress",
    )
```

## 2. Host dispatch (after decide_turn)

```python
from multi_turn_stream_contract import (
    sole_continue_blocks_entity_resolve,
    ledger_entity_pins,
)

if sole_continue_blocks_entity_resolve(context, task_intent=intent):
    # continue under pin + specialist cognition — do not resolve_by_name(...)
    ...
else:
    # open / anchor may resolve
    ...

pins = ledger_entity_pins(context)  # payload only

result = agent.handle_turn(..., context=context, thread_id=conversation_id)
# Persist domain_patch under result.pending_ref (specialist store) BEFORE or WITH ledger write
# apply_transition_request(...)  # sole writer — maps begin/continue/complete/abandon
```

## 3. Thin payload rule (P15)

When applying `payload_patch`, **reject** keys outside `KindSpec.allowed_payload_keys`
(or run `control_payload.sanitize_control_payload`). Domain IR must not land on
`active_task.payload`.

Register in `AGENT_REGISTRY` with `task_kind="bounded"`. Never import `ledger.py` from the agent module.
