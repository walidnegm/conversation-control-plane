"""Portable multi-turn stream contract — **all** chat-complete sole-continue kinds.

Not cost-specific. Cost is the pilot paint; cyber, realization, drafting, O&V,
project, scorecards, risk-catalog share the same disease when they violate this.

## Invariants (every turn on a sole-continue stream)

1. **Phase owns dispatch** — after the entity is pinned, do not re-run entity
   resolve / list openers / ambient last_read as if greenfield.
2. **Pin owns identity** — ledger payload ids only; ``last_read_*`` is mirror,
   never sole authority for "which entity they meant this turn".
3. **LLM owns continue meaning** — sizing, verify chips, refine, detour labels;
   code owns finite path digits when a path menu was armed.
4. **No NL wordlist as sole arbiter** of what the user meant (AGENTS.md).

Portable for the public SDK extract (no private product code). Optional
``task_pin_contract`` import when running inside the Bot0 monorepo.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

# Kind string constants — public-safe example registry (not a product catalog).
COST_OUT_KIND = "cost_out"
CYBER_RISK_KIND = "cyber_risk_assessment"
DRAFTING_KIND = "drafting"
OUTCOME_VALUE_KIND = "outcome_value_setup"
PROJECT_WORKSPACE_KIND = "project_workspace"
REALIZATION_KIND = "realization_intake"
RISK_CATALOG_LEARNING_KIND = "risk_catalog_learning"
SCORECARD_INTERROGATE_KIND = "scorecard_interrogate"

SOLE_CONTINUE_KINDS = frozenset({
    COST_OUT_KIND,
    CYBER_RISK_KIND,
    REALIZATION_KIND,
    OUTCOME_VALUE_KIND,
    DRAFTING_KIND,
    PROJECT_WORKSPACE_KIND,
    SCORECARD_INTERROGATE_KIND,
    RISK_CATALOG_LEARNING_KIND,
})


def active_task_from_context(
    context: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    task = (context or {}).get("active_task")
    return task if isinstance(task, dict) else None


def active_task_kind(context: Mapping[str, Any] | None) -> str | None:
    task = active_task_from_context(context)
    if not task:
        return None
    kind = str(task.get("kind") or "").strip()
    return kind or None


def is_sole_continue_kind(kind: str | None) -> bool:
    return bool(kind) and kind in SOLE_CONTINUE_KINDS


# Prefer monorepo task_pin registry when present (single source of kind strings).
try:
    from api.services.conversation_control.task_pin_contract import (  # type: ignore
        COST_OUT_KIND as COST_OUT_KIND,
        CYBER_RISK_KIND as CYBER_RISK_KIND,
        DRAFTING_KIND as DRAFTING_KIND,
        OUTCOME_VALUE_KIND as OUTCOME_VALUE_KIND,
        PROJECT_WORKSPACE_KIND as PROJECT_WORKSPACE_KIND,
        REALIZATION_KIND as REALIZATION_KIND,
        RISK_CATALOG_LEARNING_KIND as RISK_CATALOG_LEARNING_KIND,
        SCORECARD_INTERROGATE_KIND as SCORECARD_INTERROGATE_KIND,
        SOLE_CONTINUE_KINDS as SOLE_CONTINUE_KINDS,
        active_task_from_context as active_task_from_context,
        active_task_kind as active_task_kind,
        is_sole_continue_kind as is_sole_continue_kind,
    )
except ImportError:
    # Public extract / standalone: use module-local kind registry above.
    _USING_LOCAL_KIND_REGISTRY = True
else:
    _USING_LOCAL_KIND_REGISTRY = False

# Phases where *entity resolve / pick* is allowed (kind → frozenset).
# Anything not listed is treated as "continue" (no ambient re-resolve).
ENTITY_RESOLVE_PHASES_BY_KIND: dict[str, frozenset[str]] = {
    COST_OUT_KIND: frozenset({"open", "entity_pick", ""}),
    CYBER_RISK_KIND: frozenset({"anchor", ""}),  # pin once at start
    REALIZATION_KIND: frozenset({"open", "entity_pick", "anchor", ""}),
    PROJECT_WORKSPACE_KIND: frozenset({"open", ""}),
    SCORECARD_INTERROGATE_KIND: frozenset({"active", ""}),  # pick run while active
    RISK_CATALOG_LEARNING_KIND: frozenset({"browsing", ""}),
    OUTCOME_VALUE_KIND: frozenset({"collecting", ""}),
    DRAFTING_KIND: frozenset({"awaiting_domain", "awaiting_details", ""}),
}

# Phases where continue cognition owns the turn (no entity re-resolve).
# Explicit sets where known; default = "not in ENTITY_RESOLVE_PHASES".
CONTINUE_PHASES_BY_KIND: dict[str, frozenset[str]] = {
    COST_OUT_KIND: frozenset({"anchored", "sizing", "estimated"}),
    CYBER_RISK_KIND: frozenset({
        "discover", "project", "verify", "score", "complete",
    }),
    REALIZATION_KIND: frozenset({"collecting", "confirming", "export", "complete"}),
    PROJECT_WORKSPACE_KIND: frozenset({
        "roles", "staffing", "scenario", "sim", "active", "complete",
    }),
    SCORECARD_INTERROGATE_KIND: frozenset({"detail", "complete"}),
    RISK_CATALOG_LEARNING_KIND: frozenset({"detail", "complete"}),
    OUTCOME_VALUE_KIND: frozenset({"confirming", "complete", "active"}),
    DRAFTING_KIND: frozenset({"drafting", "refining", "ready_to_build", "active"}),
}


def stream_kind(context: Mapping[str, Any] | None) -> str | None:
    """Active sole-continue kind, or None."""
    kind = active_task_kind(context)
    if is_sole_continue_kind(kind):
        return kind
    return None


def stream_phase(context: Mapping[str, Any] | None) -> str:
    """Phase string from active_task (empty if none)."""
    task = active_task_from_context(context)
    if not task:
        return ""
    phase = str(task.get("phase") or "").strip()
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    if not phase and payload:
        phase = str(payload.get("phase") or "").strip()
    return phase


def phase_allows_entity_resolve(
    kind: str | None,
    phase: str,
    *,
    has_ledger_pin: bool = False,
) -> bool:
    """True only when this stream may still resolve / open entity picks.

    Once pinned into a continue phase, returns False — continue turns must go
    to cognition + code execution, not re-resolve.
    """
    if not kind or kind not in SOLE_CONTINUE_KINDS:
        # No sole-continue stream: greenfield may resolve.
        return True
    ph = (phase or "").strip()
    continue_set = CONTINUE_PHASES_BY_KIND.get(kind)
    if continue_set is not None and ph in continue_set:
        return False
    resolve_set = ENTITY_RESOLVE_PHASES_BY_KIND.get(kind)
    if resolve_set is not None:
        if ph in resolve_set:
            return True
        # Unknown phase with pin → fail closed (no re-resolve).
        if has_ledger_pin and ph not in resolve_set:
            return False
        return ph in resolve_set or ph == ""
    # Default: if we have a pin and a non-empty phase, assume continue.
    if has_ledger_pin and ph:
        return False
    return True


def context_may_seed_entity_resolve(
    *,
    kind: str | None,
    phase: str,
    generic_howto: bool,
    has_list_inventory: bool,
    has_list_position: bool,
) -> bool:
    """Whether ambient conversation context (last_read, etc.) may seed resolve.

    False for generic how-to without list pick (pin-hijack class — all streams).
    """
    if generic_howto and not has_list_inventory and not has_list_position:
        return False
    if not phase_allows_entity_resolve(kind, phase):
        return False
    return True


def ledger_entity_pins(context: Mapping[str, Any] | None) -> dict[str, str]:
    """Typed pins from active_task.payload only (authority)."""
    task = active_task_from_context(context)
    if not task:
        return {}
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    out: dict[str, str] = {}
    for key in (
        "workflow_id",
        "project_id",
        "scenario_id",
        "run_id",
        "risk_id",
        "domain_id",
        "agent_ref",
    ):
        val = str(payload.get(key) or "").strip()
        if val:
            out[key] = val
    return out


def has_ledger_entity_pin(context: Mapping[str, Any] | None) -> bool:
    return bool(ledger_entity_pins(context))


def continue_must_use_cognition(
    kind: str | None,
    phase: str,
    *,
    has_ledger_pin: bool = False,
) -> bool:
    """True when this turn's meaning must be LLM/assessor, not re-resolve."""
    if not kind or kind not in SOLE_CONTINUE_KINDS:
        return False
    return not phase_allows_entity_resolve(
        kind, phase, has_ledger_pin=has_ledger_pin,
    )


def task_intent_allows_supersede(task_intent: str | None) -> bool:
    """Classifier-owned escapes from sole-continue."""
    return (task_intent or "continue").strip().lower() in (
        "detour", "new_task", "abandon", "handoff",
    )


def sole_continue_blocks_entity_resolve(
    context: Mapping[str, Any] | None,
    *,
    task_intent: str | None = "continue",
) -> bool:
    """True when greenfield entity resolve / name re-open must not run.

    Platform gate for **all** sole-continue kinds (Grade A C5). Detour/new_task
    always allows resolve. Continue + pin + continue-phase → block.
    """
    if task_intent_allows_supersede(task_intent):
        return False
    kind = stream_kind(context)
    if not kind:
        return False
    phase = stream_phase(context)
    has_pin = has_ledger_entity_pin(context)
    return not phase_allows_entity_resolve(
        kind, phase, has_ledger_pin=has_pin,
    )


def preferred_workflow_id_from_stream(
    context: Mapping[str, Any] | None,
    *,
    allow_ambient_last_read: bool = False,
) -> str:
    """Authoritative workflow id: ledger pin first; ambient only if allowed.

    Grade A C4/C6 — never treat ``last_read_workflow_id`` as sole authority
    while a sole-continue stream is pinned unless caller opts in (resolve phase).
    """
    pins = ledger_entity_pins(context)
    pin = pins.get("workflow_id") or ""
    if pin:
        return pin
    if not allow_ambient_last_read:
        kind = stream_kind(context)
        phase = stream_phase(context)
        if kind and not phase_allows_entity_resolve(
            kind, phase, has_ledger_pin=False,
        ):
            return ""
    ctx = context if isinstance(context, Mapping) else {}
    return str(ctx.get("last_read_workflow_id") or ctx.get("workflow_id") or "").strip()


# Bot0 monorepo production adopters (Grade A C12). Public extract may ignore.
STREAM_GATE_ADOPTER_PATHS: frozenset[str] = frozenset({
    "api/services/conversation_control/multi_turn_stream_contract.py",
    "api/services/conversation_control/cost_out_turn.py",
    "api/services/conversation_control/inventory_entity_resolve.py",
    "api/services/outcome_value_setup_handler.py",
    "api/services/cyber_risk_subject_contract.py",
    "api/services/realization_intake_handler.py",
    "api/services/conversation_control/task_pin_contract.py",
})


__all__ = [
    "COST_OUT_KIND",
    "CYBER_RISK_KIND",
    "DRAFTING_KIND",
    "OUTCOME_VALUE_KIND",
    "PROJECT_WORKSPACE_KIND",
    "REALIZATION_KIND",
    "RISK_CATALOG_LEARNING_KIND",
    "SCORECARD_INTERROGATE_KIND",
    "CONTINUE_PHASES_BY_KIND",
    "ENTITY_RESOLVE_PHASES_BY_KIND",
    "SOLE_CONTINUE_KINDS",
    "STREAM_GATE_ADOPTER_PATHS",
    "context_may_seed_entity_resolve",
    "continue_must_use_cognition",
    "has_ledger_entity_pin",
    "ledger_entity_pins",
    "phase_allows_entity_resolve",
    "preferred_workflow_id_from_stream",
    "sole_continue_blocks_entity_resolve",
    "stream_kind",
    "stream_phase",
    "task_intent_allows_supersede",
]
