# decide_turn integration (copy pattern)

Add a branch in your `decide_turn` implementation **after** front-door detour precedence
(`delivery_order_contract.is_front_door_detour_kind`) and **before** generic fallthrough:

```python
# Sole-continue: while kind=cyber_risk_assessment and task_intent is continue,
# do not re-open greenfield entity resolve (SDK §2.1 multi-turn stream).
if _active_kind == "cyber_risk_assessment":
    active_task_obj = ActiveTask(**{
        k: v for k, v in current_active.items() if k in ACTIVE_FIELDS
    })
    # Perceive relative intent via bounded classifier — never keyword routing on query.
    if intent == "abandon":
        # Model A: abandon is a distinct journal event (not complete).
        complete_task(
            db, tenant_id, conversation_id,
            agent="bot0",
            reason="abandon",
            task_id=current_active.get("task_id"),
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

## Host dispatch (after decide_turn)

```python
from multi_turn_stream_contract import (
    phase_allows_entity_resolve,
    sole_continue_blocks_entity_resolve,
    ledger_entity_pins,
)

# Entity resolve / list openers only when phase allows:
if sole_continue_blocks_entity_resolve(context, task_intent=intent):
    # continue under pin + specialist cognition — do not resolve_by_name(...)
    ...
else:
    # open / anchor / pick phases may resolve
    ...

# Identity authority after pin:
pins = ledger_entity_pins(context)  # payload only — not ambient last_read alone

# Map AgentTurnResult → ledger (sole writer):
# apply_transition_request(db, tenant_id, conversation_id,
#     agent="cyber_risk_assessment", request=result.transition)
# or finish_active_task(..., reason="complete"|"abandon", context=context)
```

Register in `AGENT_REGISTRY` with `task_kind="bounded"`. Never import `ledger.py` from the agent module.
