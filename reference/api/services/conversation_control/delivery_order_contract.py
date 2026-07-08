"""Delivery-order contract — front-door detours beat active-flow handlers.

Portable invariant (SDK §2.1): when the unified router emits ``discovery_kind``
for an informative front-door detour, ``decide_turn`` supersedes active guided
flows and the chat entrypoint delivers that detour **before** ledger-first
active-flow continuations (realization_intake, outcome_value_setup, authoring
gates, product-concept how-tos).

This module is the single owner for the supersede predicate — not per-handler
``_plan_mode != "detour"`` copies in ``bot0.chat()``.

Enforced: ``regression_suite/test_delivery_order_contract.py``
"""
from __future__ import annotations

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


def front_door_detour_supersedes_active_flow(
    *,
    discovery: dict[str, str] | None = None,
    unified_signal: Any = None,
    plan: Any = None,
) -> bool:
    """True when a router-owned front-door detour must beat an active guided flow."""
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
    "FRONT_DOOR_DETOUR_KINDS",
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
]