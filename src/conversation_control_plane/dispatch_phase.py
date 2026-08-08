"""Code-owned authoring phase gates for Bot0 dispatch surfaces.

Workflow-surface read detours must not run when workflow_builder/editor
owns an in-progress authoring phase — pending markers + ledger are
authoritative (CAQ-10). This module is message-free and LLM-free.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

DetourKind = Literal["surface_read", "discovery", "orientation"]

_WORKFLOW_AUTHORING_AGENTS = frozenset({"workflow_builder", "workflow_editor"})

PHASE_COMMITTED = "committed_graph"
PHASE_OPERATIONAL_DATA = "operational_data"
PHASE_IR_REVIEW = "ir_review"
PHASE_ROLE_PROPOSAL = "role_proposal"
PHASE_DOMAIN_PICKER = "domain_picker"
PHASE_COMMIT_PLAN = "commit_plan"
PHASE_EXTRACTING = "extracting"
PHASE_GATHERING = "gathering"
PHASE_BUILDING = "building"
PHASE_EDITING = "editing"
PHASE_REVIEWING = "reviewing"

_AUTHORING_GATE_PHASES = frozenset({
    PHASE_IR_REVIEW,
    PHASE_ROLE_PROPOSAL,
    PHASE_DOMAIN_PICKER,
    PHASE_COMMIT_PLAN,
    PHASE_OPERATIONAL_DATA,
    PHASE_REVIEWING,
})

_PHASE_DISPLAY = {
    PHASE_EXTRACTING: "Extracting",
    PHASE_GATHERING: "Extracting",
    PHASE_IR_REVIEW: "Awaiting confirmation",
    PHASE_ROLE_PROPOSAL: "Role proposal",
    PHASE_DOMAIN_PICKER: "Domain picker",
    PHASE_OPERATIONAL_DATA: "Operational data",
    PHASE_COMMIT_PLAN: "Commit plan",
    PHASE_BUILDING: "Lowered to graph",
    PHASE_REVIEWING: "Awaiting confirmation",
    PHASE_EDITING: "Editing",
    PHASE_COMMITTED: "Graph validated",
}


def workflow_authoring_active(context: object) -> bool:
    """True when workflow_builder/editor owns the conversation turn (ledger only)."""
    if not isinstance(context, dict):
        return False
    from conversation_control_plane.task_phase_registry import (
        ledger_foreground_agent,
    )

    return ledger_foreground_agent(context) in _WORKFLOW_AUTHORING_AGENTS


def builder_pending_pk(tenant_id: str, conversation_id: str) -> str:
    return f"{tenant_id}:bld_{conversation_id}"


def reconcile_authoring_gate_flags(pending: dict[str, Any] | None) -> dict[str, Any] | None:
    """Heal dual-flag drift so Staffed IR / IR / commit gates stay armed.

    conv_5e8d3caa: ``_state`` stayed ``awaiting_role_proposal_review`` while
    ``_awaiting_role_proposal_review`` was cleared on a failed leave — routing
    then treated the turn as free bot0 chat and ``get_project_staffing`` used
    the *draft workflow name* as a project (hallucinated miss).
    """
    if not isinstance(pending, dict) or not pending:
        return pending
    st = str(pending.get("_state") or "").strip().lower()
    if st == "awaiting_role_proposal_review" or pending.get("_awaiting_role_proposal_review"):
        pending["_awaiting_role_proposal_review"] = True
    if st == "awaiting_ir_confirmation" or pending.get("_awaiting_ir_confirmation"):
        pending["_awaiting_ir_confirmation"] = True
    if st == "awaiting_commit_confirmation" or pending.get("_awaiting_commit_confirmation"):
        pending["_awaiting_commit_confirmation"] = True
    # Domain gate: dual-flag heal (conv_d94e7043 purity — coarse phase alone
    # dropped domain / commit / staffed awaiting from ledger projection).
    if st == "awaiting_domain" or pending.get("_awaiting_domain_choice"):
        pending["_awaiting_domain_choice"] = True
        if st != "awaiting_domain":
            pending["_state"] = "awaiting_domain"
    return pending


def load_builder_pending_state(
    db: Any,
    tenant_id: str | None,
    conversation_id: str | None,
) -> dict[str, Any] | None:
    if not db or not tenant_id or not conversation_id:
        return None
    try:
        import json

        from sqlalchemy import text

        row = db.execute(
            text("SELECT state FROM workflow_builder_pending WHERE pk = :pk"),
            {"pk": builder_pending_pk(tenant_id, conversation_id)},
        ).fetchone()
        if not row or not row[0]:
            return None
        state = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        if not isinstance(state, dict) or not state:
            return None
        return reconcile_authoring_gate_flags(state)
    except Exception:  # noqa: BLE001 — best-effort projection, never raises
        return None


def project_fine_authoring_phase(pending: dict[str, Any] | None) -> str | None:
    """Map durable builder pending to a routing-safe fine phase."""
    if not pending:
        return None
    pending = reconcile_authoring_gate_flags(pending) or pending
    if pending.get("_awaiting_post_commit_clarification"):
        return PHASE_EDITING
    # Live IR gate beats post-save committed stamp. Dual to-be re-open after
    # commit left _committed=true + _awaiting_ir_confirmation=true; projecting
    # COMMITTED first made invent/New plan miss the gate and freestyle
    # "Topology Fix Proposed" under pack plan_act (conv_6a6dbadb msg80).
    if pending.get("_awaiting_ir_confirmation"):
        return PHASE_IR_REVIEW
    if pending.get("_committed") or pending.get("workflow_created"):
        return PHASE_COMMITTED
    if pending.get("_awaiting_operational_data"):
        return PHASE_OPERATIONAL_DATA
    st = str(pending.get("_state") or "").strip().lower()
    if pending.get("_awaiting_role_proposal_review") or st == "awaiting_role_proposal_review":
        return PHASE_ROLE_PROPOSAL
    # Domain before commit in projection order — commit must not hide an open domain gate.
    from agent.workflow_builder.domain_picker_renderer import domain_authoring_gate_open

    if (
        domain_authoring_gate_open(pending)
        or pending.get("_awaiting_domain_choice")
        or st == "awaiting_domain"
    ):
        return PHASE_DOMAIN_PICKER
    if pending.get("_awaiting_commit_confirmation") or st == "awaiting_commit_confirmation":
        from agent.workflow_builder.commit_readiness import is_commit_plan_ready

        if is_commit_plan_ready(pending):
            return PHASE_COMMIT_PLAN

    from agent.workflow_builder.state import project_coarse_phase

    coarse = project_coarse_phase(pending)
    if coarse == "committed":
        return PHASE_COMMITTED
    if coarse == "editing":
        return PHASE_EDITING
    if coarse == "gathering":
        return PHASE_GATHERING
    if coarse == "building":
        return PHASE_BUILDING
    if coarse == "reviewing":
        return PHASE_REVIEWING
    return None


def ledger_phase_awaiting_from_pending(
    pending: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    """Map builder pending → ledger ``phase`` + ``awaiting`` (not null while gated).

    Chat/worker often lagged: pending had ``_awaiting_domain_choice`` while
    ledger stayed ``phase=active`` / ``awaiting=null`` so A18 owner projection
    and free-text domain bind missed (conv_dde29c0f class). Same package as the
    domain picker card must stamp ledger ``phase=domain_picker``, ``awaiting=domain``.
    """
    if not isinstance(pending, dict) or not pending:
        return None, None
    fine = project_fine_authoring_phase(pending)
    if not fine:
        return None, None
    # Ledger awaiting tokens (must match bot0 authoring-gate heal + pre_decide).
    awaiting_map = {
        PHASE_ROLE_PROPOSAL: "role_proposal_review",
        PHASE_IR_REVIEW: "ir_confirmation",
        PHASE_DOMAIN_PICKER: "domain",
        PHASE_COMMIT_PLAN: "commit_confirmation",
        PHASE_OPERATIONAL_DATA: "operational_data",
    }
    awaiting = awaiting_map.get(fine)
    # Staffed gate historically used coarse phase=active with awaiting set.
    phase = "active" if fine == PHASE_ROLE_PROPOSAL else fine
    return phase, awaiting


def _workflow_name_and_task_count(pending: dict[str, Any]) -> tuple[str, int]:
    """Best-effort name + task count from builder pending (IR or lowered nodes)."""
    nodes = pending.get("nodes") or []
    task_count = len([
        n for n in nodes
        if isinstance(n, dict) and (n.get("label") or "").strip() not in ("", "Start", "End")
    ])
    name = (pending.get("workflow_name") or "").strip()
    if not task_count:
        ir = pending.get("_workflow_ir")
        if isinstance(ir, dict):
            ir_tasks = ((ir.get("topology") or {}).get("tasks")) or []
            if isinstance(ir_tasks, list) and ir_tasks:
                task_count = len(ir_tasks)
                if not name:
                    name = (ir.get("workflow_name") or "").strip()
    return name, task_count


def display_phase_for_authoring(phase: str | None, pending: dict[str, Any] | None = None) -> str:
    """User-facing phase label for orientation cards."""
    phase = (phase or "").strip()
    if phase == PHASE_IR_REVIEW and isinstance(pending, dict):
        if isinstance(pending.get("_workflow_ir"), dict) and not pending.get("nodes"):
            return "Tasks extracted (IR)"
    return _PHASE_DISPLAY.get(phase, phase)


def next_step_for_authoring_phase(phase: str | None, pending: dict[str, Any] | None = None) -> str:
    """Code-owned next-step hint keyed by fine authoring phase."""
    phase = (phase or "").strip()
    if phase == PHASE_IR_REVIEW:
        return "Review the tasks and roles, then reply **yes** to build it."
    if phase == PHASE_ROLE_PROPOSAL:
        return (
            "Reply **accept** or **go ahead** to use the ★ roles, **skip** to name "
            "them yourself, or **try again** for new suggestions."
        )
    if phase == PHASE_DOMAIN_PICKER:
        candidates = (pending or {}).get("_domain_candidates") or []
        if candidates:
            return (
                "Pick the catalog domain — reply with the **number** "
                "(e.g. **1**) or the **domain name**. "
                "Then roles, graph compile, and commit-plan review before save."
            )
        return (
            "Pick the industry domain — reply with the number or name. "
            "Then roles, graph compile, and commit-plan review before save."
        )
    if phase == PHASE_OPERATIONAL_DATA:
        return (
            "Paste one **headline metric with a number** "
            "(e.g. `1,000 leads/quarter`), or reply **skip**."
        )
    if phase == PHASE_COMMIT_PLAN:
        from agent.workflow_builder.commit_readiness import is_commit_plan_ready

        if isinstance(pending, dict) and not is_commit_plan_ready(pending):
            return (
                "Session graph is not ready — say **interpret** to rebuild, or "
                "**start over** for a clean session."
            )
        return "Reply **yes** to save the workflow, or edit any details first."
    if phase == PHASE_REVIEWING:
        return "Reply **yes** to build the workflow into a graph."
    if phase == PHASE_BUILDING:
        return "Review the graph, then save the workflow."
    if phase == PHASE_COMMITTED:
        return "Reply **save** to commit the workflow."
    if phase == PHASE_EXTRACTING or phase == PHASE_GATHERING:
        return "I'm interpreting your workflow — hang tight."
    return ""


def project_authoring_snapshot(pending: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project durable builder pending into orientation/routing snapshot fields."""
    if not pending:
        return None
    phase = project_fine_authoring_phase(pending)
    if not phase or phase == PHASE_COMMITTED:
        return None
    name, task_count = _workflow_name_and_task_count(pending)
    if not name and not task_count and not pending.get("_awaiting_ir_confirmation"):
        return None
    display = display_phase_for_authoring(phase, pending)
    if phase == PHASE_IR_REVIEW and isinstance(pending.get("_workflow_ir"), dict) and not pending.get("nodes"):
        display = "Tasks extracted (IR)"
    from agent.workflow_builder.domain_picker_renderer import domain_authoring_gate_open

    return {
        "authoring_phase": phase,
        "display_phase": display,
        "next_step": next_step_for_authoring_phase(phase, pending),
        "workflow_name": name,
        "task_count": task_count,
        "ir_confirmed": bool(pending.get("_ir_confirmed")),
        "domain_gate_open": domain_authoring_gate_open(pending),
        "committed": bool(pending.get("_committed") or pending.get("workflow_created")),
    }


def authoring_resume_in_progress(pending: dict[str, Any] | None) -> bool:
    """True when builder pending holds a non-committed in-flight workflow."""
    if not pending:
        return False
    if pending.get("_committed") or pending.get("workflow_created"):
        return False
    return bool(
        pending.get("nodes")
        or pending.get("_workflow_ir")
        or pending.get("_awaiting_ir_confirmation")
        or pending.get("_awaiting_role_proposal_review")
        or pending.get("_awaiting_commit_confirmation")
        or pending.get("_awaiting_operational_data")
        or pending.get("_source_prompt")
        or pending.get("_drafting_handoff")
        or (
            str(pending.get("_state") or "").strip()
            and not pending.get("_committed")
        )
    )


def _unified_signals_authoring_resume(signal: object) -> bool:
    """True when the unified router labeled a status-orientation turn (not gate proceed)."""
    if signal is None:
        return False
    dk = str(getattr(signal, "discovery_kind", None) or "").strip().lower()
    of = str(getattr(signal, "orientation_focus", None) or "").strip().lower()
    ca = str(getattr(signal, "control_act", None) or "").strip().lower()
    return (dk == "orientation" and of == "status") or ca == "resume"


def authoring_snapshot_ledger_payload(
    pending: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Compact payload slice persisted on active_task.payload.

    Includes multi-gate projection (phase + gates.*.armed/satisfied) so front
    door and agent agree — authoring_gate_contract / SDK B4.
    """
    snap = project_authoring_snapshot(pending)
    if not snap:
        return None
    from conversation_control_plane.authoring_gate_contract import (
        authoring_gate_ledger_slice,
    )

    gate_slice = authoring_gate_ledger_slice(pending)
    return {
        "authoring_phase": snap["authoring_phase"],
        # Canonical coarse phase for multi-turn stream (prefer gate-derived).
        "phase": gate_slice.get("phase") or snap["authoring_phase"],
        "gates": gate_slice.get("gates") or {},
        "staffed_ir_satisfied": gate_slice.get("staffed_ir_satisfied"),
        "next_step": snap["next_step"],
        "workflow_name": snap["workflow_name"],
        "task_count": snap["task_count"],
        "domain_gate_open": snap["domain_gate_open"],
        "ir_confirmed": snap["ir_confirmed"],
    }


def sync_authoring_snapshot_to_ledger(
    db: Any,
    tenant_id: str,
    conversation_id: str,
    *,
    context: object = None,
) -> dict[str, Any] | None:
    """Write authoring snapshot to active_task.payload; merge into context when supplied."""
    if not db or not tenant_id or not conversation_id:
        return None
    ctx = context if isinstance(context, dict) else {}
    active = ctx.get("active_task")
    if not isinstance(active, dict) or not workflow_authoring_active(ctx):
        return None
    payload = authoring_snapshot_ledger_payload(
        load_builder_pending_state(db, tenant_id, conversation_id),
    )
    if not payload:
        return None
    agent = str(active.get("agent") or "workflow_builder").strip()
    try:
        from conversation_control_plane.ledger import update_phase

        _pend = load_builder_pending_state(db, tenant_id, conversation_id)
        _phase_from_pend, _awaiting_from_pend = ledger_phase_awaiting_from_pending(
            _pend,
        )
        _ledger_phase = str(
            _phase_from_pend
            or payload.get("phase")
            or payload.get("authoring_phase")
            or active.get("phase")
            or "active"
        )
        _ledger_awaiting = (
            _awaiting_from_pend
            if _awaiting_from_pend is not None
            else active.get("awaiting")
        )
        task = update_phase(
            db,
            tenant_id,
            conversation_id,
            agent=agent,
            phase=_ledger_phase,
            awaiting=_ledger_awaiting,
            pending_ref=active.get("pending_ref"),
            payload=payload,
        )
        if isinstance(task, dict):
            ctx["active_task"] = task
    except Exception:  # noqa: BLE001 — projection must never block routing
        logger.debug("authoring snapshot ledger sync failed", exc_info=True)
        ctx_active = dict(active)
        ctx_active["payload"] = payload
        ctx["active_task"] = ctx_active
    return payload


def resume_authoring_owns_turn(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str | None,
    query: str,
    context: object = None,
    unified_signal: object = None,
    messages: list | None = None,
) -> bool:
    """True when an active builder session should answer with orientation/status."""
    from conversation_control_plane.authoring_gate_turn import (
        resume_authoring_owns_turn as _contract_resume_authoring_owns_turn,
    )

    if not conversation_id or not (query or "").strip():
        return False
    try:
        from conversation_control_plane.prose_intake_contract import (
            grounded_glossary_detour_query,
        )

        if grounded_glossary_detour_query(
            query, db=db, tenant_id=tenant_id, history=messages,
        ):
            return False
    except Exception:  # noqa: BLE001 — glossary probe never blocks authoring resume
        logger.debug("glossary detour probe skipped", exc_info=True)
    if not workflow_authoring_active(context):
        return False
    pending = load_builder_pending_state(db, tenant_id, conversation_id)
    if not authoring_resume_in_progress(pending):
        return False
    if _unified_signals_authoring_resume(unified_signal):
        phase = project_fine_authoring_phase(pending)
        if phase in _AUTHORING_GATE_PHASES:
            return False
        try:
            from conversation_control_plane.orientation import (
                classify_orientation_request,
            )

            return classify_orientation_request(
                db, tenant_id, query, messages=messages,
            )
        except Exception:  # noqa: BLE001
            return True
    return _contract_resume_authoring_owns_turn(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        query=query,
        context=context,
        unified_signal=unified_signal,
        messages=messages,
    )


def load_workflow_authoring_phase(
    db: Any,
    tenant_id: str | None,
    conversation_id: str | None,
    *,
    context: object = None,
) -> str | None:
    """Return fine authoring phase when workflow_builder/editor is active."""
    if not workflow_authoring_active(context):
        return None
    return project_fine_authoring_phase(
        load_builder_pending_state(db, tenant_id, conversation_id),
    )


def surface_read_detour_suppressed(
    authoring_phase: str | None,
    *,
    context: object = None,
    task_intent: str | None = None,
) -> bool:
    """True when the workflow-surface read detour must not run.

    Suppresses when:
    * builder/editor authoring is active and not yet committed (CAQ-10), or
    * ledger sole-continue owns the turn (drafting refine, cost-out, …) so
      greenfield O&V / library open cannot steal (conv_80523a09).
    """
    if workflow_authoring_active(context):
        if authoring_phase is None:
            # Builder/editor is active but pending could not be loaded — still
            # suppress saved-workflow detours so KPI/IR turns stay in-builder.
            return True
        if authoring_phase != PHASE_COMMITTED:
            return True
    # Sole-continue drafting (and sibling kinds) — not builder-agent-keyed.
    try:
        from conversation_control_plane.task_pin_contract import (
            sole_continue_suppresses_surface_read,
        )

        active = None
        if isinstance(context, dict):
            cand = context.get("active_task")
            active = cand if isinstance(cand, dict) else None
            if task_intent is None:
                task_intent = str(context.get("task_intent") or "continue")
        if sole_continue_suppresses_surface_read(
            active, task_intent=task_intent,
        ):
            return True
    except Exception:  # noqa: BLE001 — never break routing on suppress helper
        import logging

        logging.getLogger(__name__).debug(
            "sole_continue surface suppress helper failed", exc_info=True,
        )
    return False


def active_agent_task_blocks_detour(
    detour_kind: DetourKind,
    *,
    db: Any = None,
    tenant_id: str | None = None,
    conversation_id: str | None = None,
    query: str = "",
    context: object = None,
    authoring_phase: str | None = None,
    task_intent: str | None = None,
) -> bool:
    """Single facade: active authoring task owns the turn — block competing detours.

    ``surface_read`` — saved-workflow read classifier must not fire mid-IR /
    mid-drafting sole-continue.
    ``discovery`` / ``orientation`` — front-door cognition must not steal gate replies.
    """
    if detour_kind == "surface_read":
        return surface_read_detour_suppressed(
            authoring_phase, context=context, task_intent=task_intent,
        )
    if detour_kind in ("discovery", "orientation"):
        return discovery_cognition_suppressed(
            db, tenant_id, conversation_id, query, context=context,
        )
    return False


# Finite-grammar gate replies — **single SoT** = finite_confirm_grammar
# (not a parallel synonym table). Bare "yes" at IR/commit reaches decide_turn
# instead of discovery orientation (conv_7a953788).
from conversation_control_plane.finite_confirm_grammar import (  # noqa: E402
    GATE_REPLY_ALIASES as _GATE_REPLY_ALIASES,
    WORKFLOW_GATE_REPLY_EXACT as WORKFLOW_CONFIRMATION_REPLIES,
    normalize_short_gate_reply,
)

# Menu tokens for Staffed IR (role proposal review).
ROLE_PROPOSAL_MENU_REPLIES = frozenset({
    "accept", "skip", "try again",
})

# Natural advance affirmatives at the armed Staffed IR gate — same finite
# control-token class as Draft IR structure confirm (not free-text NL cognition).
# Staging conv_96197869: user said "Go ahead" after Staffed IR; only the menu
# word "accept" was recognized → card re-rendered.
ROLE_PROPOSAL_DECLINE_REPLIES = frozenset({
    "no", "n", "nope", "cancel", "stop", "skip", "reject",
})
ROLE_PROPOSAL_REPROPOSE_REPLIES = frozenset({
    "try again", "repropose",
})
# Staffed leave tokens only — not structure-chip "lets continue" (conv_882a6234).
# Align with authoring_gate_contract.STAFFED_MENU_ACCEPT.
ROLE_PROPOSAL_ACCEPT_REPLIES = frozenset({
    "accept",
    "go ahead",
    "yes",
    "y",
    "ok",
    "okay",
    "sure",
})
# Structural gate ownership: menu + natural accept (authoring_gate_turn).
ROLE_PROPOSAL_REPLIES = (
    ROLE_PROPOSAL_MENU_REPLIES
    | ROLE_PROPOSAL_ACCEPT_REPLIES
    | ROLE_PROPOSAL_REPROPOSE_REPLIES
)


# Prefer task_pin_contract.KINDS_PREEMPT_POST_SAVE_OV_STATUS (S8) — kept as
# alias for older imports.
def _ledger_kinds_preempt_post_save_status() -> frozenset[str]:
    try:
        from conversation_control_plane.task_pin_contract import (
            KINDS_PREEMPT_POST_SAVE_OV_STATUS,
        )

        return KINDS_PREEMPT_POST_SAVE_OV_STATUS | frozenset({"workflow_pick"})
    except Exception:  # noqa: BLE001
        return frozenset({
            "drafting",
            "realization_intake",
            "workflow_pick",
            "cost_out",
            "cyber_risk_assessment",
            "project_workspace",
            "scorecard_interrogate",
        })


_LEDGER_KINDS_PREEMPT_POST_SAVE_STATUS = _ledger_kinds_preempt_post_save_status()


def post_save_status_orientation_suppressed(
    *,
    context: object = None,
    orientation_focus: str | None = None,
    discovery: dict[str, str] | None = None,
) -> bool:
    """True when ledger inventory must win over post-save O&V status copy.

    ``build_post_save_workflow_status_response`` keys off ``last_read_workflow_id``
    and always narrates Outcome & Value Model progress. That is correct only when
    the ledger's active task is ``outcome_value_setup`` (or no competing intake task).
    Realization deploy walkthrough, drafting, catalog-role, scorecard list asks, and
    workflow authoring must reach ``compose_orientation_response`` or discovery detours.
    """
    from conversation_control_plane.discovery_intent import (
        DISCOVERY_DETOUR_KINDS,
    )
    from conversation_control_plane.task_pin_contract import (
        post_save_ov_status_blocked_by_sole_continue,
    )

    disc_kind = ((discovery or {}).get("kind") or "").strip()
    if disc_kind in DISCOVERY_DETOUR_KINDS:
        return True

    focus = (
        (orientation_focus or (discovery or {}).get("orientation_focus") or "")
        .strip()
        .lower()
    )
    if focus == "active_session":
        return True

    ctx = context if isinstance(context, dict) else {}
    # S8 sole-continue substrate — cost/cyber/project/draft/realization, etc.
    if post_save_ov_status_blocked_by_sole_continue(ctx):
        return True

    active = ctx.get("active_task") or {}
    if not isinstance(active, dict):
        return False

    kind = (active.get("kind") or "").strip()
    if kind == "outcome_value_setup":
        return False
    if kind in _ledger_kinds_preempt_post_save_status():
        return True

    agent = (active.get("agent") or "").strip()
    if agent == "catalog_role_create":
        return True
    if workflow_authoring_active(ctx):
        return True
    return False


def outcome_value_setup_orientation_suppressed(
    db: Any,
    tenant_id: str | None,
    query: str,
    *,
    context: object = None,
    messages: list | None = None,
    unified_task_intent: str | None = None,
) -> bool:
    """True when the user is resuming business scorecard collection.

    Discovery orientation (improvement menu / status card) must not steal
    "go back to what we were doing" while ``kind=outcome_value_setup`` is
    still active on the ledger.
    """
    ctx = context if isinstance(context, dict) else {}
    active = ctx.get("active_task") or {}
    if not isinstance(active, dict) or active.get("kind") != "outcome_value_setup":
        return False
    if not (query or "").strip() or db is None or not tenant_id:
        return False
    intent = (unified_task_intent or "").strip().lower()
    if intent in ("continue", "resume"):
        return True
    return False


def discovery_orientation_suppressed(
    db: Any,
    tenant_id: str | None,
    conversation_id: str | None,
    query: str,
    *,
    context: object = None,
) -> bool:
    """True when a workflow authoring gate owns this finite-grammar reply.

    Discovery/orientation cognition must not run before decide_turn on these
    turns — the LLM classifier misread bare affirmatives as status/orientation
    asks (conv_7a953788: "yes" after IR confirmation → sessions card).
    """
    if not (query or "").strip() or not workflow_authoring_active(context):
        return False
    phase = load_workflow_authoring_phase(
        db, tenant_id, conversation_id, context=context,
    )
    if phase is None or phase == PHASE_COMMITTED:
        return False
    reply = normalize_short_gate_reply(query)
    if not reply:
        return False
    if phase == PHASE_ROLE_PROPOSAL:
        return reply in ROLE_PROPOSAL_REPLIES
    if phase in (PHASE_IR_REVIEW, PHASE_REVIEWING):
        return reply in WORKFLOW_CONFIRMATION_REPLIES
    if phase == PHASE_DOMAIN_PICKER:
        return True
    if phase == PHASE_OPERATIONAL_DATA:
        # Entire KPI gate is builder-owned — bot0 detours must not steal replies
        # (conv_7ba3b870: KPI values and "I already entered…" fell through to
        # orchestrator prose that fabricated a save without workflow_id).
        return True
    return False


def router_supersedes_discovery(route: object | None) -> bool:
    """Discovery/orientation are informative detours — only when the intent router stays on bot0.

    The L3 intent router (plus its L1/L2 accelerators that still LLM-arbitrate) owns
    build/edit/handoff routing. When it names a specialist or ambiguous clarifier path,
    skip discovery so we do not stack a second NL classifier with edge-case guards.

    Latency (epic #1e / CAQ-1c Pillar 3, pre-S4): also skip discovery when the router
    already resolved a bot0 turn via a cheap layer or a structured detour signal — the
    orchestrator or a code-owned detour owns the answer; discovery would be redundant.
    """
    if route is None:
        return False
    intent = str(getattr(route, "intent", None) or "bot0").strip().lower()
    if intent != "bot0":
        return True
    if getattr(route, "workflow_draft_request", False):
        return True
    if getattr(route, "catalog_role_request", False):
        return True
    if getattr(route, "attachment_capability_request", False):
        return True
    if getattr(route, "cost_estimate_request", False):
        return True
    layer = str(getattr(route, "layer", None) or "").strip().lower()
    if layer in {"l2_trivial", "gate_continue"}:
        return True
    return False


def read_intent_cognition_needed(
    *,
    route: object | None,
    read_detour_active: bool,
    workflow_surface_context_ready: bool,
) -> bool:
    """Whether ``conversation_read_intent_classifier`` must run this turn.

    Saved-workflow surface reads need the classifier when a sticky heavy agent is
    active or the conversation already carries a workflow referent (recent list,
    last-read id). Cold bot0 concept/product turns defer to discovery +
    decide_turn/orchestrator — avoids ~1s serial preamble on every front-door Q&A.
    """
    if read_detour_active or workflow_surface_context_ready:
        return True
    return False


def operational_data_provision_shape(query: str) -> bool:
    """Structural shape: headline KPI gate expects a numeric target in the reply."""
    return any(ch.isdigit() for ch in (query or ""))


def operational_data_kpi_gate_open(
    pending: dict[str, Any] | None,
    *,
    context: object = None,
) -> bool:
    """True when the optional top-line KPI step is the active authoring gate."""
    if pending and pending.get("_awaiting_operational_data"):
        return True
    ctx = context if isinstance(context, dict) else {}
    active = ctx.get("active_task") if isinstance(ctx.get("active_task"), dict) else {}
    if str(active.get("awaiting") or "").strip() == PHASE_OPERATIONAL_DATA:
        return True
    if not pending:
        return False
    if pending.get("_committed") or pending.get("workflow_created"):
        return False
    if pending.get("operational_data") or pending.get("_operational_data_reviewed"):
        return False
    if pending.get("_operational_data_skipped"):
        return False
    if not (pending.get("_resolved_domain_id") or pending.get("domain") or "").strip():
        return False
    if not (pending.get("workflow_name") or "").strip():
        return False
    if not (pending.get("nodes") or pending.get("_graph_validated")):
        return False
    # Commit plan may still be flagged while the KPI prompt is on screen.
    return bool(pending.get("_awaiting_commit_confirmation"))


def operational_data_gate_owns_provision_turn(
    db: Any,
    *,
    tenant_id: str | None,
    conversation_id: str | None,
    query: str,
    context: object = None,
    messages: list | None = None,
) -> bool:
    """True when the open top-line KPI gate should stay on workflow_builder."""
    from conversation_control_plane.authoring_gate_turn import (
        operational_data_gate_owns_provision_turn as _contract_kpi_gate_owns_turn,
    )

    return _contract_kpi_gate_owns_turn(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        query=query,
        context=context,
        messages=messages,
    )


def discovery_detour_supersedes_active_flow(
    *,
    discovery: dict[str, str] | None = None,
    unified_signal: object | None = None,
    plan: object | None = None,
) -> bool:
    """True when a router-owned front-door detour must beat an active guided flow."""
    from conversation_control_plane.delivery_order_contract import (
        front_door_detour_supersedes_active_flow,
    )

    return front_door_detour_supersedes_active_flow(
        discovery=discovery,
        unified_signal=unified_signal,
        plan=plan,
    )


def discovery_cognition_suppressed(
    db: Any,
    tenant_id: str | None,
    conversation_id: str | None,
    query: str,
    *,
    context: object = None,
    messages: list | None = None,
) -> bool:
    """Skip discovery/orientation LLM when authoring owns the turn.

    Not only finite-token gate replies — open Staffed IR / IR / domain / commit
    must suppress discovery so free-text like "show me the staffing again"
    cannot become intent_clarify (process-first pack) or orientation (conv_5e8d3caa).
    """
    if discovery_orientation_suppressed(
        db, tenant_id, conversation_id, query, context=context,
    ):
        return True
    if operational_data_gate_owns_provision_turn(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        query=query,
        context=context,
        messages=messages,
    ):
        return True
    # Pending-authority: open pre-commit gates own free-text continues.
    pending = load_builder_pending_state(db, tenant_id, conversation_id)
    pending = reconcile_authoring_gate_flags(pending) if pending else None
    phase = project_fine_authoring_phase(pending)
    if phase in _AUTHORING_GATE_PHASES:
        return True
    ctx = context if isinstance(context, dict) else {}
    active = ctx.get("active_task")
    if not isinstance(active, dict):
        return False
    # Ledger sole-continue on workflow_build: suppress front-door discovery.
    kind = str(active.get("kind") or "").strip()
    agent = str(active.get("agent") or "").strip()
    if kind == "workflow_build" or agent in ("workflow_builder", "workflow_editor"):
        awaiting = str(active.get("awaiting") or "").strip()
        if awaiting and awaiting not in ("", "in_progress"):
            return True
        # phase=role_proposal even when awaiting string differs
        ph = str(active.get("phase") or "").strip().lower()
        if ph in {
            "role_proposal", "ir_review", "commit_plan", "domain_picker",
            "operational_data", "reviewing",
        }:
            return True
    awaiting = str(active.get("awaiting") or "").strip()
    if not awaiting or awaiting == "in_progress":
        return False
    reply = normalize_short_gate_reply(query)
    return bool(reply and reply in WORKFLOW_CONFIRMATION_REPLIES)


def authoring_gate_proceed_owns_turn(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str | None,
    query: str,
    context: object = None,
    unified_signal: object = None,
    messages: list | None = None,
) -> bool:
    """True when an open authoring gate should advance via workflow_builder."""
    from conversation_control_plane.authoring_gate_turn import (
        authoring_gate_proceed_owns_turn as _contract_gate_proceed_owns_turn,
    )

    return _contract_gate_proceed_owns_turn(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        query=query,
        context=context,
        unified_signal=unified_signal,
        messages=messages,
    )


def domain_gate_owns_pick_turn(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str | None,
    query: str,
    context: object = None,
) -> bool:
    """True when the domain picker is up and the reply is a finite menu pick."""
    if not conversation_id or not (query or "").strip():
        return False
    if not workflow_authoring_active(context):
        return False
    pending = load_builder_pending_state(db, tenant_id, conversation_id)
    if not isinstance(pending, dict):
        return False
    from agent.workflow_builder.domain_picker_renderer import (
        matches_domain_authoring_pick,
    )

    return matches_domain_authoring_pick(query, pending)


def domain_gate_owns_authoring_turn(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str | None,
    query: str,
    context: object = None,
) -> bool:
    """True when the domain gate is open — workflow_builder owns the turn."""
    if not conversation_id or not (query or "").strip():
        return False
    if not workflow_authoring_active(context):
        return False
    pending = load_builder_pending_state(db, tenant_id, conversation_id)
    if not isinstance(pending, dict):
        return False
    from agent.workflow_builder.domain_picker_renderer import domain_authoring_gate_open

    return domain_authoring_gate_open(pending)


def domain_picker_blocks_inventory_soft_name(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str | None,
    context: object = None,
    query: str = "",
) -> bool:
    """conv_5e398f46: domain_picker exclusive over inventory soft-name.

    When the industry-domain card is armed, free-text replies (typed label or
    number) must bind via ``resolve_offered_domain_pick`` on the builder path —
    never tenant inventory soft-name ("Customer management" → 10 workflows).
    """
    return domain_gate_owns_authoring_turn(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        query=query or "domain",  # non-empty so gate check runs
        context=context,
    )


def authoring_gate_blocks_inventory_resolve(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str | None,
    context: object = None,
    query: str = "",
) -> bool:
    """Open pre-commit authoring gates exclusive over inventory short-circuit.

    Domain / Staffed IR / IR / KPI / commit must not lose free-text to
    ``inventory_name_resolve`` / inspect-saved (conv_e0008ce7: KPI labels
    without a number → Help Desk invalid graph; conv_5e398f46 domain).
    """
    if domain_picker_blocks_inventory_soft_name(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        context=context,
        query=query or "gate",
    ):
        return True
    pending = load_builder_pending_state(db, tenant_id, conversation_id)
    pending = reconcile_authoring_gate_flags(pending) if pending else None
    if operational_data_kpi_gate_open(pending, context=context):
        return True
    phase = project_fine_authoring_phase(pending)
    if phase in _AUTHORING_GATE_PHASES:
        return True
    ctx = context if isinstance(context, dict) else {}
    active = ctx.get("active_task")
    if not isinstance(active, dict):
        return False
    kind = str(active.get("kind") or "").strip()
    agent = str(active.get("agent") or "").strip()
    if kind != "workflow_build" and agent not in (
        "workflow_builder", "workflow_editor",
    ):
        return False
    awaiting = str(active.get("awaiting") or "").strip()
    if awaiting and awaiting not in ("", "in_progress"):
        return True
    ph = str(active.get("phase") or "").strip().lower()
    return ph in {
        "role_proposal", "ir_review", "commit_plan", "domain_picker",
        "operational_data", "reviewing",
    }


def exclusive_owner_blocks_inventory_early(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str | None,
    context: object = None,
    query: str = "",
) -> bool:
    """Host-level: open exclusive owner blocks pre-decide inventory name/soft.

    **Implementation:** :func:`pre_decide_owner_contract.project_and_allow` —
    not a growing ``if open_X: skip inventory`` laundry. Same rule denies
    ``workflow_simulation_entry_early`` and other foreign pre-decide leaves.
    """
    try:
        from conversation_control_plane.pre_decide_owner_contract import (
            foreign_pre_decide_blocked,
            project_pre_decide_owner,
        )

        owner = project_pre_decide_owner(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            context=context if isinstance(context, dict) else None,
            query=query or "",
        )
        return foreign_pre_decide_blocked(owner, "inventory_name_resolve")
    except Exception:  # noqa: BLE001
        # Fail closed on open authoring only (legacy path).
        return bool(
            authoring_gate_blocks_inventory_resolve(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                context=context,
                query=query,
            ),
        )


def exclusive_owner_blocks_foreign_pre_decide(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str | None,
    context: object = None,
    query: str = "",
    dispatch: str,
) -> bool:
    """True when projected owner denies this pre-decide dispatch (A18 seal)."""
    try:
        from conversation_control_plane.pre_decide_owner_contract import (
            foreign_pre_decide_blocked,
            project_pre_decide_owner,
        )

        owner = project_pre_decide_owner(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            context=context if isinstance(context, dict) else None,
            query=query or "",
        )
        return foreign_pre_decide_blocked(owner, dispatch)
    except Exception:  # noqa: BLE001
        return False


def ir_gate_owns_role_proposal_turn(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str | None,
    query: str,
    context: object = None,
) -> bool:
    """True when IR review awaits roles and the user asked to propose them."""
    if not conversation_id or not (query or "").strip():
        return False
    phase = load_workflow_authoring_phase(
        db, tenant_id, conversation_id, context=context,
    )
    if phase != PHASE_IR_REVIEW:
        return False
    pending = load_builder_pending_state(db, tenant_id, conversation_id)
    if not isinstance(pending, dict) or not pending.get("_awaiting_ir_confirmation"):
        return False
    from api.services.workflow_role_proposer import classify_propose_roles_request

    return classify_propose_roles_request(db, tenant_id, query=query)


def synthesize_gate_continue_route(
    db: Any,
    tenant_id: str | None,
    conversation_id: str | None,
    query: str,
    *,
    context: object = None,
    messages: list | None = None,
):
    """Code-owned route for finite gate continues — avoids a redundant classify."""
    if domain_gate_owns_pick_turn(
        db,
        tenant_id=tenant_id or "",
        conversation_id=conversation_id,
        query=query,
        context=context,
    ):
        from api.services.bot0_intent_router import IntentRoute

        return IntentRoute(
            intent="workflow_builder",
            layer="gate_continue",
            reason="finite domain picker reply continues active workflow session",
            confidence=1.0,
        )
    if operational_data_gate_owns_provision_turn(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        query=query,
        context=context,
        messages=messages,
    ):
        from api.services.bot0_intent_router import IntentRoute

        return IntentRoute(
            intent="workflow_builder",
            layer="gate_continue",
            reason="finite headline KPI reply continues active workflow session",
            confidence=1.0,
        )
    if not discovery_cognition_suppressed(
        db, tenant_id, conversation_id, query, context=context, messages=messages,
    ):
        return None
    ctx = context if isinstance(context, dict) else {}
    active = ctx.get("active_task")
    agent_raw = active.get("agent") if isinstance(active, dict) else None
    from conversation_control_plane.contract import canonical_agent
    from api.services.bot0_intent_router import IntentRoute

    agent = canonical_agent(agent_raw) or agent_raw
    if agent not in ("workflow_builder", "workflow_editor"):
        return None
    return IntentRoute(
        intent=agent,
        layer="gate_continue",
        reason="finite gate reply continues active workflow session",
        confidence=1.0,
    )


_FABRICATED_SAVE_MARKERS = (
    "saved to the database",
    "workflow is now saved",
    "workflow has been saved",
    "the workflow is saved",
)


def strip_authoring_save_fabrication(
    answer: str,
    *,
    context: object,
    db: Any,
    tenant_id: str | None,
    conversation_id: str | None,
) -> str:
    """Backstop: bot0 detour must not claim a workflow save mid-authoring."""
    text = (answer or "").strip()
    if not text or not workflow_authoring_active(context):
        return answer
    pending = load_builder_pending_state(db, tenant_id, conversation_id)
    if pending and (pending.get("_committed") or pending.get("workflow_created")):
        return answer
    lower = text.lower()
    if not any(marker in lower for marker in _FABRICATED_SAVE_MARKERS):
        return answer
    from agent.workflow_builder.operational_data_prompt import TOP_LINE_KPI_STATUS_HINT

    return (
        "Your workflow **isn't saved yet** — the in-progress build is still open.\n\n"
        f"To continue: {TOP_LINE_KPI_STATUS_HINT}, then reply **yes** on the "
        "commit plan. You'll see **✅ Workflow saved** with an ID when it actually "
        "commits."
    )


__all__ = [
    "PHASE_BUILDING",
    "PHASE_COMMIT_PLAN",
    "PHASE_COMMITTED",
    "PHASE_DOMAIN_PICKER",
    "PHASE_EDITING",
    "PHASE_EXTRACTING",
    "PHASE_GATHERING",
    "PHASE_IR_REVIEW",
    "PHASE_OPERATIONAL_DATA",
    "PHASE_REVIEWING",
    "PHASE_ROLE_PROPOSAL",
    "ROLE_PROPOSAL_ACCEPT_REPLIES",
    "ROLE_PROPOSAL_DECLINE_REPLIES",
    "ROLE_PROPOSAL_MENU_REPLIES",
    "ROLE_PROPOSAL_REPLIES",
    "ROLE_PROPOSAL_REPROPOSE_REPLIES",
    "WORKFLOW_CONFIRMATION_REPLIES",
    "authoring_resume_in_progress",
    "authoring_snapshot_ledger_payload",
    "builder_pending_pk",
    "discovery_cognition_suppressed",
    "discovery_detour_supersedes_active_flow",
    "discovery_orientation_suppressed",
    "display_phase_for_authoring",
    "next_step_for_authoring_phase",
    "outcome_value_setup_orientation_suppressed",
    "post_save_status_orientation_suppressed",
    "load_builder_pending_state",
    "project_authoring_snapshot",
    "read_intent_cognition_needed",
    "authoring_gate_proceed_owns_turn",
    "resume_authoring_owns_turn",
    "sync_authoring_snapshot_to_ledger",
    "router_supersedes_discovery",
    "synthesize_gate_continue_route",
    "domain_gate_owns_authoring_turn",
    "domain_gate_owns_pick_turn",
    "domain_picker_blocks_inventory_soft_name",
    "authoring_gate_blocks_inventory_resolve",
    "exclusive_owner_blocks_inventory_early",
    "exclusive_owner_blocks_foreign_pre_decide",
    "ir_gate_owns_role_proposal_turn",
    "load_workflow_authoring_phase",
    "normalize_short_gate_reply",
    "operational_data_gate_owns_provision_turn",
    "operational_data_kpi_gate_open",
    "operational_data_provision_shape",
    "strip_authoring_save_fabrication",
    "project_fine_authoring_phase",
    "ledger_phase_awaiting_from_pending",
    "surface_read_detour_suppressed",
    "workflow_authoring_active",
    "DetourKind",
    "active_agent_task_blocks_detour",
]