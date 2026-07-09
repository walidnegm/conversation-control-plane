"""Delivery-order contract — front-door detours beat active-flow handlers.

Portable invariant (SDK §2.1): when the unified router emits ``discovery_kind``
for an informative front-door detour, ``decide_turn`` supersedes active guided
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

from dataclasses import dataclass
from typing import Any

from api.services.conversation_control.discovery_intent import (
    DISCOVERY_DETOUR_KINDS,
    is_discovery_detour_kind,
)

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
        detour_id="prose_intake_early_enqueue",
        timing="pre_decide",
        runs_after=STAGE_PRE_DECIDE_FINITE,
        runs_before="unified_turn_router",
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
        runs_after="apply_unified_router_authorities",
        runs_before=STAGE_DECIDE_TURN,
        suppresses_labels=(
            "attachment_capability_request",
            "workflow_draft_request+draft_help",
            "sparse_intake_copy",
            "product_concept_kind",
        ),
        authority_module=(
            "unified_turn_router.apply_workflow_diagram_authoring_authority"
        ),
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
        authority_module="unified_turn_router.apply_attachment_capability_authority",
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
            "task_pin_contract.sole_continue_blocks_greenfield_start"
        ),
    ),
    DetourDeliveryRow(
        detour_id="concept_gate",
        timing="post_decide_front_door",
        runs_after=STAGE_DECIDE_TURN,
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
        authority_module=(
            "unified_turn_router.apply_scorecards_discovery_authority"
        ),
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
        authority_module="unified_turn_router.apply_product_concept_authority",
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


def _discovery_kind_candidates(
    *,
    discovery: dict[str, str] | None = None,
    unified_signal: Any = None,
    plan: Any = None,
) -> list[str]:
    out: list[str] = []
    if plan is not None:
        out.append(str(getattr(plan, "discovery_kind", None) or ""))
    if isinstance(discovery, dict):
        out.append(str(discovery.get("kind") or ""))
    if unified_signal is not None:
        out.append(str(getattr(unified_signal, "discovery_kind", None) or ""))
    return out


# Exclusive post-router owners — at most ONE may deliver a user-visible reply.
# Priority is load-bearing (first match wins). New multi-turn work streams register
# here; do not append parallel late handlers in bot0.chat().
EXCLUSIVE_TURN_OWNER_PRIORITY: tuple[str, ...] = (
    "cost_out",
    "draft",
    "cyber_risk",
    "realization",
    "outcome_value",
    "scorecard",
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
    "cyber_risk",
    "realization",
    "outcome_value",
    "scorecard",
    "surface_read",
    "advisor",
})


@dataclass(frozen=True)
class ExclusiveTurnOwner:
    """Single delivery owner for one user turn after authority sealing."""

    owner_id: str
    reason: str = ""


def select_exclusive_turn_owner(
    signal: Any = None,
    *,
    query: str = "",
    packaging_eligible: bool | None = None,
    active_task: Any = None,
    context: Any = None,
) -> ExclusiveTurnOwner:
    """Pick exactly one delivery owner from a post-authority UnifiedTurnSignal.

    Priority (first match wins) — never run concept_gate / intent_clarify /
    product howto when a higher action owner is set.

    Multi-turn sole-continue: when ledger ``active_task.kind`` is a sole-continue
    stream (e.g. ``cost_out``) and task_intent is not detour/new_task/abandon,
    that kind owns delivery even if this turn's labels omitted cost_estimate_request
    (chat-complete multi-turn contract — follow-up stickiness).
    """
    # Ledger multi-turn ownership (turns N…N+k) — before label-only races.
    # Strong action labels still win when they start a different stream.
    task_intent = (
        str(getattr(signal, "task_intent", None) or "continue").strip().lower()
        if signal is not None
        else "continue"
    )
    try:
        from api.services.conversation_control.task_pin_contract import (
            exclusive_owner_for_active_kind,
        )

        ctx = context if isinstance(context, dict) else {}
        if active_task is not None and isinstance(active_task, dict):
            ctx = {**ctx, "active_task": active_task}
        sole_owner = exclusive_owner_for_active_kind(ctx, task_intent=task_intent)
        # New strong action labels may supersede sole-continue (user switched goal).
        strong_new = False
        if signal is not None:
            if bool(getattr(signal, "cost_estimate_request", False)):
                strong_new = sole_owner != "cost_out"
            if bool(getattr(signal, "workflow_draft_request", False)):
                strong_new = True
            rk_probe = str(getattr(signal, "read_kind", None) or "none").strip().lower()
            if rk_probe in ("cyber_risk_assessment", "realization_intake"):
                # Same stream continue is fine; different stream is strong_new.
                if sole_owner == "cost_out":
                    strong_new = True
                elif sole_owner == "cyber_risk" and rk_probe != "cyber_risk_assessment":
                    strong_new = True
                elif sole_owner == "realization" and rk_probe != "realization_intake":
                    strong_new = True
        if sole_owner and not strong_new and task_intent not in (
            "detour",
            "new_task",
            "abandon",
            "handoff",
        ):
            return ExclusiveTurnOwner(sole_owner, f"active_task sole-continue kind")
        # cost_estimate_request while cost_out active → still cost_out
        if sole_owner == "cost_out" and signal is not None and bool(
            getattr(signal, "cost_estimate_request", False),
        ):
            return ExclusiveTurnOwner("cost_out", "cost_out continue|cost_estimate_request")
    except Exception:  # noqa: BLE001
        pass

    if signal is None:
        return ExclusiveTurnOwner("default", "no signal")

    if bool(getattr(signal, "cost_estimate_request", False)):
        return ExclusiveTurnOwner("cost_out", "cost_estimate_request")

    builder = str(getattr(signal, "builder_entry", None) or "none").strip().lower()
    if bool(getattr(signal, "workflow_draft_request", False)) or builder not in (
        "",
        "none",
    ):
        return ExclusiveTurnOwner("draft", "workflow_draft_request|builder_entry")

    rk = str(getattr(signal, "read_kind", None) or "none").strip().lower()
    if rk == "cyber_risk_assessment":
        return ExclusiveTurnOwner("cyber_risk", "read_kind=cyber_risk_assessment")
    if rk == "realization_intake":
        return ExclusiveTurnOwner("realization", "read_kind=realization_intake")

    try:
        from api.services.conversation_control.read_intent import (
            PROJECT_SURFACE_READ_KINDS,
            WORKFLOW_SURFACE_READ_KINDS,
            WORKFLOW_SURFACE_SIMULATION_KINDS,
        )

        surface = (
            *WORKFLOW_SURFACE_READ_KINDS,
            *WORKFLOW_SURFACE_SIMULATION_KINDS,
            *PROJECT_SURFACE_READ_KINDS,
        )
        if rk in surface:
            return ExclusiveTurnOwner("surface_read", f"read_kind={rk}")
    except Exception:  # noqa: BLE001
        if rk not in ("", "none"):
            return ExclusiveTurnOwner("surface_read", f"read_kind={rk}")

    route = str(getattr(signal, "route_intent", None) or "bot0").strip().lower()
    if route == "advisor":
        return ExclusiveTurnOwner("advisor", "route_intent=advisor")

    product = str(getattr(signal, "product_concept_kind", None) or "none").strip().lower()
    if product not in ("", "none"):
        return ExclusiveTurnOwner("product_concept", f"product_concept_kind={product}")

    disc = str(getattr(signal, "discovery_kind", None) or "none").strip().lower()
    if disc not in ("", "none") and is_front_door_detour_kind(disc):
        return ExclusiveTurnOwner("discovery", f"discovery_kind={disc}")

    packaging_ctx: dict = context if isinstance(context, dict) else {}
    if active_task is not None and isinstance(active_task, dict):
        packaging_ctx = {**packaging_ctx, "active_task": active_task}

    if packaging_eligible is None and (query or "").strip():
        try:
            from api.services.bot0_product_knowledge import concept_packaging_query_eligible

            packaging_eligible = concept_packaging_query_eligible(
                query,
                product_concept_kind=product,
                context=packaging_ctx,
            )
        except Exception:  # noqa: BLE001
            packaging_eligible = False
    if packaging_eligible:
        return ExclusiveTurnOwner("concept_gate", "definitional packaging eligible")

    return ExclusiveTurnOwner("default", "orchestrator/plan default")


def exclusive_owner_allows_front_door_discovery(owner: ExclusiveTurnOwner | str) -> bool:
    oid = owner.owner_id if isinstance(owner, ExclusiveTurnOwner) else str(owner)
    return oid == "discovery"


def exclusive_owner_allows_concept_gate(owner: ExclusiveTurnOwner | str) -> bool:
    oid = owner.owner_id if isinstance(owner, ExclusiveTurnOwner) else str(owner)
    return oid == "concept_gate"


def exclusive_owner_allows_product_concept(owner: ExclusiveTurnOwner | str) -> bool:
    oid = owner.owner_id if isinstance(owner, ExclusiveTurnOwner) else str(owner)
    return oid == "product_concept"


def front_door_detour_supersedes_active_flow(
    *,
    discovery: dict[str, str] | None = None,
    unified_signal: Any = None,
    plan: Any = None,
) -> bool:
    """True when a router-owned front-door detour must beat an active guided flow.

    Action exclusive owners (cost / draft / cyber / surface / advisor) never yield
    to discovery — seals the multi-winner race.
    """
    if unified_signal is not None:
        owner = select_exclusive_turn_owner(unified_signal)
        if owner.owner_id in ACTION_EXCLUSIVE_OWNERS:
            return False
        if owner.owner_id in ("product_concept", "concept_gate", "default"):
            # Only discovery owner may supersede active flow via front door.
            if owner.owner_id != "discovery" and not any(
                is_front_door_detour_kind(k)
                for k in _discovery_kind_candidates(
                    discovery=discovery,
                    unified_signal=unified_signal,
                    plan=plan,
                )
            ):
                return False
    return any(
        is_front_door_detour_kind(k)
        for k in _discovery_kind_candidates(
            discovery=discovery,
            unified_signal=unified_signal,
            plan=plan,
        )
    )


def discovery_detour_supersedes_active_flow(
    *,
    discovery: dict[str, str] | None = None,
    unified_signal: Any = None,
    plan: Any = None,
) -> bool:
    """Facade name for execute-layer guards — includes orientation detours.

    Adopters may import from ``dispatch_phase.discovery_detour_supersedes_active_flow``
    or this module; both delegate to ``front_door_detour_supersedes_active_flow``.
    """
    return front_door_detour_supersedes_active_flow(
        discovery=discovery,
        unified_signal=unified_signal,
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
    unified_signal: Any = None,
) -> bool:
    """Recipe for ledger-first / gate handlers: yield to front-door delivery."""
    return (
        plan_owns_front_door_delivery(plan)
        or front_door_detour_supersedes_active_flow(
            discovery=discovery,
            unified_signal=unified_signal,
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
    "select_exclusive_turn_owner",
    "ExclusiveTurnOwner",
    "ACTION_EXCLUSIVE_OWNERS",
    "EXCLUSIVE_TURN_OWNER_PRIORITY",
    "exclusive_owner_allows_concept_gate",
    "exclusive_owner_allows_front_door_discovery",
    "exclusive_owner_allows_product_concept",
]