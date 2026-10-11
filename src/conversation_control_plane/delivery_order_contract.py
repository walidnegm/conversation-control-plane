"""Delivery-order contract — front-door detours beat active-flow handlers.

Portable invariant (SDK §2.1): when the turn's decision names an informative
front-door detour (``orient`` / ``choose_path``), ``decide_turn`` supersedes active guided
flows and the chat entrypoint delivers that detour **before** ledger-first
active-flow continuations (realization_intake, outcome_value_setup, authoring
gates, product-concept how-tos).

This module is the single owner for the supersede predicate — not per-handler
``_plan_mode != "detour"`` copies in ``bot0.chat()``.

**Capability detour delivery-order table** (``DETOUR_DELIVERY_ORDER_TABLE``) pins
which code-owned detours run before vs after ``decide_turn`` and which router
labels they suppress. New detours must extend the table + allow-list + ratchet
tests — never append late ``_try_resolve_*`` handlers at the bottom of
``bot0.chat()``.

Enforced: ``regression_suite/test_delivery_order_contract.py``
"""
from __future__ import annotations

import logging

from dataclasses import dataclass
from typing import Any

from conversation_control_plane.discovery_intent import (
    DISCOVERY_DETOUR_KINDS,
    is_discovery_detour_kind,
)

logger = logging.getLogger(__name__)

# Router ``discovery_kind`` labels that must beat active guided flows.
FRONT_DOOR_DETOUR_KINDS = frozenset({*DISCOVERY_DETOUR_KINDS, "orientation"})

# Post-decide delivery ladder (Bot0 reference). Stages before ``FRONT_DOOR_DELIVERY``
# must call ``active_flow_handler_must_yield()`` before returning.
STAGE_PRE_DECIDE_FINITE = "pre_decide_finite"
STAGE_DECIDE_TURN = "decide_turn"
STAGE_FRONT_DOOR_DELIVERY = "front_door_delivery"
STAGE_ACTIVE_FLOW_CONTINUE = "active_flow_continue"
STAGE_SURFACE_READ = "surface_read"
STAGE_ORCHESTRATOR = "orchestrator"


@dataclass(frozen=True)
class DetourDeliveryRow:
    """One row in the capability detour delivery-order table."""

    detour_id: str
    """Stable id matching ``dispatch=`` in ``_code_owned_dispatch_routing``."""

    timing: str
    """``pre_decide`` | ``post_decide_front_door`` | ``post_decide_active_flow``."""

    runs_after: str
    """Prior stage or handler this detour follows in ``bot0.chat()``."""

    runs_before: str
    """Next stage this detour must precede (load-bearing)."""

    suppresses_labels: tuple[str, ...]
    """Router / plan labels this detour must clear or beat on the same turn."""

    authority_module: str
    """Code owner for cognition overrides (router authority or shape gate)."""


# Load-bearing delivery order for capability detours (attach, scorecards,
# product-concept, prose intake). Order within ``pre_decide`` is enforced in
# ``bot0.chat()`` and ratcheted in ``test_delivery_order_contract.py``.
DETOUR_DELIVERY_ORDER_TABLE: tuple[DetourDeliveryRow, ...] = (
    DetourDeliveryRow(
        detour_id="prose_intake_post_router_enqueue",
        timing="pre_decide",
        runs_after="decide_turn_act",
        runs_before=STAGE_DECIDE_TURN,
        suppresses_labels=(
            "workflow_draft_request+draft_help",
            "discovery_kind",
            "sparse_intake_copy",
            "orchestrator_preamble",
        ),
        authority_module=(
            "turn_decision_contract act=draft_work+"
            "input_shape.looks_like_rich_workflow_spec"
        ),
    ),
    # Legacy id kept for pin compatibility; same delivery as post_router.
    DetourDeliveryRow(
        detour_id="prose_intake_early_enqueue",
        timing="pre_decide",
        runs_after="decide_turn_act",
        runs_before=STAGE_DECIDE_TURN,
        suppresses_labels=(
            "workflow_draft_request+draft_help",
            "discovery_kind",
            "sparse_intake_copy",
        ),
        authority_module="input_shape.looks_like_rich_workflow_spec",
    ),
    DetourDeliveryRow(
        detour_id="workflow_diagram_authoring",
        timing="pre_decide",
        runs_after="decide_turn_act",
        runs_before=STAGE_DECIDE_TURN,
        suppresses_labels=(
            "attachment_capability_request",
            "workflow_draft_request+draft_help",
            "sparse_intake_copy",
            "product_concept_kind",
        ),
        authority_module="turn_decision_contract act=draft_work",
    ),
    DetourDeliveryRow(
        detour_id="attachment_capability",
        timing="pre_decide",
        runs_after="workflow_diagram_authoring",
        runs_before=STAGE_DECIDE_TURN,
        suppresses_labels=(
            "workflow_draft_request",
            "user_wants=draft_help",
            "sparse_intake_copy",
            "intake_readiness",
        ),
        authority_module="turn_decision_contract act=attach_capability",
    ),
    # Greenfield multi-turn *starts* only. Must yield when ledger already owns
    # the kind (sole_continue_blocks_greenfield_start) — otherwise verify/save
    # turns re-enter start and loop (conv_069561ce cyber).
    DetourDeliveryRow(
        detour_id="cyber_risk_assessment_start",
        timing="pre_decide",
        runs_after="attachment_capability",
        runs_before=STAGE_DECIDE_TURN,
        suppresses_labels=(
            "product_concept_kind",
            "discovery_kind",
            "concept_gate",
        ),
        authority_module=(
            "bot0._try_resolve_cyber_risk_assessment_turn + "
            "task_pin_contract.sole_continue_blocks_greenfield_start + "
            "task_pin_contract.sole_continue_blocks_foreign_surface_start"
        ),
    ),
    # Ledger session status (active activities / resume) — before concept_gate
    # so product-knowledge cannot package "What is Home?" (conv_f116cd1f).
    DetourDeliveryRow(
        detour_id="session_activities",
        timing="post_decide_front_door",
        runs_after=STAGE_DECIDE_TURN,
        runs_before="concept_gate",
        suppresses_labels=(
            "concept_gate",
            "product_concept_kind",
            "discovery_kind",
        ),
        authority_module=(
            "session_activities.try_session_activities_answer + "
            "concept_packaging_query_eligible session-status block"
        ),
    ),
    DetourDeliveryRow(
        detour_id="concept_gate",
        timing="post_decide_front_door",
        runs_after="session_activities",
        runs_before=STAGE_FRONT_DOOR_DELIVERY,
        suppresses_labels=(
            "discovery_kind=scorecards",
            "orientation_focus=status",
            "resume_authoring",
            "sparse_intake_copy",
            "workflow_draft_request",
        ),
        authority_module=(
            "grounded_glossary_detour_query + apply_grounded_glossary_authority "
            "+ _try_post_decide_concept_gate_answer"
        ),
    ),
    DetourDeliveryRow(
        detour_id="scorecards_discovery",
        timing="post_decide_front_door",
        runs_after=STAGE_DECIDE_TURN,
        runs_before=STAGE_ACTIVE_FLOW_CONTINUE,
        suppresses_labels=(
            "read_kind=outcome_value_setup",
            "workflow_draft_request",
            "product_concept_kind",
        ),
        authority_module="turn_decision_contract act=orient focus=scorecards",
    ),
    DetourDeliveryRow(
        detour_id="product_concept_howto",
        timing="post_decide_front_door",
        runs_after=STAGE_FRONT_DOOR_DELIVERY,
        runs_before=STAGE_ACTIVE_FLOW_CONTINUE,
        suppresses_labels=(
            "workflow_draft_request",
            "discovery_kind",
            "sparse_intake_copy",
        ),
        authority_module="turn_decision_contract act=explain",
    ),
    DetourDeliveryRow(
        detour_id="prose_intake_turn",
        timing="post_decide_active_flow",
        runs_after=STAGE_FRONT_DOOR_DELIVERY,
        runs_before=STAGE_ORCHESTRATOR,
        suppresses_labels=(
            "discovery_kind",
            "product_concept_kind",
            "attachment_capability_request",
        ),
        authority_module="prose_intake_contract + workflow_intake",
    ),
)

PRE_DECIDE_CAPABILITY_DETOUR_IDS = frozenset(
    row.detour_id
    for row in DETOUR_DELIVERY_ORDER_TABLE
    if row.timing == "pre_decide"
)


def is_front_door_detour_kind(kind: str | None) -> bool:
    return (kind or "").strip().lower() in FRONT_DOOR_DETOUR_KINDS


def _decision_discovery_kind() -> str:
    """The front-door kind the turn's decision names, or ``""``.

    ``orient`` names its focus (``orientation`` included); ``choose_path`` is
    the intent-clarify door. Any other act names none. No decision → ``""``.
    """
    try:
        from conversation_control_plane.turn_decision_contract import (
            get_turn_decision,
        )

        d = get_turn_decision()
    except Exception:  # noqa: BLE001
        return ""
    if d is None:
        return ""
    if d.act == "orient":
        return str((d.slots or {}).get("focus") or "orientation")
    if d.act == "choose_path":
        return "intent_clarify"
    return ""


def _discovery_kind_candidates(
    *,
    discovery: dict[str, str] | None = None,
    plan: Any = None,
) -> list[str]:
    out: list[str] = []
    if plan is not None:
        out.append(str(getattr(plan, "discovery_kind", None) or ""))
    if isinstance(discovery, dict):
        out.append(str(discovery.get("kind") or ""))
    out.append(_decision_discovery_kind())
    return out


# Exclusive post-router owners — at most ONE may deliver a user-visible reply.
# B-248: the owner is read off the turn's one decision
# (``turn_owner_from_decision``), so nothing picks from this tuple any more; it
# is the declared vocabulary of delivery owners (projected by
# ``turn_composition_registry``). New multi-turn work streams register here; do
# not append parallel late handlers in bot0.chat().
EXCLUSIVE_TURN_OWNER_PRIORITY: tuple[str, ...] = (
    "cost_out",
    "draft",
    "workflow_build",  # multi-gate authoring sole-continue (WB ladder)
    "cyber_risk",
    "realization",
    "outcome_value",
    "scorecard",
    "pattern_midflight",  # Optimize/Expand/Rewire/Precedent midflight (C11)
    "recommendation_setup",  # Recommend 2.0 gather/setup interview
    "engagement_pack",  # Dense multi-surface plan of attack (F6)
    "input_state_setup",  # Input State Manager (chat sim assumptions)
    "surface_read",
    "advisor",
    "product_concept",
    "discovery",
    "concept_gate",
    "default",
)

# Owners that must never yield to front-door discovery / glossary detours.
ACTION_EXCLUSIVE_OWNERS = frozenset({
    "cost_out",
    "draft",
    "workflow_build",
    "cyber_risk",
    "realization",
    "outcome_value",
    "scorecard",
    "pattern_midflight",
    "recommendation_setup",
    "engagement_pack",
    "input_state_setup",
    "surface_read",
    "advisor",
    "session_activities",  # orientation → ledger status, never concept_gate
})


@dataclass(frozen=True)
class ExclusiveTurnOwner:
    """Single delivery owner for one user turn after authority sealing."""

    owner_id: str
    reason: str = ""


#: The ``product_concept_kind`` that means "a question about the product",
#: routed to ``concept_gate`` rather than to a how-to overview. Registered in
#: ``turn_decision_contract.CONCEPT_KINDS``.
PRODUCT_KNOWLEDGE_KIND = "product_knowledge"
try:
    from conversation_control_plane.product_knowledge_family_contract import (
        GLOSSARY_PRODUCT_CONCEPT_KINDS as _GLOSSARY_PCK,
    )
except Exception:  # noqa: BLE001
    _GLOSSARY_PCK = frozenset({PRODUCT_KNOWLEDGE_KIND})


#: B-248: the delivery owner of a decided act. One reading of the decision —
#: never a second classification of the turn (AGENTS §1 *No second authority*).
_OWNER_BY_ACT: dict[str, str] = {
    "draft_work": "draft",
    "show_example": "draft",
    "read": "surface_read",
    "edit_work": "surface_read",
    "simulate": "surface_read",
    "set_value_metrics": "surface_read",
    "export_authority": "surface_read",
    "realize": "realization",
    "assess_risk": "cyber_risk",
    "estimate_cost": "cost_out",
    "orient": "discovery",
    "choose_path": "discovery",
    "create_project": "advisor",
    "create_catalog_role": "advisor",
    "engagement_pack": "engagement_pack",
    "setup_input_state": "input_state_setup",
}


def turn_owner_from_decision(decision: Any, *, active_task: Any = None) -> ExclusiveTurnOwner:
    """The turn's delivery owner, read off its one ``ResolvedTurnDecision``.

    ``continue`` belongs to the open task — its kind's owner from
    ``KIND_TO_EXCLUSIVE_OWNER`` (the same table the sole-continue contract
    uses). Every other act names its own owner. ``explain`` splits on the
    decision's concept kind exactly as packaging does: a product question is
    ``concept_gate``, a how-to overview is ``product_concept``.
    """
    act = str(getattr(decision, "act", "") or "")
    slots = dict(getattr(decision, "slots", None) or {})
    if act == "continue":
        kind = ""
        if isinstance(active_task, dict):
            kind = str(active_task.get("kind") or "").strip()
        try:
            from conversation_control_plane.task_pin_contract import (
                KIND_TO_EXCLUSIVE_OWNER,
            )

            owner = KIND_TO_EXCLUSIVE_OWNER.get(kind, "")
        except Exception:  # noqa: BLE001
            owner = ""
        return ExclusiveTurnOwner(owner or "default", f"decision:continue kind={kind or '-'}")
    if act == "explain":
        concept = str(slots.get("concept_kind") or PRODUCT_KNOWLEDGE_KIND)
        if concept in _GLOSSARY_PCK:
            return ExclusiveTurnOwner("concept_gate", f"decision:explain {concept}")
        return ExclusiveTurnOwner("product_concept", f"decision:explain {concept}")
    if act == "orient":
        # The focus's owner is declared once, in the discovery packaging table
        # (orientation is ledger-owned by session_activities, conv_2d889a55).
        focus = str(slots.get("focus") or "orientation")
        try:
            from conversation_control_plane.discovery_packaging_authority_contract import (
                _row as _packaging_row,
            )

            row = _packaging_row(focus)
        except Exception:  # noqa: BLE001
            row = None
        owner = row.owner_when_unyielded if row is not None else "discovery"
        return ExclusiveTurnOwner(owner, f"decision:orient {focus}")
    return ExclusiveTurnOwner(_OWNER_BY_ACT.get(act, "default"), f"decision:{act}")


# B-248: ``select_exclusive_turn_owner`` and its unguarded cascade are deleted.
# They re-picked the delivery owner from legacy router labels and free text
# (a second decider over a projection of the decision); the owner is read off
# the decision by ``turn_owner_from_decision``. Their private helpers
# (``_observe_declared_priority``, ``sole_continue_blocks_concept_gate_owner``)
# went with them.


def exclusive_owner_allows_front_door_discovery(owner: ExclusiveTurnOwner | str) -> bool:
    oid = owner.owner_id if isinstance(owner, ExclusiveTurnOwner) else str(owner)
    return oid == "discovery"


def exclusive_owner_allows_concept_gate(owner: ExclusiveTurnOwner | str) -> bool:
    """Concept gate only when it *is* the exclusive owner.

    Action sole-continue owners (cost_out, draft, cyber, …) never allow packaging.
    ``default`` also refuses — residual orchestrator path, not glossary.
    """
    oid = owner.owner_id if isinstance(owner, ExclusiveTurnOwner) else str(owner)
    return oid == "concept_gate"


def exclusive_owner_allows_product_concept(owner: ExclusiveTurnOwner | str) -> bool:
    oid = owner.owner_id if isinstance(owner, ExclusiveTurnOwner) else str(owner)
    return oid == "product_concept"


def front_door_detour_supersedes_active_flow(
    *,
    discovery: dict[str, str] | None = None,
    plan: Any = None,
) -> bool:
    """True when a router-owned front-door detour must beat an active guided flow.

    Action exclusive owners (cost / draft / cyber / surface / advisor) never yield
    to discovery — seals the multi-winner race.

    Composed ``product_concept`` / ``concept_gate`` / ``default`` also never
    yield: leftover ``intent_clarify`` on a stale discovery dict must not
    steal Realization howto (conv_a4805af5). Only owner ``discovery`` may
    supersede via the front door.

    B-248: the owner is the turn's decision (``turn_owner_from_decision``);
    the ``unified_signal=`` legacy parameter is gone.
    """
    try:
        from conversation_control_plane.turn_decision_contract import (
            get_turn_decision,
        )

        d = get_turn_decision()
    except Exception:  # noqa: BLE001
        d = None
    if d is not None:
        owner = turn_owner_from_decision(d)
        # session_activities owns the orientation read (conv_2d889a55); it is
        # the front-door orientation detour, not an action that holds a flow.
        if owner.owner_id in ACTION_EXCLUSIVE_OWNERS and owner.owner_id != "session_activities":
            return False
        if owner.owner_id in ("product_concept", "concept_gate", "default"):
            return False
    return any(
        is_front_door_detour_kind(k)
        for k in _discovery_kind_candidates(discovery=discovery, plan=plan)
    )


def discovery_detour_supersedes_active_flow(
    *,
    discovery: dict[str, str] | None = None,
    plan: Any = None,
) -> bool:
    """Facade name for execute-layer guards — includes orientation detours.

    Adopters may import from ``dispatch_phase.discovery_detour_supersedes_active_flow``
    or this module; both delegate to ``front_door_detour_supersedes_active_flow``.
    """
    return front_door_detour_supersedes_active_flow(
        discovery=discovery,
        plan=plan,
    )


def plan_owns_front_door_delivery(plan: Any = None) -> bool:
    """True when ``decide_turn`` opened or detoured for a front-door delivery."""
    if plan is None:
        return False
    mode = str(getattr(plan, "mode", None) or "").strip().lower()
    dk = str(getattr(plan, "discovery_kind", None) or "none").strip().lower()
    return mode in ("discovery", "detour") and is_front_door_detour_kind(dk)


def active_flow_handler_must_yield(
    *,
    plan: Any = None,
    discovery: dict[str, str] | None = None,
) -> bool:
    """Recipe for ledger-first / gate handlers: yield to front-door delivery."""
    return (
        plan_owns_front_door_delivery(plan)
        or front_door_detour_supersedes_active_flow(
            discovery=discovery,
            plan=plan,
        )
    )


__all__ = [
    "DETOUR_DELIVERY_ORDER_TABLE",
    "DetourDeliveryRow",
    "FRONT_DOOR_DETOUR_KINDS",
    "PRE_DECIDE_CAPABILITY_DETOUR_IDS",
    "STAGE_ACTIVE_FLOW_CONTINUE",
    "STAGE_DECIDE_TURN",
    "STAGE_FRONT_DOOR_DELIVERY",
    "STAGE_ORCHESTRATOR",
    "STAGE_PRE_DECIDE_FINITE",
    "STAGE_SURFACE_READ",
    "active_flow_handler_must_yield",
    "discovery_detour_supersedes_active_flow",
    "front_door_detour_supersedes_active_flow",
    "is_front_door_detour_kind",
    "plan_owns_front_door_delivery",
    "turn_owner_from_decision",
    "ExclusiveTurnOwner",
    "ACTION_EXCLUSIVE_OWNERS",
    "EXCLUSIVE_TURN_OWNER_PRIORITY",
    "exclusive_owner_allows_concept_gate",
    "exclusive_owner_allows_front_door_discovery",
    "exclusive_owner_allows_product_concept",
]