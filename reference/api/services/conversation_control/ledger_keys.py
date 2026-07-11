"""Single canonical registry of ledger-owned control keys.

Every component must import ``LEDGER_CONTROL_KEYS`` — do not maintain parallel sets
in ``contract.CONTROL_KEYS``, ``ledger._CONTROL_KEYS``, or docs-only lists.
"""
from __future__ import annotations

# Keys the ledger may write on conversations.context (single-writer).
# Agents must never author these via context_updates (strip_control_keys).
LEDGER_CONTROL_KEYS: frozenset[str] = frozenset({
    # Core ownership
    "active_task",
    "suspended_tasks",
    "pending_switch",
    "pending_question",
    # Orchestrator plan (ledger-owned)
    "plan",
    "shadow_plan",
    # Summary / scheduling (ledger or claim path)
    "agent_type",  # write-through projection; agents must not invent sticky ownership
    # Transitional legacy — retired over time but still ledger-cleared on complete
    "advisor_active",
    "pipeline_step",
    "create_flow_state",
    # Turn serialization + coherence (ledger-only writers)
    "_turn_claim",
    "_last_completed_turn",
    "_control_revision",
})

# Keys agents may never set (subset used by strip_control_keys — same set).
CONTROL_KEYS = LEDGER_CONTROL_KEYS

# Mutation surface for _set_jsonb_key allowlist (excludes meta counters written by helpers).
LEDGER_MUTABLE_PROJECTION_KEYS: frozenset[str] = frozenset({
    "pending_switch",
    "pending_question",
    "active_task",
    "suspended_tasks",
    "advisor_active",
    "pipeline_step",
    "create_flow_state",
    "plan",
    "shadow_plan",
})

__all__ = [
    "CONTROL_KEYS",
    "LEDGER_CONTROL_KEYS",
    "LEDGER_MUTABLE_PROJECTION_KEYS",
]
