"""Chat dispatch contract — S7 allow-list + S4/S6 post-decide enforcement.

``decide_turn`` is the sole dispatcher. Pre-decide returns are finite-grammar /
deterministic execution only. Discovery, orientation, and surface-read detours
deliver **after** ``decide_turn`` opens the ledger task.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class ChatDispatchContractError(Exception):
    """Violation of chat gauntlet dispatch contract."""

    code: str
    message: str
    dispatch: str = ""

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


# S7 — deterministic pre-decide KEEP paths (must match ``dispatch=`` in bot0.chat).
PRE_DECIDE_DISPATCHES: FrozenSet[str] = frozenset({
    "pending_question_pick",
    "pending_workflow_pick",
    "pending_entity_pick",
    "ordinal_read",
    "reset",
    "catalog_role",
    "catalog_plan_exec",
    "ir_gate_role_proposal",
    "authoring_gate_proceed_early",
    "prose_intake_early_enqueue",
    "domain_gate_pick",
    "post_save_setup",
    "post_save_status",
    "catalog_precedent_variants",
    "gap_create_linked_project",
    "authoring_gate_ir_confirm_early",
    "realization_gap_intake",
    "realization_gap_intake_enqueue",
    "realization_gap_intake_failed",
    "workflow_diagram_authoring",
    "attachment_capability",
    # Greenfield multi-turn starts (must call sole_continue_blocks_greenfield_start)
    "cyber_risk_assessment_start",
    "cyber_risk_assessment_intake",
    # Cost-out multi-turn leaf (phase-gated owner in cost_out_turn.py)
    "cost_out_anchor",
    "cost_out_sizing",
    "cost_out_fork",
    "cost_out_sparse",
    "cost_out_estimate",
})

# S4 collapse — post-decide deliveries (decide_turn runs first).
POST_DECIDE_DISPATCHES: FrozenSet[str] = frozenset({
    "discovery_detour",
    "orientation_detour",
    "surface_read_detour",
    "authoring_gate_proceed",
    "concept_gate",
    "project_interrogation",
    "workflow_simulation_entry",
    "post_save_status",
    "inventory_entity_resolve",
    "cost_out_anchor",
    "cost_out_sizing",
    "cost_out_fork",
    "cost_out_sparse",
    "cost_out_estimate",
})

# S4/S6 — must never skip decide_turn (routing trace must say post-decide delivery).
POST_DECIDE_ONLY_DISPATCHES: FrozenSet[str] = frozenset({
    "discovery_detour",
    "orientation_detour",
    "surface_read_detour",
    "concept_gate",
    "project_interrogation",
    "workflow_simulation_entry",
    "authoring_gate_proceed",
    "inventory_entity_resolve",
})


def allowed_dispatches(*, pre_decide_short_circuit: bool) -> FrozenSet[str]:
    return PRE_DECIDE_DISPATCHES if pre_decide_short_circuit else POST_DECIDE_DISPATCHES


def validate_dispatch(
    dispatch: str,
    *,
    pre_decide_short_circuit: bool,
) -> ChatDispatchContractError | None:
    """Return a contract error when dispatch violates S4/S6/S7; None when allowed."""
    name = (dispatch or "").strip()
    if not name:
        return ChatDispatchContractError(
            code="dispatch_empty",
            message="dispatch name is required",
        )
    if pre_decide_short_circuit and name in POST_DECIDE_ONLY_DISPATCHES:
        return ChatDispatchContractError(
            code="post_decide_only_violation",
            message=(
                f"{name} must deliver after decide_turn, not as a pre-decide short-circuit"
            ),
            dispatch=name,
        )
    allowed = allowed_dispatches(pre_decide_short_circuit=pre_decide_short_circuit)
    if name not in allowed:
        return ChatDispatchContractError(
            code="dispatch_not_allowlisted",
            message=(
                f"{name} is not in the "
                f"{'pre' if pre_decide_short_circuit else 'post'}-decide allow-list"
            ),
            dispatch=name,
        )
    return None


def plan_summary_for_dispatch(
    dispatch: str,
    *,
    pre_decide_short_circuit: bool,
) -> str:
    if pre_decide_short_circuit:
        return f"Skipped decide_turn; {dispatch} short-circuit"
    return f"Post-decide delivery; {dispatch}"