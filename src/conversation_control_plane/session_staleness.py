"""Session-staleness re-orientation gate (control-plane).

When a user returns after a long gap while an active multi-turn stream is
live, code re-orients with Resume / Start Fresh **before** acting on a
terse continue ("yes", "lets continue") that might confirm something set
up hours earlier.

## Known idle policy (do not invent silent different cutoffs)

| Horizon | Default | Where | What happens |
|---|---|---|---|
| **Authoring soft reorient** | **30 min** | ``builder_idle_reset.AUTHORING_SOFT_REORIENT_SECONDS`` | Restorable Draft IR/nodes: stash + **Resume card**; live pending kept |
| **Session reorient (this module)** | **max(60m, suspended_ttl/6)** ≈ **4h** when TTL=24h | sole-continue + gate awaits | Resume card before continue acts |
| **Hard wipe (no restorable IR)** | **2h** default (param ``conversation_idle_reset_seconds``) | builder empty pending only | Drop history; no silent IR wipe when restorable |

User-visible honesty: after these gaps, the product must say so (card), not
silently re-enter multi-LLM continue. Builder soft path and this gate share
the same card type (``session_reorientation``).
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from conversation_control_plane.contract import canonical_agent

_AGENT_LABEL = {
    "workflow_builder": "Workflow Builder",
    "workflow_editor": "Workflow Editor",
    "transformation_advisor": "Transformation Advisor",
    "transformation_recommender": "Transformation Recommender",
    "advisor": "Transformation Advisor",
    "recommender": "Transformation Recommender",
    "bot0": "Bot0 Assistant",
}

# Kind → user-facing stream label (sole-continue paints)
_KIND_LABEL = {
    "cost_out": "agent / workflow cost-out",
    "cyber_risk_assessment": "cyber risk assessment",
    "realization_intake": "realization / deploy plan",
    "outcome_value_setup": "outcome & value setup",
    "drafting": "workflow drafting",
    "project_workspace": "project workspace",
    "scorecard_interrogate": "scorecard / run review",
    "risk_catalog_learning": "risk catalog exploration",
    "workflow_build": "workflow build",
    # F12a — engagement pack conductor (not a BOT0_AGENTS agent)
    "engagement_pack_plan": "initiative plan",
    # ISS — simulation input state (AI Involvement / staffing / value drivers)
    "input_state_setup": "simulation inputs",
}

# Mid-flight markers that used to skip reorient (bug: silent continue after hours).
_MIDFLIGHT_AWAITING = frozenset({"", "in_progress", "none", "null"})

# Ledger ``awaiting`` tokens → product voice. Never paint raw snake_case
# (conv_6a6dbadb: "Resuming … at **plan_act**").
_AWAITING_LABEL: dict[str, str] = {
    "plan_act": "your initiative plan",
    "mapping_confirm": "confirming the plan overview",
    "in_progress": "in-progress work",
    "in-progress work": "in-progress work",
    "operational_metrics": "operational metrics",
    "ir_review": "Draft IR review",
    "awaiting_ir_confirmation": "Draft IR confirmation",
    "awaiting_role_proposal_review": "staffed role review",
    "awaiting_commit_confirmation": "save confirmation",
    "awaiting_domain_choice": "domain choice",
    "awaiting_details": "waiting for more detail",
    "staff_as_is_accept": "staffing the as-is workflow",
    "staff_to_be_accept": "staffing the to-be workflow",
    "cost_profile_save_confirm": "cost profile save",
    "the previous step": "where you left off",
}


def product_voice_awaiting_label(awaiting: str | None) -> str | None:
    """Map ledger awaiting tokens to product voice (or omit unsafe internals).

    Returns a short user-facing phrase, or ``None`` when the token must not
    appear in prose (unknown snake_case). Callers omit the clause when None.
    """
    import re

    raw = str(awaiting or "").strip()
    if not raw:
        return "in-progress work"
    key = raw.casefold().replace(" ", "_").replace("-", "_")
    if key in _MIDFLIGHT_AWAITING or key in {"none", "null", ""}:
        return "in-progress work"
    if key in _AWAITING_LABEL:
        return _AWAITING_LABEL[key]
    # Engagement-pack step_ids double as awaiting_detail
    try:
        from conversation_control_plane.engagement_pack_contract import (
            _STEP_LABELS,
        )

        if key in _STEP_LABELS:
            return str(_STEP_LABELS[key])
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).debug(
            "pack step label lookup skipped",
            exc_info=True,
        )
    # Already human prose (spaces / title words) — keep
    if " " in raw and not re.search(r"_[a-z]", raw.casefold()):
        return raw
    # Unknown snake_case / camelCase machine token → do not paint
    if re.fullmatch(r"[a-z][a-z0-9_]{1,80}", key) and "_" in key:
        return None
    if re.fullmatch(r"[a-z]+(?:[A-Z][a-z0-9]+)+", raw):
        return None
    return raw


def resume_session_product_lead(*, awaiting: str | None = None) -> str:
    """Code-owned Resume lead — no internal awaiting tokens in prose."""
    label = product_voice_awaiting_label(awaiting)
    if label and label not in ("in-progress work", "where you left off"):
        return (
            f"Picking up where you left off — **{label}**."
        )
    return "Picking up where you left off."


def transport_resume_product_lead(
    *,
    kind: str | None = None,
    awaiting: str | None = None,
) -> str:
    """Lead after FE transport recovery when no idle reorient card was pending.

    Distinct from idle Resume: connection hiccup, not a multi-hour pause.
    Still names the live product stream when known — never generic
    \"re-tap Apply this plan\" laundry (Draft IR thrash after brief disconnect).
    """
    step = product_voice_awaiting_label(awaiting)
    kind_key = str(kind or "").strip()
    stream = _KIND_LABEL.get(kind_key) if kind_key else None
    if step and step not in ("in-progress work", "where you left off"):
        return (
            f"**Connection restored** — still on **{step}**. "
            f"Here's the card again."
        )
    if stream:
        return (
            f"**Connection restored** — still on **{stream}**. "
            f"Here's where you left off."
        )
    return (
        "**Connection restored** — you're still on this chat. "
        "Continue with your next step when ready."
    )


def _humanize_age(minutes: float) -> str:
    """Portable age label (kept local so this module has no orientation.py dep)."""
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{int(minutes)}m ago"
    hours = minutes / 60.0
    if hours < 24:
        return f"{int(hours)}h ago"
    days = hours / 24.0
    return f"{int(days)}d ago"

SESSION_REORIENTATION_RESUME_ACTION = "resume_current_session"
SESSION_REORIENTATION_START_FRESH_ACTION = "start_fresh"
SESSION_REORIENTATION_ACTION_IDS = frozenset(
    {
        SESSION_REORIENTATION_RESUME_ACTION,
        SESSION_REORIENTATION_START_FRESH_ACTION,
    }
)


def _parse_iso(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        parsed = dt.datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def reorientation_threshold_minutes(db: Any) -> float:
    """Re-confirm before the suspended-task prune horizon (default 24h → 4h)."""
    try:
        from conversation_control_plane.ledger import suspended_task_ttl_minutes

        ttl = float(suspended_task_ttl_minutes(db))
    except Exception:  # noqa: BLE001
        ttl = 24 * 60.0
    return max(60.0, ttl / 6.0)


def _gap_minutes_since_last_turn(context: dict[str, Any] | None) -> float | None:
    ctx = context or {}
    marker = ctx.get("_last_completed_turn")
    if isinstance(marker, dict):
        ts = _parse_iso(marker.get("completed_at"))
        if ts is not None:
            return max(
                0.0,
                (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() / 60.0,
            )
    active = ctx.get("active_task")
    if isinstance(active, dict):
        ts = _parse_iso(active.get("started_at"))
        if ts is not None:
            return max(
                0.0,
                (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() / 60.0,
            )
    return None


def _ack_covers_last_completed_turn(context: dict[str, Any] | None) -> bool:
    ctx = context or {}
    if not ctx.get("session_reorientation_ack"):
        return False
    resolved_at = _parse_iso(ctx.get("session_reorientation_resolved_at"))
    marker = ctx.get("_last_completed_turn")
    completed_at = (
        _parse_iso(marker.get("completed_at"))
        if isinstance(marker, dict)
        else None
    )
    if resolved_at is None or completed_at is None:
        return True
    return resolved_at >= completed_at


def _active_is_multi_turn_stream(active: dict[str, Any]) -> bool:
    """True when ledger marks a multi-turn stream (sole-continue or builder)."""
    kind = str(active.get("kind") or "").strip()
    if kind == "workflow_build":
        return True
    try:
        from conversation_control_plane.multi_turn_stream_contract import (
            is_sole_continue_kind,
        )

        if is_sole_continue_kind(kind):
            return True
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).debug(
            "sole_continue kind probe skipped",
            exc_info=True,
        )
    agent = str(active.get("agent") or "").strip()
    return agent in ("workflow_builder", "workflow_editor")


def should_reorient_before_acting(
    db: Any,
    *,
    context: dict[str, Any] | None,
    query: str,
) -> bool:
    """True when a stale-gap turn must re-orient instead of silent continue.

    Fires for:
      - specific gate awaits (historical: confirm/domain/etc.)
      - **any sole-continue / builder multi-turn stream** after the threshold,
        even when ``awaiting`` is ``in_progress`` (mid-stream continue)

    Does **not** fire when the user already acked Resume/Start Fresh for this
    gap, or when a reorient card is already pending.

    ``query`` is reserved for host short-circuits (finite chips still reorient —
    honesty before mutative IR/repair acts after a long idle gap).
    """
    _ = query
    ctx = context or {}
    if _ack_covers_last_completed_turn(ctx):
        return False
    if ctx.get("session_reorientation_pending"):
        return False
    active = ctx.get("active_task")
    if not isinstance(active, dict):
        return False

    awaiting = str(active.get("awaiting") or "").strip().lower()
    multi = _active_is_multi_turn_stream(active)
    at_specific_gate = awaiting not in _MIDFLIGHT_AWAITING
    if not multi and not at_specific_gate:
        return False

    gap = _gap_minutes_since_last_turn(ctx)
    if gap is None:
        return False
    if gap < reorientation_threshold_minutes(db):
        return False
    return True


def needs_session_reorientation_surface(
    db: Any,
    *,
    context: dict[str, Any] | None,
    query: str = "",
) -> bool:
    """True when host should open the Resume/Start Fresh card (no LLM).

    Covers both first stale-gap fire and re-show while a card is already
    pending (user clicked Continue repair again without Resume).
    """
    ctx = context or {}
    if ctx.get("session_reorientation_pending"):
        return True
    return should_reorient_before_acting(db, context=ctx, query=query)


def build_session_staleness_reorientation(
    *,
    context: dict[str, Any] | None,
    db: Any,
) -> dict[str, Any]:
    """Code-owned re-orientation reply + context marker."""
    del db  # threshold already applied by caller; kept for API symmetry
    ctx = context or {}
    active = ctx.get("active_task") if isinstance(ctx.get("active_task"), dict) else {}
    agent = canonical_agent(active.get("agent")) or active.get("agent") or "bot0"
    label = _AGENT_LABEL.get(str(agent), str(agent))
    kind = str(active.get("kind") or "").strip()
    stream = _KIND_LABEL.get(kind) or label
    raw_awaiting = str(active.get("awaiting") or "").strip()
    awaiting_voice = product_voice_awaiting_label(raw_awaiting) or "in-progress work"
    gap = _gap_minutes_since_last_turn(ctx) or 0.0
    # _humanize_age already ends with "ago" / "just now" — do not append another.
    age = _humanize_age(gap)
    # Product voice: stream + optional stage — never raw plan_act / snake_case.
    if awaiting_voice and awaiting_voice != "in-progress work":
        summary = (
            f"We were mid-{stream} ({awaiting_voice}) about {age}. "
            "Choose whether to continue that session or reset before I act "
            "on the next message."
        )
        text = (
            f"We were mid-**{stream}** ({awaiting_voice}) about **{age}**. "
            "Choose whether to pick up where we left off or start fresh before I act."
        )
    else:
        summary = (
            f"We were mid-{stream} about {age}. "
            "Choose whether to continue that session or reset before I act "
            "on the next message."
        )
        text = (
            f"We were mid-**{stream}** about **{age}**. "
            "Choose whether to pick up where we left off or start fresh before I act."
        )
    return {
        "action": "answer",
        "route": None,
        "answer": {
            "answer": text,
            "sources": [],
            "blocks": [
                {
                    "type": "session_reorientation",
                    "data": {
                        "title": "Resume previous session?",
                        "summary": summary,
                        "agent": agent,
                        "agent_label": label,
                        # FE may show stage — product voice only
                        "awaiting": awaiting_voice,
                        "age_label": age,
                        "kind": kind or None,
                        "actions": [
                            {
                                "action_id": SESSION_REORIENTATION_RESUME_ACTION,
                                "label": "Resume",
                                "variant": "primary",
                            },
                            {
                                "action_id": SESSION_REORIENTATION_START_FRESH_ACTION,
                                "label": "Start Fresh",
                                "variant": "secondary",
                            },
                        ],
                    },
                },
            ],
        },
        "context_updates": {
            "session_reorientation_pending": True,
            "session_reorientation_shown_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        "response_agent_type": agent,
    }


__all__ = [
    "build_session_staleness_reorientation",
    "needs_session_reorientation_surface",
    "product_voice_awaiting_label",
    "reorientation_threshold_minutes",
    "resume_session_product_lead",
    "SESSION_REORIENTATION_ACTION_IDS",
    "SESSION_REORIENTATION_RESUME_ACTION",
    "SESSION_REORIENTATION_START_FRESH_ACTION",
    "should_reorient_before_acting",
]
