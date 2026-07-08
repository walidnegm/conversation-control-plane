"""Code-owned post-save scorecard turns after WB ledger release.

After commit, ``release_post_commit_builder`` clears the active workflow_builder
task so simulate/orientation paths stay coherent. Metric patches and finite
1–4 monetization picks must still resolve on the saved workflow — not bot0
generic chat or sparse drafting intake (conv_b5910559 class).

Ownership is **narrow**: digit-bearing metric paste and menu picks only.
Orientation/status and product questions (e.g. per-step KPIs) fall through to
the unified router; post-save status answers via ``is_orientation_turn``.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_SAVE_ID_RE = re.compile(r"\b(wf_[a-z0-9]+)\b", re.IGNORECASE)
_POST_SAVE_MARKERS = (
    "still needed before project attach",
    "outcome & value model",
    "capacity monetization",
    "already captured:",
    "workflow saved successfully",
    "is saved and project-ready",
)


def _messages_as_dicts(
    messages: list[dict[str, Any]] | list[tuple[str, str]] | None,
) -> list[dict[str, Any]]:
    if not messages:
        return []
    out: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, dict):
            out.append(msg)
        elif isinstance(msg, (list, tuple)) and len(msg) >= 2:
            out.append({"role": msg[0], "content": msg[1]})
    return out


def workflow_id_from_post_save_transcript(
    messages: list[dict[str, Any]] | list[tuple[str, str]] | None,
) -> str | None:
    """Best-effort wf_* from a recent code-owned save or setup follow-up."""
    from api.services.conversation_control.authoring_gate_turn import (
        committed_workflow_id_from_messages,
    )

    wid = committed_workflow_id_from_messages(_messages_as_dicts(messages))
    if wid:
        return wid
    for msg in reversed(_messages_as_dicts(messages)[-12:]):
        if msg.get("role") != "assistant":
            continue
        text = (msg.get("content") or "").lower()
        if not any(marker in text for marker in _POST_SAVE_MARKERS):
            continue
        match = _SAVE_ID_RE.search(msg.get("content") or "")
        if match:
            return match.group(1)
    return None


def resolve_post_save_workflow_id(
    context: dict[str, Any] | None,
    messages: list[dict[str, Any]] | list[tuple[str, str]] | None,
) -> str | None:
    ctx = context if isinstance(context, dict) else {}
    for raw in (
        ctx.get("last_read_workflow_id"),
        ctx.get("workflow_id"),
        workflow_id_from_post_save_transcript(messages),
    ):
        wid = str(raw or "").strip()
        if wid:
            return wid
    return None


def _builder_mid_authoring_open(
    db: Any,
    tenant_id: str,
    conversation_id: str | None,
) -> bool:
    if not db or not tenant_id or not conversation_id:
        return False
    try:
        from api.services.conversation_control.dispatch_phase import (
            load_builder_pending_state,
        )

        pending = load_builder_pending_state(db, tenant_id, conversation_id)
        if not pending:
            return False
        if pending.get("_committed"):
            return False
        return bool(
            pending.get("_workflow_ir")
            or pending.get("_awaiting_ir_confirmation")
            or pending.get("_awaiting_domain_choice")
            or pending.get("_awaiting_domain")
            or pending.get("_awaiting_operational_data")
            or pending.get("_awaiting_commit_confirmation")
            or (pending.get("nodes") and pending.get("_graph_validated"))
        )
    except Exception:  # noqa: BLE001
        logger.debug("post_save builder pending probe failed", exc_info=True)
        return False


def recent_post_save_setup_offered(
    messages: list[dict[str, Any]] | list[tuple[str, str]] | None,
) -> bool:
    for msg in reversed(_messages_as_dicts(messages)[-6:]):
        if msg.get("role") != "assistant":
            continue
        text = (msg.get("content") or "").lower()
        if any(marker in text for marker in _POST_SAVE_MARKERS):
            return True
    return False


def post_save_setup_owns_turn(
    db: Any,
    tenant_id: str,
    *,
    query: str,
    context: dict[str, Any] | None,
    messages: list[dict[str, Any]] | list[tuple[str, str]] | None,
    conversation_id: str | None,
) -> tuple[bool, str | None]:
    """Return (owns, workflow_id) when this turn should patch the saved scorecard."""
    q = (query or "").strip()
    if not q or not db or not tenant_id:
        return False, None

    active = (context or {}).get("active_task") if isinstance(context, dict) else None
    if isinstance(active, dict) and (active.get("kind") or "") == "outcome_value_setup":
        return False, None
    if _builder_mid_authoring_open(db, tenant_id, conversation_id):
        return False, None

    wf_id = resolve_post_save_workflow_id(context, messages)
    if not wf_id:
        return False, None

    from api.services.conversation_control.authoring_gate_turn import (
        workflow_saved_in_db,
    )
    from api.services.conversation_control.workflow_builder_post_commit import (
        workflow_has_committed_graph,
    )

    saved, db_id = workflow_saved_in_db(
        db, tenant_id, workflow_id=wf_id, workflow_name=None,
    )
    if not saved or not db_id:
        return False, None
    if not workflow_has_committed_graph(db, db_id):
        return False, None
    wf_id = db_id

    try:
        from agent.workflow_builder.input_shape import looks_like_rich_workflow_spec

        if looks_like_rich_workflow_spec(q):
            return False, None
    except Exception:  # noqa: BLE001
        pass

    from api.services.workflow_scorecard_fields import parse_workflow_type_pick

    if parse_workflow_type_pick(q):
        return True, wf_id

    if any(ch.isdigit() for ch in q):
        return True, wf_id

    return False, None


def build_post_save_setup_response(
    db: Any,
    tenant_id: str,
    *,
    query: str,
    context: dict[str, Any] | None,
    messages: list[dict[str, Any]] | list[tuple[str, str]] | None,
    conversation_id: str | None,
) -> dict[str, Any] | None:
    owns, wf_id = post_save_setup_owns_turn(
        db,
        tenant_id,
        query=query,
        context=context,
        messages=messages,
        conversation_id=conversation_id,
    )
    if not owns or not wf_id:
        return None

    from agent.workflow_builder.post_commit_turn import maybe_handle_post_commit_turn
    from agent.workflow_builder.state import AgentState

    result = maybe_handle_post_commit_turn(
        db,
        tenant_id,
        query=query,
        pending={},
        messages=_messages_as_dicts(messages),
        session_id=conversation_id,
        agent_state_cls=AgentState,
        context=context,
    )
    if not result:
        return None

    committed_id = str(result.get("workflow_id") or wf_id).strip()
    ctx_updates: dict[str, Any] = {
        "agent_type": None,
        "workflow_id": committed_id,
        "last_read_workflow_id": committed_id,
    }
    wf_name = str((context or {}).get("last_read_workflow_name") or "").strip()
    if wf_name:
        ctx_updates["last_read_workflow_name"] = wf_name

    return {
        "action": "answer",
        "route": None,
        "answer": {
            "answer": str(result.get("reply") or "").strip(),
            "sources": ["post_save_setup"],
            "blocks": list(result.get("blocks") or []),
        },
        "context_updates": ctx_updates,
        "response_agent_type": "bot0",
    }


def _committed_workflow_row(
    db: Any,
    tenant_id: str,
    *,
    context: dict[str, Any] | None,
    messages: list[dict[str, Any]] | list[tuple[str, str]] | None,
) -> tuple[str | None, dict[str, Any] | None]:
    wf_id = resolve_post_save_workflow_id(context, messages)
    if not wf_id:
        return None, None
    from api.services.conversation_control.authoring_gate_turn import (
        workflow_saved_in_db,
    )
    from api.services.conversation_control.workflow_builder_post_commit import (
        workflow_has_committed_graph,
    )

    saved, db_id = workflow_saved_in_db(
        db, tenant_id, workflow_id=wf_id, workflow_name=None,
    )
    if not saved or not db_id or not workflow_has_committed_graph(db, db_id):
        return None, None
    from api.services.workspace_interrogation import load_workflow_row

    wf = load_workflow_row(db, tenant_id=tenant_id, workflow_id=db_id)
    if not wf:
        return None, None
    return db_id, wf


def collect_workflow_scorecard_allowed_numbers(
    wf: dict[str, Any] | None,
) -> set[float]:
    """Authoritative scorecard numbers the orchestrator may restate."""
    allowed: set[float] = set()
    if not wf:
        return allowed
    for key in (
        "baseline_annual_units",
        "revenue_per_unit_usd",
        "absorption_ratio",
        "opportunity_cost_per_unit_usd",
        "cycle_time_baseline_days",
    ):
        raw = wf.get(key)
        if raw is None:
            continue
        try:
            allowed.add(float(raw))
        except (TypeError, ValueError):
            pass
    wtype = str(wf.get("workflow_type") or "").strip()
    if wtype:
        from api.services.workflow_type_catalog import WORKFLOW_TYPE_SPECS

        for i, spec in enumerate(WORKFLOW_TYPE_SPECS, start=1):
            if spec.value == wtype:
                allowed.add(float(i))
                break
    return allowed


def post_save_workflow_status_eligible(
    context: dict[str, Any] | None,
    messages: list[dict[str, Any]] | list[tuple[str, str]] | None = None,
    *,
    discovery: dict[str, str] | None = None,
    orientation_focus: str | None = None,
) -> bool:
    """True only when O&V post-save status copy is the right answer for this turn.

    A bare ``last_read_workflow_id`` thread pin is never sufficient — that pin
    survives across unrelated detours (realization_intake, scorecards, catalog role)
    and must not hijack orientation or discovery turns (conv realization + scorecards).
    """
    from api.services.conversation_control.dispatch_phase import (
        post_save_status_orientation_suppressed,
    )

    if post_save_status_orientation_suppressed(
        context=context,
        orientation_focus=orientation_focus,
        discovery=discovery,
    ):
        return False

    ctx = context if isinstance(context, dict) else {}
    active = ctx.get("active_task") or {}
    if isinstance(active, dict) and (active.get("kind") or "") == "outcome_value_setup":
        return True
    return recent_post_save_setup_offered(messages)


def build_post_save_workflow_status_response(
    db: Any,
    tenant_id: str,
    *,
    context: dict[str, Any] | None,
    messages: list[dict[str, Any]] | list[tuple[str, str]] | None = None,
    discovery: dict[str, str] | None = None,
    orientation_focus: str | None = None,
) -> dict[str, Any] | None:
    """Ledger-grounded status for orientation — real DB values, not transcript tables."""
    if not post_save_workflow_status_eligible(
        context,
        messages,
        discovery=discovery,
        orientation_focus=orientation_focus,
    ):
        return None

    wf_id, wf = _committed_workflow_row(
        db, tenant_id, context=context, messages=messages,
    )
    if not wf_id or not wf:
        return None

    from agent.workflow_builder.post_commit_setup_followup import (
        _setup_followup_cta,
        scorecard_gaps_from_row,
    )
    from api.services.workflow_output_step_handler import (
        list_output_step_candidates,
        workflow_has_output_step,
    )
    from api.services.workflow_scorecard_fields import (
        format_operational_fact_lines,
        outcome_field_plain_label,
    )
    from api.services.workspace_interrogation import assess_outcome_anchor

    name = str(wf.get("workflow_name") or wf_id)
    wtype = str(wf.get("workflow_type") or "").strip() or None
    gaps = scorecard_gaps_from_row(wf)
    captured = format_operational_fact_lines(
        {
            "unit_of_flow_label": wf.get("unit_of_flow_label"),
            "baseline_annual_units": wf.get("baseline_annual_units"),
            "revenue_per_unit_usd": wf.get("revenue_per_unit_usd"),
            "workflow_type": wf.get("workflow_type"),
            "absorption_ratio": wf.get("absorption_ratio"),
            "opportunity_cost_per_unit_usd": wf.get("opportunity_cost_per_unit_usd"),
            "cycle_time_baseline_days": wf.get("cycle_time_baseline_days"),
        },
    )
    candidates = list_output_step_candidates(
        db, tenant_id=tenant_id, workflow_id=wf_id,
    )
    needs_output = len(candidates) > 0 and not workflow_has_output_step(candidates)
    anchor = assess_outcome_anchor(wf)

    lines: list[str] = [
        f"In this conversation we're finishing the **Outcome & Value Model** for "
        f"**{name}** (saved as `{wf_id}`).",
    ]
    if captured:
        lines.append("**Saved in the database right now:**")
        lines.extend(f"- {ln}" for ln in captured)
    elif anchor.get("recap_plain"):
        lines.append(f"**Saved in the database:** {anchor['recap_plain']}.")
    if gaps:
        missing = [
            outcome_field_plain_label(f, workflow_type=wtype) for f in gaps
        ]
        lines.append("**Still needed:** " + "; ".join(missing) + ".")
        lines.append(_setup_followup_cta(gaps=gaps, needs_output=needs_output))
    elif needs_output:
        lines.append("**Still needed:** pick the primary **output step** on the graph.")
    else:
        lines.append(
            "The business scorecard is complete — attach this workflow to a project "
            "or say *simulate this workflow* when you're ready."
        )

    ctx_updates: dict[str, Any] = {
        "agent_type": None,
        "workflow_id": wf_id,
        "last_read_workflow_id": wf_id,
    }
    if name:
        ctx_updates["last_read_workflow_name"] = name

    return {
        "action": "answer",
        "route": None,
        "answer": {
            "answer": "\n\n".join(lines),
            "sources": ["post_save_status"],
            "blocks": [],
        },
        "context_updates": ctx_updates,
        "response_agent_type": "bot0",
    }


__all__ = [
    "build_post_save_setup_response",
    "build_post_save_workflow_status_response",
    "collect_workflow_scorecard_allowed_numbers",
    "post_save_setup_owns_turn",
    "post_save_workflow_status_eligible",
    "resolve_post_save_workflow_id",
    "workflow_id_from_post_save_transcript",
]