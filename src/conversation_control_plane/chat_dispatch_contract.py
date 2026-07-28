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
    "inventory_dual_stream_clarify",
    # Exact inventory name on armed lists — exclusive owner vs referential_list LLM
    # (conv_9c5f24a6 Keynote / Eligibility Screening).
    "inventory_name_resolve",
    # Org-design chip — exclusive vs inventory name open (Keynote before/after).
    "show_org_design_viewer",
    # Home/recommendation starter — proposal options for saved workflows.
    "recommendation_entry",
    "surface_read_early",
    # Pinned-workflow multi-clause sim BEFORE sticky advisor (not post-decide-only).
    "workflow_simulation_entry_early",
    # Post-run metric explain (how is agent investment calculated…) — beats
    # residual-mass sim force so Optimize confirm is not reopened (conv_e8341149).
    "pinned_run_results_explain",
    "referential_list",
    "ordinal_read",
    "reset",
    "catalog_role",
    "catalog_plan_exec",
    "ir_gate_role_proposal",
    "authoring_gate_proceed_early",
    "authoring_gate_ir_confirm_early",
    "authoring_gate_ir_freeform_repair_early",
    "drafting_interpret_early",
    "prose_intake_early_enqueue",  # legacy alias — prefer post_router
    "prose_intake_post_router_enqueue",
    "diagram_attachment_early_enqueue",
    "domain_gate_pick",
    "post_save_setup",
    "post_save_status",
    "catalog_precedent_variants",
    "gap_create_linked_project",
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
    # Finite chip: bind agentic cost profile → catalog role (not NL).
    "attach_agent_cost_profile",
    # Finite chip: cost-out detour from Optimize attach card (return pin).
    "cost_out_for_attach",
    # Finite chip / typo-tolerant publish of a draft profile then attach.
    "publish_agent_cost",
    # Refuse stale Rewire baseline confirm while Optimize attach gap is open.
    "optimize_resources_flow_guard",
    # Pattern-scoped sim confirm (pre-intent; run only, never create).
    "input_state_run_confirm",
    "input_state_confirm_guard",
    # Engine 2.0 recommendation setup sole-continue + gather chips
    "recommendation_setup_continue",
    "recommendation_gather_chip",
    "recommendation_gather_create_project",
    "recommendation_not_ready",
    # Cost-out Stay/Leave when recommend grammar mid pricing
    "cost_out_recommend_fork",
    "cost_pin_refine",
    # Catalog / grounding / SOP chat short-circuits
    "catalog_plan_guard",
    "domain_grounding_chat",
    "workflow_sop_chat",
    "list_catalog_agent_roles",
    "drafting_handoff_host_ir_open",
    "interrogate_project",
    "d4_abandon_wipe",
})

# S4 collapse — post-decide deliveries (decide_turn runs first).
POST_DECIDE_DISPATCHES: FrozenSet[str] = frozenset({
    "discovery_detour",
    "orientation_detour",
    "surface_read_detour",
    "authoring_gate_proceed",
    "authoring_gate_detour",
    "concept_gate",
    "session_activities",
    "project_interrogation",
    "workflow_simulation_entry",
    "workflow_surface_read",
    # Pattern midflight free-text continue (router labels → stay/ask/abandon).
    "pattern_midflight_continue",
    "post_save_status",
    "inventory_entity_resolve",
    "cost_out_anchor",
    "cost_out_sizing",
    "cost_out_fork",
    "cost_out_sparse",
    "cost_out_estimate",
    "save_agent_cost_profile",
    "agent_cost_pricing",
    "agent_cost_pricing_elicit",
    "agent_cost_pricing_preview",
    "agent_cost_pricing_publish",
    # Engagement pack plan conductor (finite acts + journey steps).
    "engagement_pack_plan",
    "engagement_pack_open_decompose",
    "engagement_pack_continue",
    "engagement_pack_interrupted_continue",
    "engagement_pack_unclear",
    "engagement_pack_blocked",
    "engagement_pack_unknown_step",
    "engagement_pack_show_extract",
    "engagement_pack_show_extract_empty",
    "engagement_pack_show_plan",
    "engagement_pack_show_mapping",
    "engagement_pack_mapping_confirmed",
    "engagement_pack_mapping_unclear",
    "engagement_pack_need_confirm",
    "engagement_pack_need_deep_extract",
    "engagement_pack_need_as_is_structure",
    "engagement_pack_no_pack",
    "engagement_pack_deep_extract",
    "engagement_pack_deep_extract_fail",
    "engagement_pack_structure_wait",
    "engagement_pack_staff_as_is",
    "engagement_pack_staff_as_is_already_done",
    "engagement_pack_staff_to_be",
    "engagement_pack_staff_accept",
    "engagement_pack_staff_accept_fail",
    "engagement_pack_seal",
    "engagement_pack_mark_done",
    "engagement_pack_project_as_is",
    "engagement_pack_project_to_be",
    "engagement_pack_project_to_be_need_wf",
    "engagement_pack_run_as_is",
    "engagement_pack_run_to_be",
    "engagement_pack_run_to_be_need_wf",
    "engagement_pack_compare",
})

# S4/S6 — must never skip decide_turn (routing trace must say post-decide delivery).
POST_DECIDE_ONLY_DISPATCHES: FrozenSet[str] = frozenset({
    "discovery_detour",
    "orientation_detour",
    "surface_read_detour",
    "concept_gate",
    "session_activities",
    "project_interrogation",
    "workflow_simulation_entry",
    "workflow_surface_read",
    "authoring_gate_proceed",
    "authoring_gate_detour",
    "inventory_entity_resolve",
    "save_agent_cost_profile",
    "agent_cost_pricing",
    "agent_cost_pricing_elicit",
    "agent_cost_pricing_preview",
    "agent_cost_pricing_publish",
})

# Union used by static inventory ratchets (#10s multi-detour steal seal).
ALL_ALLOWLISTED_DISPATCHES: FrozenSet[str] = frozenset(
    {*PRE_DECIDE_DISPATCHES, *POST_DECIDE_DISPATCHES}
)

# Optional internal / non-chat-finish labels that may appear in traces but are
# not user-facing short-circuit leaves (not required in bot0 inventory).
DISPATCH_INVENTORY_IGNORE: FrozenSet[str] = frozenset({
    "untraced",
    "project_registry",
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


def extract_dispatch_literals_from_text(source: str) -> set[str]:
    """Collect ``dispatch=\"…\"`` and ``\"dispatch\": \"…\"`` string literals."""
    import re

    found: set[str] = set()
    for m in re.finditer(
        r'(?:dispatch\s*=\s*["\']|["\']dispatch["\']\s*:\s*["\'])([a-z0-9_]+)["\']',
        source or "",
    ):
        found.add(m.group(1))
    return found


def extract_pre_decide_true_dispatches_from_text(source: str) -> set[str]:
    """Dispatch ids near ``pre_decide_short_circuit=True`` (static window scan)."""
    import re

    found: set[str] = set()
    lines = (source or "").splitlines()
    for i, line in enumerate(lines):
        if "pre_decide_short_circuit=True" not in line and (
            "pre_decide_short_circuit = True" not in line
        ):
            continue
        window = "\n".join(lines[max(0, i - 14) : i + 4])
        for m in re.finditer(r'dispatch\s*=\s*["\']([a-z0-9_]+)["\']', window):
            found.add(m.group(1))
    return found