# decide_turn integration (copy pattern)

Add a branch in your `decide_turn` implementation **after** front-door detour precedence
(`delivery_order_contract.is_front_door_detour_kind`) and **before** generic fallthrough:

```python
if _active_kind == "cyber_risk_assessment":
    active_task_obj = ActiveTask(**{k: v for k, v in current_active.items() if k in ACTIVE_FIELDS})
    # Perceive relative intent via bounded classifier — never keyword routing on query.
    if intent == "abandon":
        complete_task(db, tenant_id, conversation_id, agent="bot0")
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

Register in `AGENT_REGISTRY` with `task_kind="bounded"`. Never import `ledger.py` from the agent module.