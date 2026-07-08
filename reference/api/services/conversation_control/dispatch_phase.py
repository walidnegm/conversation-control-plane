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
    """True when workflow_builder/editor owns the conversation turn."""
    if not isinstance(context, dict):
        return False
    active_agent = str(
        ((context.get("active_task") or {}).get("agent") or "")
    ).strip()
    agent_type = str(context.get("agent_type") or "").strip()
    return (
        active_agent in _WORKFLOW_AUTHORING_AGENTS
        or agent_type in _WORKFLOW_AUTHORING_AGENTS
    )


def builder_pending_pk(tenant_id: str, conversation_id: str) -> str:
    return f"{tenant_id}:bld_{conversation_id}"


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
        return state if isinstance(state, dict) and state else None
    except Exception:  # noqa: BLE001 — best-effort projection, never raises
        return None


def project_fine_authoring_phase(pending: dict[str, Any] | None) -> str | None:
    """Map durable builder pending to a routing-safe fine phase."""
    if not pending:
        return None
    if pending.get("_awaiting_post_commit_clarification"):
        return PHASE_EDITING
    if pending.get("_committed") or pending.get("workflow_created"):
        return PHASE_COMMITTED
    if pending.get("_awaiting_operational_data"):
        return PHASE_OPERATIONAL_DATA
    if pending.get("_awaiting_ir_confirmation"):
        return PHASE_IR_REVIEW
    if pending.get("_awaiting_role_proposal_review"):
        return PHASE_ROLE_PROPOSAL
    if pending.get("_awaiting_commit_confirmation"):
        from agent.workflow_builder.commit_readiness import is_commit_plan_ready

        if is_commit_plan_ready(pending):
            return PHASE_COMMIT_PLAN
    from agent.workflow_builder.domain_picker_renderer import domain_authoring_gate_open

    if domain_authoring_gate_open(pending):
        return PHASE_DOMAIN_PICKER

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
        return "Reply **accept**, **skip**, or **try again** for the proposed roles."
    if phase == PHASE_DOMAIN_PICKER:
        candidates = (pending or {}).get("_domain_candidates") or []
        if candidates:
            return (
                "Pick the catalog domain — reply with the **number** "
                "(e.g. **1**) or the **domain name**."
            )
        return "Pick the industry domain — reply with the number or name."
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
    """Compact payload slice persisted on active_task.payload."""
    snap = project_authoring_snapshot(pending)
    if not snap:
        return None
    return {
        "authoring_phase": snap["authoring_phase"],
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
        from api.services.conversation_control.ledger import update_phase

        task = update_phase(
            db,
            tenant_id,
            conversation_id,
            agent=agent,
            phase=str(active.get("phase") or "active"),
            awaiting=payload.get("authoring_phase") or active.get("awaiting"),
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
    from api.services.conversation_control.authoring_gate_turn import (
        resume_authoring_owns_turn as _contract_resume_authoring_owns_turn,
    )

    if not conversation_id or not (query or "").strip():
        return False
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
            from api.services.conversation_control.orientation import (
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
) -> bool:
    """True when the workflow-surface read detour must not run."""
    if not workflow_authoring_active(context):
        return False
    if authoring_phase is None:
        # Builder/editor is active but pending could not be loaded — still
        # suppress saved-workflow detours so KPI/IR turns stay in-builder.
        return True
    return authoring_phase != PHASE_COMMITTED


def active_agent_task_blocks_detour(
    detour_kind: DetourKind,
    *,
    db: Any = None,
    tenant_id: str | None = None,
    conversation_id: str | None = None,
    query: str = "",
    context: object = None,
    authoring_phase: str | None = None,
) -> bool:
    """Single facade: active authoring task owns the turn — block competing detours.

    ``surface_read`` — saved-workflow read classifier must not fire mid-IR.
    ``discovery`` / ``orientation`` — front-door cognition must not steal gate replies.
    """
    if detour_kind == "surface_read":
        return surface_read_detour_suppressed(authoring_phase, context=context)
    if detour_kind in ("discovery", "orientation"):
        return discovery_cognition_suppressed(
            db, tenant_id, conversation_id, query, context=context,
        )
    return False


# Finite-grammar gate replies — not NL cognition. Mirrors workflow_builder
# ``_confirm_tokens`` so a bare "yes" at IR/commit gates reaches decide_turn
# instead of the discovery orientation classifier (conv_7a953788).
WORKFLOW_CONFIRMATION_REPLIES = frozenset({
    "yes", "y", "ok", "okay", "sure", "proceed", "continue",
    "go ahead", "go on", "looks good", "looks right", "correct",
    "that works", "confirm", "confirmed", "no", "n", "nope",
    "cancel", "stop", "save",
})

ROLE_PROPOSAL_REPLIES = frozenset({
    "accept", "skip", "try again",
})


def normalize_short_gate_reply(query: str) -> str:
    return (query or "").strip().lower().rstrip(".!?")


_LEDGER_KINDS_PREEMPT_POST_SAVE_STATUS = frozenset({
    "drafting",
    "realization_intake",
    "workflow_pick",
})


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
    from api.services.conversation_control.discovery_intent import (
        DISCOVERY_DETOUR_KINDS,
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
    active = ctx.get("active_task") or {}
    if not isinstance(active, dict):
        return False

    kind = (active.get("kind") or "").strip()
    if kind == "outcome_value_setup":
        return False
    if kind in _LEDGER_KINDS_PREEMPT_POST_SAVE_STATUS:
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
) -> bool:
    """True when the open top-line KPI gate should stay on workflow_builder."""
    from api.services.conversation_control.authoring_gate_turn import (
        operational_data_gate_owns_provision_turn as _contract_kpi_gate_owns_turn,
    )

    return _contract_kpi_gate_owns_turn(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        query=query,
        context=context,
    )


def discovery_detour_supersedes_active_flow(
    *,
    discovery: dict[str, str] | None = None,
    unified_signal: object | None = None,
    plan: object | None = None,
) -> bool:
    """True when a router-owned front-door detour must beat an active guided flow."""
    from api.services.conversation_control.delivery_order_contract import (
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
) -> bool:
    """Skip discovery/orientation LLM when an active task owns a finite gate reply."""
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
    ):
        return True
    ctx = context if isinstance(context, dict) else {}
    active = ctx.get("active_task")
    if not isinstance(active, dict):
        return False
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
    from api.services.conversation_control.authoring_gate_turn import (
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
    ):
        from api.services.bot0_intent_router import IntentRoute

        return IntentRoute(
            intent="workflow_builder",
            layer="gate_continue",
            reason="finite headline KPI reply continues active workflow session",
            confidence=1.0,
        )
    if not discovery_cognition_suppressed(
        db, tenant_id, conversation_id, query, context=context,
    ):
        return None
    ctx = context if isinstance(context, dict) else {}
    active = ctx.get("active_task")
    agent_raw = active.get("agent") if isinstance(active, dict) else None
    from api.services.conversation_control.contract import canonical_agent
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
    "ROLE_PROPOSAL_REPLIES",
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
    "domain_gate_owns_pick_turn",
    "ir_gate_owns_role_proposal_turn",
    "load_workflow_authoring_phase",
    "normalize_short_gate_reply",
    "operational_data_gate_owns_provision_turn",
    "operational_data_kpi_gate_open",
    "operational_data_provision_shape",
    "strip_authoring_save_fabrication",
    "project_fine_authoring_phase",
    "surface_read_detour_suppressed",
    "workflow_authoring_active",
    "DetourKind",
    "active_agent_task_blocks_detour",
]