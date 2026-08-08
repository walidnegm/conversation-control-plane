"""Pre-decide exclusive owner — allow-list, not suppress laundry.

**Smell (A18 · dispatch-order laundry):** each steal adds ``if open_X: skip_Y``
or inserts another short-circuit in call order. Correct for one soak; O(N²)
leaf politics across the host gauntlet.

**Seal:** project one owner for the turn, then allow only pre-decide
dispatches on that owner's allow-set. Sticky owners are **fail-closed**:
unknown / foreign leaves are denied. Greenfield ``default`` is fail-open
(all pre-decide matchers may run). Extend this table — never add
``exclusive_owner_blocks_<leaf>_early``.

Doctrine: SDK §1.6 A18 · AGENTS multi-detour / exclusive owner ·
``delivery_order_contract.select_exclusive_turn_owner`` (post-decide sibling).

Incidents: conv_e0008ce7 (KPI→inventory, then→sim early), conv_5e398f46,
conv_5e8d3caa.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Owner ids (align with delivery_order ACTION_EXCLUSIVE / KIND_TO_EXCLUSIVE)
# ---------------------------------------------------------------------------

OWNER_DEFAULT = "default"
OWNER_WORKFLOW_BUILD = "workflow_build"
OWNER_COST_OUT = "cost_out"
OWNER_DRAFT = "draft"
OWNER_CYBER = "cyber_risk"
OWNER_REALIZATION = "realization"
OWNER_OUTCOME_VALUE = "outcome_value"
OWNER_SCORECARD = "scorecard"
OWNER_AGENT_COST = "agent_cost_pricing"
OWNER_SURFACE_READ = "surface_read"
OWNER_ADVISOR = "advisor"
OWNER_PATTERN_MIDFLIGHT = "pattern_midflight"
OWNER_RECOMMENDATION_SETUP = "recommendation_setup"
OWNER_ENGAGEMENT_PACK = "engagement_pack"
OWNER_INPUT_STATE_SETUP = "input_state_setup"

STICKY_PRE_DECIDE_OWNERS: frozenset[str] = frozenset({
    OWNER_WORKFLOW_BUILD,
    OWNER_COST_OUT,
    OWNER_DRAFT,
    OWNER_CYBER,
    OWNER_REALIZATION,
    OWNER_OUTCOME_VALUE,
    OWNER_SCORECARD,
    OWNER_AGENT_COST,
    OWNER_SURFACE_READ,
    OWNER_ADVISOR,
    OWNER_PATTERN_MIDFLIGHT,
    OWNER_RECOMMENDATION_SETUP,
    OWNER_ENGAGEMENT_PACK,
    OWNER_INPUT_STATE_SETUP,
})

# Finite / control leaves safe under any sticky owner (owner's chips + reset).
# Purpose collisions still use sole_continue_blocks_inventory_pick.
STICKY_UNIVERSAL_OK: frozenset[str] = frozenset({
    "reset",
    "pending_question_pick",
    "pending_workflow_pick",
    "pending_entity_pick",
    "attach_agent_cost_profile",
    "cost_out_for_attach",
    "publish_agent_cost",
    "input_state_run_confirm",
    "input_state_confirm_guard",
    "optimize_resources_flow_guard",
    # Recommendation gather chips (finite send_text) — pin-resume path grammar.
    "recommendation_gather_chip",
    # Domain corpus arm (cognition read_kind=domain_grounding) — pin-arm detour
    # under any sticky owner (conv_44cbf0d5: project_workspace stole free-text).
    "domain_grounding_open",
    # Browse Agentic Cost SKU catalog (list prices) — universal detour.
    "list_cost_catalog",
    # FE transport recovery / product chip — sessions card (not sticky leaf).
    # conv_db40932b: sticky ISS re-showed value_drivers on "check active sessions".
    "session_activities",
})

# Per sticky owner: additional pre-decide dispatches that ARE the owner path.
PRE_DECIDE_ALLOWED_EXTRA_BY_OWNER: dict[str, frozenset[str]] = {
    OWNER_WORKFLOW_BUILD: frozenset({
        "authoring_gate_proceed_early",
        "authoring_gate_ir_confirm_early",
        "domain_gate_pick",
        "ir_gate_role_proposal",
        # Dual pack spine: after as-is IR, sticky builder must still accept
        # "Start: Build Draft IR — to-be" (conv_7a55800b: advance chip fell
        # through to orchestrator because pack pre-decide was fail-closed).
        "engagement_pack_plan",
    }),
    OWNER_DRAFT: frozenset({
        "drafting_interpret_early",
        "prose_intake_early_enqueue",
        "prose_intake_post_router_enqueue",
        "diagram_attachment_early_enqueue",
        "workflow_diagram_authoring",
        "attachment_capability",
        # Show ⇔ arm inventory under sticky draft (conv_8998d83a: list my
        # workflows re-showed draft because pre-decide denied inventory).
        "inventory_name_resolve",
    }),
    OWNER_COST_OUT: frozenset({
        "cost_out_anchor",
        "cost_out_sizing",
        "cost_out_fork",
        "cost_out_sparse",
        "cost_out_estimate",
        "pinned_run_results_explain",
        # Explicit leave/stay when user says recommend mid cost-out (conv_019aae41).
        "cost_out_recommend_fork",
    }),
    OWNER_AGENT_COST: frozenset({
        "cost_out_anchor",
        "cost_out_sizing",
        "cost_out_fork",
        "cost_out_sparse",
        "cost_out_estimate",
        "attach_agent_cost_profile",
        "publish_agent_cost",
        "cost_out_recommend_fork",
    }),
    OWNER_CYBER: frozenset({
        "cyber_risk_assessment_intake",  # continue intake, not greenfield start
    }),
    OWNER_REALIZATION: frozenset({
        "realization_gap_intake",
        "realization_gap_intake_enqueue",
        "realization_gap_intake_failed",
    }),
    OWNER_OUTCOME_VALUE: frozenset({
        # O&V continue is mostly post-decide; keep finite only via universal.
        # catalog_role is FOREIGN (conv_6ffaf54d) — never EXTRA under O&V.
        # Inventory detours while sticky metrics (conv_6ffaf54d re-burn):
        # workspace list ordinals + "simulations for 13" must deliver, not
        # fall through to hollow goal_guidance / metrics re-elicit.
        "inventory_dual_stream_clarify",
        "inventory_ordinal_simulation_runs",
        "inventory_name_resolve",
    }),
    OWNER_SCORECARD: frozenset({
        "pending_question_pick",
        "pinned_run_results_explain",
    }),
    OWNER_SURFACE_READ: frozenset({
        "ordinal_read",
        "pinned_run_results_explain",
        "surface_read_early",  # graph/inspect/list when cognition labeled
    }),
    OWNER_ADVISOR: frozenset({
        # Advisor stickiness is post-router; deny foreign pre-decide steals.
    }),
    OWNER_PATTERN_MIDFLIGHT: frozenset({
        # Catalog re-click / canned handoff under open midflight.
        "catalog_plan_exec",
        "catalog_precedent_variants",
        # Open other workflow by name (S3 abandon-on-open); list ordinals are UNIVERSAL.
        "inventory_name_resolve",
        "surface_read_early",
    }),
    OWNER_RECOMMENDATION_SETUP: frozenset({
        "recommendation_gather_chip",
        "recommendation_setup_continue",
        "recommendation_entry",
        "inventory_name_resolve",  # list my projects while project phase
    }),
    OWNER_ENGAGEMENT_PACK: frozenset({
        "engagement_pack_plan",  # continue plan / advance chips
        # Handoff contract dispatches (invent closed after structure, pack only)
        "ir_invent_closed_structure_complete",
        "ir_invent_closed_structure_complete_fallback",
        "ir_invent_no_open_gate",
        # IR finite chips only while structure world incomplete (leaf)
        "ir_gate_finite_token_early",
        "authoring_gate_ir_confirm_early",
    }),
    # Input State Manager — inspect/act/confirm chips only under sticky owner.
    OWNER_INPUT_STATE_SETUP: frozenset({
        "input_state_setup",
        "input_state_setup_continue",
        "show_simulation_inputs",
        "input_state_act_confirm",
        "input_state_run_confirm",
        "input_state_confirm_guard",
        "inventory_name_resolve",  # pick project / input state while pick_state
    }),
}

# Documented foreign leaves (denied under sticky fail-closed; greenfield OK).
# Kept for ratchets / STEAL docs — allow logic uses STICKY_UNIVERSAL + EXTRA.
FOREIGN_PRE_DECIDE_DISPATCHES: frozenset[str] = frozenset({
    "inventory_name_resolve",
    "workflow_simulation_entry_early",
    "referential_list",
    "recommendation_entry",
    "show_org_design_viewer",
    "inventory_dual_stream_clarify",
    "gap_create_linked_project",
    "catalog_precedent_variants",
    "catalog_role",
    "catalog_plan_exec",
    # Catalog continuum under cost_out (conv_196e8e8e estimate-with-defaults steal)
    "catalog_role_ai_impact",
    "catalog_role_task_param_edit",
    "catalog_add_task",
    "catalog_role_ordinal_detail",
    "cyber_risk_assessment_start",
    "drafting_interpret_early",  # only under draft owner (EXTRA)
    "prose_intake_post_router_enqueue",
    "prose_intake_early_enqueue",
    "post_save_setup",
    "post_save_status",
    # Pre-decide host leaves registered in chat_dispatch but not sticky-universal
    # (A18: foreign under sticky unless EXTRA). Keep inventory complete.
    "authoring_checkpoint",
    "authoring_gate_ir_freeform_repair_early",
    "catalog_plan_guard",
    "cost_pin_refine",
    "d4_abandon_wipe",
    "domain_grounding_chat",
    "drafting_handoff_host_ir_open",
    "goal_seek_band_compare",
    "goal_seek_band_history",
    "goal_seek_chat_solve",
    "goal_seek_intensity_preview",
    "goal_seek_need_project",
    "goal_seek_need_workflow_link",
    "goal_seek_project_workflow_pick",
    "goal_seek_results",
    "hollow_open_transfer_refuse",
    "input_state_goal_seek_bridge",
    "input_state_setup_abandon",
    "input_state_setup_band_needs_scope",
    "input_state_setup_done",
    "input_state_setup_need_name",
    "input_state_setup_need_project",
    "input_state_setup_propose_act",
    "input_state_setup_saved",
    "input_state_setup_value_mech_write",
    "input_state_setup_written",
    "interrogate_project",
    "list_catalog_agent_roles",
    "pending_entity_pick_input_state_setup",
    "project_create_confirm_rearm",
    "project_create_name_open",
    "recommendation_gather_create_project",
    "recommendation_not_ready",
    "set_value_metrics_finite",
    "workflow_sop_chat",
})

# Back-compat name used in older tests / docs.
OWNER_FINITE_PRE_DECIDE_OK = STICKY_UNIVERSAL_OK | frozenset({
    "authoring_gate_proceed_early",
    "authoring_gate_ir_confirm_early",
    "domain_gate_pick",
    "ir_gate_role_proposal",
})


@dataclass(frozen=True)
class PreDecideTurnOwner:
    """Projected exclusive owner for pre-decide filtering."""

    owner_id: str
    reason: str = ""


def project_pre_decide_owner(
    db: Any = None,
    *,
    tenant_id: str | None = None,
    conversation_id: str | None = None,
    context: Mapping[str, Any] | None = None,
    query: str = "",
) -> PreDecideTurnOwner:
    """Project who owns this turn before pre-decide short-circuits run.

    Priority:
    1. Open workflow-authoring gates (domain / Staffed / IR / KPI / commit)
    2. Sole-continue mid-flight (cost / cyber / draft / O&V / …) as continue
    3. default (greenfield — all pre-decide leaves may claim)
    """
    ctx = dict(context) if isinstance(context, Mapping) else {}

    try:
        from api.services.conversation_control.dispatch_phase import (
            authoring_gate_blocks_inventory_resolve,
        )

        if db is not None and tenant_id and conversation_id:
            if authoring_gate_blocks_inventory_resolve(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                context=ctx,
                query=query or "gate",
            ):
                return PreDecideTurnOwner(
                    OWNER_WORKFLOW_BUILD,
                    "open_authoring_gate",
                )
    except Exception:  # noqa: BLE001
        # Fail soft: missing pending / DB → fall through to ledger sole-continue.
        return PreDecideTurnOwner(OWNER_DEFAULT, "authoring_probe_failed")

    # Open advisor project-create (create_graph_step) — even without ledger kind
    # (conv_3edc8989 / DT-name-as-greenfield).
    try:
        from api.services.conversation_control.advisor_create_continue_contract import (
            advisor_project_create_open as _adv_create_open,
        )

        if _adv_create_open(ctx):
            return PreDecideTurnOwner(
                OWNER_ADVISOR,
                "advisor_project_create_open",
            )
    except Exception:  # noqa: BLE001
        pass

    active = ctx.get("active_task")
    if isinstance(active, dict):
        kind = str(active.get("kind") or "").strip()
        agent = str(active.get("agent") or "").strip()
        awaiting = str(active.get("awaiting") or "").strip()
        phase = str(active.get("phase") or "").strip().lower()
        # Initiative pack sole-continue (dual as-is/to-be spine)
        if kind == "engagement_pack_plan" or kind.startswith("engagement_pack"):
            return PreDecideTurnOwner(
                OWNER_ENGAGEMENT_PACK,
                f"ledger_kind={kind}",
            )
        if kind == "input_state_setup":
            return PreDecideTurnOwner(
                OWNER_INPUT_STATE_SETUP,
                f"ledger_kind={kind}",
            )
        if kind == "workflow_build" or agent in (
            "workflow_builder", "workflow_editor",
        ):
            if awaiting and awaiting not in ("", "in_progress"):
                return PreDecideTurnOwner(
                    OWNER_WORKFLOW_BUILD,
                    f"ledger_awaiting={awaiting}",
                )
            if phase in {
                "role_proposal", "ir_review", "commit_plan", "domain_picker",
                "operational_data", "reviewing",
            }:
                return PreDecideTurnOwner(
                    OWNER_WORKFLOW_BUILD,
                    f"ledger_phase={phase}",
                )

    try:
        from api.services.conversation_control.multi_turn_stream_contract import (
            sole_continue_blocks_entity_resolve,
        )
        from api.services.conversation_control.task_pin_contract import (
            exclusive_owner_for_active_kind,
        )

        if sole_continue_blocks_entity_resolve(ctx, task_intent="continue"):
            mapped = exclusive_owner_for_active_kind(
                ctx, task_intent="continue",
            ) or OWNER_DEFAULT
            if mapped and mapped != "default":
                return PreDecideTurnOwner(
                    str(mapped),
                    "sole_continue_mid_flight",
                )
            kind = ""
            if isinstance(active, dict):
                kind = str(active.get("kind") or "").strip()
            if kind:
                return PreDecideTurnOwner(kind, "sole_continue_kind")
    except Exception:  # noqa: BLE001
        # Fail soft: sole-continue helpers must not break owner projection.
        return PreDecideTurnOwner(OWNER_DEFAULT, "sole_continue_probe_failed")

    return PreDecideTurnOwner(OWNER_DEFAULT, "greenfield")


def pre_decide_dispatch_allowed(
    owner: PreDecideTurnOwner | str,
    dispatch: str,
) -> bool:
    """True when this pre-decide dispatch may run under the projected owner.

    * **default / greenfield** — fail-open (all dispatches may match).
    * **sticky owners** — fail-closed: only ``STICKY_UNIVERSAL_OK`` +
      ``PRE_DECIDE_ALLOWED_EXTRA_BY_OWNER[owner]``.
    """
    oid = (
        owner.owner_id if isinstance(owner, PreDecideTurnOwner) else str(owner or "")
    ).strip() or OWNER_DEFAULT
    d = (dispatch or "").strip()
    if not d:
        return False
    if oid == OWNER_DEFAULT or oid not in STICKY_PRE_DECIDE_OWNERS:
        return True
    if d in STICKY_UNIVERSAL_OK:
        return True
    extra = PRE_DECIDE_ALLOWED_EXTRA_BY_OWNER.get(oid) or frozenset()
    return d in extra


def foreign_pre_decide_blocked(
    owner: PreDecideTurnOwner | str,
    dispatch: str,
) -> bool:
    """Inverse of :func:`pre_decide_dispatch_allowed`."""
    return not pre_decide_dispatch_allowed(owner, dispatch)


def project_and_allow(
    db: Any = None,
    *,
    tenant_id: str | None = None,
    conversation_id: str | None = None,
    context: Mapping[str, Any] | None = None,
    query: str = "",
    dispatch: str,
) -> tuple[PreDecideTurnOwner, bool]:
    """Convenience: project owner + whether dispatch is allowed."""
    owner = project_pre_decide_owner(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        context=context,
        query=query,
    )
    return owner, pre_decide_dispatch_allowed(owner, dispatch)


def scrub_ambient_identity_for_sticky_owner(
    context: Mapping[str, Any] | None,
    owner: PreDecideTurnOwner | str,
) -> dict[str, Any]:
    """Drop ambient last_read identity while a sticky owner holds the turn.

    After a past steal, ``last_read_workflow_*`` can still point at a foreign
    graph (Help Desk). Sticky authoring/sole-continue must not feed that into
    sim residual. Returns a shallow copy; leaves ledger ``active_task`` intact.
    """
    oid = (
        owner.owner_id if isinstance(owner, PreDecideTurnOwner) else str(owner or "")
    ).strip()
    ctx = dict(context) if isinstance(context, Mapping) else {}
    if oid not in STICKY_PRE_DECIDE_OWNERS:
        return ctx
    for k in (
        "last_read_workflow_id",
        "last_read_workflow_name",
        "last_read_project_id",
        "last_read_project_name",
    ):
        ctx.pop(k, None)
    # Authoring mid-ladder: drop ambient inspect cache (committed_read residue).
    if oid == OWNER_WORKFLOW_BUILD:
        wc = ctx.get("workflow_context")
        if isinstance(wc, dict) and str(wc.get("target_type") or "") in (
            "committed_read", "inspect",
        ):
            ctx.pop("workflow_context", None)
    return ctx


__all__ = [
    "FOREIGN_PRE_DECIDE_DISPATCHES",
    "OWNER_AGENT_COST",
    "OWNER_ADVISOR",
    "OWNER_COST_OUT",
    "OWNER_CYBER",
    "OWNER_DEFAULT",
    "OWNER_DRAFT",
    "OWNER_OUTCOME_VALUE",
    "OWNER_REALIZATION",
    "OWNER_SCORECARD",
    "OWNER_SURFACE_READ",
    "OWNER_WORKFLOW_BUILD",
    "OWNER_FINITE_PRE_DECIDE_OK",
    "OWNER_INPUT_STATE_SETUP",
    "PRE_DECIDE_ALLOWED_EXTRA_BY_OWNER",
    "PreDecideTurnOwner",
    "STICKY_PRE_DECIDE_OWNERS",
    "STICKY_UNIVERSAL_OK",
    "foreign_pre_decide_blocked",
    "pre_decide_dispatch_allowed",
    "project_and_allow",
    "project_pre_decide_owner",
    "scrub_ambient_identity_for_sticky_owner",
]
