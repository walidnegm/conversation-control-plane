"""L2.1 — rebuild projection *hints* from the journal for audit / equivalence.

Hot-path routing still reads the live L1 projection. This module reconstructs
a simplified control view from ordered journal events so tests can assert
replay equivalence for accepted lifecycle sequences.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from conversation_control_plane.ledger_journal import list_control_events


def rebuild_control_projection(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reduce ordered journal events → reconstructed control projection.

    Supports: task_began, task_completed/abandoned/failed/superseded/expired,
    switch_proposed / switch_accepted / switch_declined, and phase-like payload
    updates embedded in task_began (phase/awaiting).
    """
    active: Optional[dict[str, Any]] = None
    suspended: list[dict[str, Any]] = []
    pending_switch: Optional[dict[str, Any]] = None
    control_revision = 0
    last_command_id: Optional[str] = None

    for ev in events:
        et = str(ev.get("event_type") or "")
        payload = ev.get("payload_json") or ev.get("payload") or {}
        if isinstance(payload, str):
            import json

            try:
                payload = json.loads(payload)
            except Exception:  # noqa: BLE001
                payload = {}
        if not isinstance(payload, dict):
            payload = {}

        rev = ev.get("control_revision_after")
        if rev is not None:
            try:
                control_revision = max(control_revision, int(rev))
            except (TypeError, ValueError):
                pass
        last_command_id = str(ev.get("command_id") or last_command_id or "") or last_command_id

        if et == "task_began":
            if active and isinstance(active, dict):
                # Implicit suspend prior (mirrors begin replacing active).
                suspended = _dedupe_suspended(suspended, active)
                suspended.append({**active, "suspend_reason": "superseded_by_begin"})
            active = {
                "task_id": ev.get("task_id"),
                "agent": ev.get("agent"),
                "kind": ev.get("kind"),
                "phase": payload.get("phase"),
                "awaiting": payload.get("awaiting"),
                "pending_ref": payload.get("pending_ref"),
            }
        elif et in (
            "task_completed",
            "task_abandoned",
            "task_failed",
            "task_superseded",
            "task_expired",
        ):
            active = None
            pending_switch = None
        elif et == "switch_proposed":
            pending_switch = {
                "from_agent": payload.get("from_agent"),
                "to_agent": payload.get("to_agent"),
                "source_message_id": payload.get("source_message_id"),
                "decision_id": payload.get("decision_id"),
            }
        elif et == "switch_accepted":
            pending_switch = None
            if active and isinstance(active, dict):
                suspended = _dedupe_suspended(suspended, active)
                suspended.append({
                    **active,
                    "suspend_reason": "switch_accepted",
                    "task_id": payload.get("suspended_task_id") or active.get("task_id"),
                })
            to_agent = payload.get("to_agent")
            begun = payload.get("pending") if isinstance(payload.get("pending"), dict) else {}
            if payload.get("begin_target") or begun.get("to_agent") or to_agent:
                active = {
                    "task_id": ev.get("task_id"),
                    "agent": to_agent or begun.get("to_agent"),
                    "kind": ev.get("kind"),
                    "phase": "ready",
                    "awaiting": "task_request",
                }
        elif et == "switch_declined":
            pending_switch = None
        # else: ignore unknown event types (forward-compatible)

    return {
        "active_task": active,
        "suspended_tasks": suspended,
        "pending_switch": pending_switch,
        "control_revision": control_revision,
        "last_command_id": last_command_id,
        "event_count": len(events),
    }


def _dedupe_suspended(
    suspended: list[dict[str, Any]],
    active: dict[str, Any],
) -> list[dict[str, Any]]:
    tid = active.get("task_id")
    agent = active.get("agent")
    out: list[dict[str, Any]] = []
    for t in suspended:
        if not isinstance(t, dict):
            continue
        if tid and t.get("task_id") == tid:
            continue
        if not tid and agent and t.get("agent") == agent and not t.get("task_id"):
            continue
        out.append(t)
    return out


def rebuild_from_db(
    db: Session,
    *,
    tenant_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Load journal rows and rebuild projection hints."""
    events = list_control_events(
        db, tenant_id=tenant_id, conversation_id=conversation_id, after_seq=0, limit=1000,
    )
    return rebuild_control_projection(events)


def projection_equivalence(
    live: dict[str, Any],
    rebuilt: dict[str, Any],
) -> dict[str, Any]:
    """Compare live get_control_state vs rebuilt for core fields.

    Returns ``{ok, mismatches}`` — used by L2.1 regression suite.
    """
    mismatches: list[str] = []
    live_active = live.get("active_task") if isinstance(live.get("active_task"), dict) else None
    reb_active = rebuilt.get("active_task") if isinstance(rebuilt.get("active_task"), dict) else None

    def _tid(t: dict | None) -> str | None:
        if not t:
            return None
        return str(t.get("task_id") or "") or None

    def _agent(t: dict | None) -> str | None:
        if not t:
            return None
        return str(t.get("agent") or "") or None

    def _kind(t: dict | None) -> str | None:
        if not t:
            return None
        return str(t.get("kind") or "") or None

    if bool(live_active) != bool(reb_active):
        mismatches.append("active_task_presence")
    elif live_active and reb_active:
        if _tid(live_active) and _tid(reb_active) and _tid(live_active) != _tid(reb_active):
            mismatches.append("active_task.task_id")
        if _agent(live_active) != _agent(reb_active):
            mismatches.append("active_task.agent")
        if _kind(live_active) and _kind(reb_active) and _kind(live_active) != _kind(reb_active):
            mismatches.append("active_task.kind")

    live_ps = live.get("pending_switch")
    reb_ps = rebuilt.get("pending_switch")
    if bool(live_ps) != bool(reb_ps):
        mismatches.append("pending_switch_presence")

    return {"ok": len(mismatches) == 0, "mismatches": mismatches}


__all__ = [
    "projection_equivalence",
    "rebuild_control_projection",
    "rebuild_from_db",
]
