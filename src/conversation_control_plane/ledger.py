"""Ledger — the single writer for all conversation control state.

Implements the API sketched in the epic (with review-driven clarifications).

All writes to control keys (pending_switch, active_task, suspended_tasks,
and the transitional legacy advisor flags during P2) MUST go through this module.

It generalizes the safe jsonb primitives that were proven in the Stage-1 shim
(`api/services/conversation_control_state.py`). During P2a/P2b the shim remains
for P0/P1 compatibility and worker handoff paths; new code uses the ledger
directly. Post-P3b the shim can be retired.

Write discipline (invariants 7 + 8):
- Per-key jsonb_set / jsonb - array (never whole-blob read-modify-write for control keys).
- Multi-key transitions (e.g. complete_task) run under SELECT ... FOR UPDATE.
- Every write emits the appropriate platform event.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from typing import Any, Literal, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from api.services.event_logger import log_platform_event
except ImportError:  # public extract without monorepo host
    def log_platform_event(*_a: Any, **_k: Any) -> None:  # type: ignore[misc]
        return None

logger = logging.getLogger(__name__)

# Inlined from the former Stage-1 shim (now retired for the ledger writer per P3b).
# These are the minimal primitives needed for single-writer control key updates.
# The old conversation_control_state.py can remain for transitional P0/P1 shim callers
# but ledger no longer delegates to it.
try:
    from api.services import conversation_staleness as _staleness
except ImportError:  # public extract — use hardcoded TTL defaults
    class _StalenessFallback:
        _DEFAULTS = {
            "control_pending_switch_ttl_minutes": 30.0,
            "control_suspended_task_ttl_hours": 24.0,
            "turn_claim_ttl_seconds": 240.0,
            "turn_claim_orphan_steal_seconds": 30.0,
        }

        @classmethod
        def default(cls, key: str) -> float:
            return float(cls._DEFAULTS.get(key, 0.0))

        @classmethod
        def resolve_global(cls, _db: Any, key: str) -> float:
            return cls.default(key)

    _staleness = _StalenessFallback()  # type: ignore[assignment]


def _pending_switch_ttl_minutes(db: Session | None = None) -> float:
    # Keep the historical default visible in source; runtime authority is the
    # system-wide simulation_parameters chain (__default__ + bot0-platform).
    _staleness.default("control_pending_switch_ttl_minutes")
    return float(_staleness.resolve_global(db, "control_pending_switch_ttl_minutes"))


def _suspended_task_ttl_minutes(db: Session | None = None) -> float:
    _staleness.default("control_suspended_task_ttl_hours")
    return float(_staleness.resolve_global(db, "control_suspended_task_ttl_hours")) * 60.0


def _build_pending_switch(
    *,
    from_agent: str,
    to_agent: str,
    original_message: str,
    source_message_id: str | None = None,
    requested_at: str | None = None,
    decision_id: str | None = None,
    control_revision: int = 0,
    task_text: str | None = None,
) -> dict:
    requested = requested_at or dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "original_message": original_message,
        "source_message_id": source_message_id,
        "requested_at": requested,
        "decision_id": decision_id,
        "control_revision": int(control_revision or 0),
        "task_text": task_text,
    }

def _read_pending_switch(context: dict | None) -> dict | None:
    pending = (context or {}).get("pending_switch")
    return pending if isinstance(pending, dict) else None


def _pending_switch_age_minutes(pending_switch: dict | None, *, now: dt.datetime | None = None) -> float | None:
    if not isinstance(pending_switch, dict):
        return None
    requested_at = pending_switch.get("requested_at")
    if not requested_at or not isinstance(requested_at, str):
        return None
    try:
        requested = dt.datetime.fromisoformat(requested_at)
    except ValueError:
        return None
    if requested.tzinfo is None:
        requested = requested.replace(tzinfo=dt.timezone.utc)
    now = now or dt.datetime.now(dt.timezone.utc)
    return (now - requested).total_seconds() / 60.0

def _pending_switch_is_stale(
    pending_switch: dict | None,
    *,
    now: dt.datetime | None = None,
    db: Session | None = None,
) -> bool:
    age = _pending_switch_age_minutes(pending_switch, now=now)
    return age is not None and age > _pending_switch_ttl_minutes(db)


# Public surface (promoted from retired Stage-1 shim for single-writer centralization post-P3b).
# Callers (bot0, router, worker, persistence) now import from ledger.
def build_pending_switch(
    *,
    from_agent: str,
    to_agent: str,
    original_message: str,
    source_message_id: str | None = None,
    requested_at: str | None = None,
    decision_id: str | None = None,
    control_revision: int = 0,
    task_text: str | None = None,
) -> dict:
    return _build_pending_switch(
        from_agent=from_agent, to_agent=to_agent, original_message=original_message,
        source_message_id=source_message_id, requested_at=requested_at,
        decision_id=decision_id, control_revision=control_revision, task_text=task_text,
    )


def read_pending_switch(context: dict | None) -> dict | None:
    return _read_pending_switch(context)


def pending_switch_age_minutes(pending_switch: dict | None, *, now: dt.datetime | None = None) -> float | None:
    return _pending_switch_age_minutes(pending_switch, now=now)


def pending_switch_is_stale(
    pending_switch: dict | None,
    *,
    now: dt.datetime | None = None,
    db: Session | None = None,
) -> bool:
    return _pending_switch_is_stale(pending_switch, now=now, db=db)


def suspended_task_ttl_minutes(db: Session | None = None) -> float:
    """Public accessor for the suspended-task staleness horizon (default 24h),
    so consumers (e.g. orientation cards) compute staleness with the SAME TTL
    the prune sweep uses."""
    return _suspended_task_ttl_minutes(db)


# The switch accept/decline decision moved to the bounded classifier
# (conversation_control.classifier.classify_switch_reply) — no enumerated phrase
# lists. Natural phrasings ("start a new one", "scrap that, build it") are
# understood, not just the literal words.


def strip_private_stage1_updates(
    updates: dict | None,
) -> tuple[dict, dict[str, Any]]:
    """Remove Stage-1-only helper keys before persistence (inlined from the
    retired shim — single-writer consolidation)."""
    cleaned = dict(updates or {})
    metadata = {
        "pending_switch_resolution": cleaned.pop("_pending_switch_resolution", None),
        "pending_switch_from_agent": cleaned.pop("_pending_switch_from_agent", None),
        "pending_switch_to_agent": cleaned.pop("_pending_switch_to_agent", None),
    }
    return cleaned, metadata


def set_pending_switch_source_message_id(
    db: Session,
    *,
    conversation_id: str,
    tenant_id: str,
    source_message_id: str,
) -> None:
    """Fill in ``pending_switch.source_message_id`` after the user row exists.
    (Consolidated here as part of single-writer retirement of the Stage-1 shim.)
    """
    db.execute(
        text(
            """
            UPDATE conversations
               SET context = jsonb_set(
                       COALESCE(context, '{}'::jsonb),
                       '{pending_switch,source_message_id}',
                       CAST(:message_id AS jsonb),
                       true
                   ),
                   updated_at = now()
             WHERE conversation_id = :cid
               AND tenant_id = :tid
               AND context ? 'pending_switch'
            """
        ),
        {
            "message_id": json.dumps(source_message_id),
            "cid": conversation_id,
            "tid": tenant_id,
        },
    )


def _revision_fence_sql(expected_version: Optional[int]) -> str:
    """Optional WHERE clause fragment for optimistic concurrency (Model A)."""
    if expected_version is None:
        return ""
    return (
        " AND COALESCE((context->>'_control_revision')::int, 0) = :expected_version"
    )


def _raise_if_stale_update(
    db: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    expected_version: Optional[int],
    rowcount: int,
) -> None:
    if expected_version is None:
        return
    if rowcount and rowcount > 0:
        return
    from conversation_control_plane.failure_modes import StaleControlRevisionError

    actual = get_control_revision(db, tenant_id, conversation_id)
    raise StaleControlRevisionError(
        expected=int(expected_version),
        actual=actual,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
    )


def assert_expected_version(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    expected_version: Optional[int],
) -> int:
    """Fence a compound command: raise if expected_version mismatches live revision.

    When ``expected_version`` is None, returns the current revision without error
    (backward-compatible callers that do not yet carry a fence).
    """
    actual = get_control_revision(db, tenant_id, conversation_id)
    if expected_version is None:
        return actual
    if int(expected_version) != actual:
        from conversation_control_plane.failure_modes import StaleControlRevisionError

        raise StaleControlRevisionError(
            expected=int(expected_version),
            actual=actual,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
        )
    return actual


def _clear_context_keys(
    db: Session,
    *,
    conversation_id: str,
    tenant_id: str,
    keys: list[str] | tuple[str, ...],
    expected_version: Optional[int] = None,
) -> None:
    if not keys:
        return
    # Bump _control_revision in the same statement: any control-key clear is a
    # control mutation, and the monotonic revision is what the decision envelope
    # validates against (epic §8.2). Optional expected_version is Model A fencing.
    fence = _revision_fence_sql(expected_version)
    result = db.execute(
        text(
            f"""
            UPDATE conversations
               SET context = jsonb_set(
                       COALESCE(context, '{{}}'::jsonb) - CAST(:keys AS text[]),
                       ARRAY['_control_revision']::text[],
                       to_jsonb(COALESCE((context->>'_control_revision')::int, 0) + 1),
                       true
                   ),
                   updated_at = now()
             WHERE conversation_id = :cid AND tenant_id = :tid
             {fence}
            """
        ),
        {
            "keys": list(keys),
            "cid": conversation_id,
            "tid": tenant_id,
            **(
                {"expected_version": int(expected_version)}
                if expected_version is not None
                else {}
            ),
        },
    )
    _raise_if_stale_update(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        expected_version=expected_version,
        rowcount=int(getattr(result, "rowcount", 0) or 0),
    )


def _set_jsonb_key(
    db: Session,
    *,
    conversation_id: str,
    tenant_id: str,
    key: str,
    value: object,
    expected_version: Optional[int] = None,
) -> None:
    # Only ledger-controlled keys for the writer.
    allowed = {
        "pending_switch",
        "pending_question",
        "active_task",
        "suspended_tasks",
        "shadow_plan",
        "plan",
    }
    if key not in allowed:
        raise ValueError(f"Unsupported control key: {key}")
    # Set the control key AND bump _control_revision atomically in one UPDATE.
    # control_revision is monotonic metadata about control coherence (epic §8.2),
    # not rich content — it stays consistent with the lightweight-ledger model.
    fence = _revision_fence_sql(expected_version)
    result = db.execute(
        text(
            f"""
            UPDATE conversations
               SET context = jsonb_set(
                       jsonb_set(
                           COALESCE(context, '{{}}'::jsonb),
                           ARRAY[:key]::text[],
                           CAST(:value AS jsonb),
                           true
                       ),
                       ARRAY['_control_revision']::text[],
                       to_jsonb(COALESCE((context->>'_control_revision')::int, 0) + 1),
                       true
                   ),
                   updated_at = now()
             WHERE conversation_id = :cid AND tenant_id = :tid
             {fence}
            """
        ),
        {
            "key": key,
            "value": json.dumps(value),
            "cid": conversation_id,
            "tid": tenant_id,
            **(
                {"expected_version": int(expected_version)}
                if expected_version is not None
                else {}
            ),
        },
    )
    _raise_if_stale_update(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        expected_version=expected_version,
        rowcount=int(getattr(result, "rowcount", 0) or 0),
    )

# Control keys that the ledger is allowed to touch (single-writer enforcement).
from conversation_control_plane.ledger_keys import LEDGER_MUTABLE_PROJECTION_KEYS

_CONTROL_KEYS = set(LEDGER_MUTABLE_PROJECTION_KEYS)


# -----------------------------------------------------------------------------
# Public ledger API (matches epic + TurnPlan / ControlState in contract.py)
# -----------------------------------------------------------------------------

def get_control_state(
    db: Session,
    tenant_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Return the current control snapshot for a conversation.

    In P2a this is mostly a read of the context JSONB (plus the persisted
    agent_type column as summary). Later it may be promoted to a dedicated
    table if write/query patterns justify it (the post-P3b checkpoint).
    """
    row = db.execute(
        text(
            """
            SELECT context, agent_type
              FROM conversations
             WHERE conversation_id = :cid AND tenant_id = :tid
            """
        ),
        {"cid": conversation_id, "tid": tenant_id},
    ).fetchone()

    if not row:
        return {}

    context = row[0] or {}
    from conversation_control_plane.pending_question import read_pending_question

    return {
        "agent_type": row[1],
        "pending_switch": _read_pending_switch(context),
        "pending_question": read_pending_question(context),
        "active_task": context.get("active_task") if isinstance(context.get("active_task"), dict) else None,
        "suspended_tasks": [
            t for t in (context.get("suspended_tasks") or [])
            if isinstance(t, dict)
        ],
        # Monotonic control-coherence counter (epic §8.2). Decision envelopes are
        # issued against this; a worker compares it to detect a stale decision.
        "control_revision": int(context.get("_control_revision") or 0),
        # Durable orchestrator plan (P4). Must be returned here or decide_turn's
        # plan-precedence check (current_plan = control.get("plan")) can never see it.
        "plan": context.get("plan") if isinstance(context.get("plan"), dict) else None,
    }


def get_control_revision(
    db: Session,
    tenant_id: str,
    conversation_id: str,
) -> int:
    """Current monotonic control_revision for a conversation (0 if none/absent).

    Bumped by every control-key mutation (`_set_jsonb_key` / `_clear_context_keys`).
    The decision envelope records the revision it was issued against so the worker
    can no-op a stale decision instead of acting on moved control state."""
    row = db.execute(
        text(
            "SELECT COALESCE((context->>'_control_revision')::int, 0) "
            "FROM conversations WHERE conversation_id = :cid AND tenant_id = :tid"
        ),
        {"cid": conversation_id, "tid": tenant_id},
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# S5: unified handoff primitive (single ledger-SDK entry for all handoffs:
# silent, accepted, catalog, envelope). Replaces scattered logic.
def handoff(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    target_agent: str,
    task_text: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Single entry for handoff. Sets pending or begins task.
    Called from decide_turn / dispatch for coherence.
    """
    from conversation_control_plane.contract import ledger_kind_for_agent

    kind = ledger_kind_for_agent(target_agent) or "handoff"
    try:
        return begin_task(
            db, tenant_id, conversation_id,
            agent=target_agent,
            phase="active",
            awaiting="handoff",
            pending_ref=None,
            kind=kind,
            payload={"task_text": task_text, "reason": reason or ""},
        )
    except Exception:  # noqa: BLE001
        return {}


def propose_switch(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    from_agent: str,
    to_agent: str,
    original_message: str,
    source_message_id: Optional[str] = None,
    decision_id: Optional[str] = None,
    control_revision: int = 0,
    task_text: Optional[str] = None,
    command_id: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> dict[str, Any]:
    """Record a pending agent switch. Single writer for pending_switch key."""
    from conversation_control_plane.ledger_journal import (
        append_control_event,
        new_command_id,
    )

    payload = _build_pending_switch(
        from_agent=from_agent,
        to_agent=to_agent,
        original_message=original_message,
        source_message_id=source_message_id,
        decision_id=decision_id,
        control_revision=control_revision,
        task_text=task_text,
    )
    cmd = (command_id or new_command_id()).strip()
    rev_before = get_control_revision(db, tenant_id, conversation_id)
    _set_jsonb_key(
        db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        key="pending_switch",
        value=payload,
        expected_version=expected_version,
    )
    rev = get_control_revision(db, tenant_id, conversation_id)
    append_control_event(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event_type="switch_proposed",
        command_id=cmd,
        agent=from_agent,
        control_revision_before=rev_before,
        control_revision_after=rev,
        source_message_id=source_message_id,
        causation_id=decision_id,
        payload={
            "from_agent": from_agent,
            "to_agent": to_agent,
            "source_message_id": source_message_id,
            "decision_id": decision_id,
        },
    )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="agent_switch_proposed",
        details={
            "from_agent": from_agent,
            "to_agent": to_agent,
            "source_message_id": source_message_id,
            "command_id": cmd,
        },
    )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="task_suspended",
        details={
            "agent": from_agent,
            "awaiting": "pending_switch_confirmation",
            "to_agent": to_agent,
            "suspend_reason": "pending_switch_proposed",
        },
    )
    return payload


def resolve_switch(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    accepted: bool,
    command_id: Optional[str] = None,
    expected_version: Optional[int] = None,
    # Atomic AcceptSwitch compound options (ignored when accepted=False).
    begin_target: bool = False,
    begin_phase: str = "ready",
    begin_awaiting: str = "task_request",
    begin_pending_ref: Optional[str] = None,
    begin_kind: Optional[str] = None,
    begin_payload: Optional[dict[str, Any]] = None,
    suspend_active_on_accept: bool = True,
) -> Optional[dict[str, Any]]:
    """Accept or decline a pending switch.

    Model A atomic AcceptSwitch (when ``accepted`` and ``begin_target``): under
    one FOR UPDATE, optionally suspend active_task, clear pending_switch, begin
    the target agent task, and append a single journal event.
    """
    from conversation_control_plane.ledger_journal import (
        append_control_event,
        find_event_by_command_id,
        new_command_id,
    )

    cmd = (command_id or new_command_id()).strip()
    # Idempotency: prior switch resolution with same command_id → return prior pending snapshot.
    try:
        prior = find_event_by_command_id(
            db, tenant_id=tenant_id, conversation_id=conversation_id, command_id=cmd,
        )
        if prior and str(prior.get("event_type") or "") in (
            "switch_accepted",
            "switch_declined",
        ):
            payload = prior.get("payload_json") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:  # noqa: BLE001
                    payload = {}
            if isinstance(payload, dict) and payload.get("pending"):
                return payload.get("pending")
            return {"_idempotent": True, "command_id": cmd}
    except Exception:  # noqa: BLE001
        pass

    db.execute(
        text(
            """
            SELECT 1 FROM conversations
             WHERE conversation_id = :cid AND tenant_id = :tid
             FOR UPDATE
            """
        ),
        {"cid": conversation_id, "tid": tenant_id},
    )
    assert_expected_version(db, tenant_id, conversation_id, expected_version)

    current = get_control_state(db, tenant_id, conversation_id)
    pending = current.get("pending_switch")
    if not pending:
        return None

    suspended_task_id = None
    if accepted and suspend_active_on_accept and current.get("active_task"):
        active = current.get("active_task")
        if isinstance(active, dict) and active.get("agent"):
            suspended_task_id = active.get("task_id")
            # Fence already applied once for this compound; nested writes unfenced.
            suspend_active(
                db, tenant_id, conversation_id, reason="switch_accepted",
            )

    _clear_context_keys(
        db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        keys=("pending_switch",),
    )

    begun: Optional[dict[str, Any]] = None
    to_agent = str(pending.get("to_agent") or "").strip()
    if accepted and to_agent:
        _sync_agent_type_column(
            db,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            agent=to_agent,
        )
        if begin_target:
            ref = begin_pending_ref or f"handoff:{to_agent}:{conversation_id}"
            begun = begin_task(
                db,
                tenant_id,
                conversation_id,
                agent=to_agent,
                phase=begin_phase,
                awaiting=begin_awaiting,
                pending_ref=ref,
                kind=begin_kind,
                payload=begin_payload,
            )

    resolution = "accepted" if accepted else "declined"
    event_name = "agent_switch_confirmed" if accepted else "agent_switch_declined"
    journal_type = "switch_accepted" if accepted else "switch_declined"
    rev = get_control_revision(db, tenant_id, conversation_id)
    # Fail-closed journal (same TX as projection mutations).
    append_control_event(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event_type=journal_type,
        command_id=cmd,
        task_id=(begun or {}).get("task_id") if begun else suspended_task_id,
        agent=to_agent or pending.get("from_agent"),
        kind=begin_kind,
        control_revision_after=rev,
        payload={
            "resolution": resolution,
            "from_agent": pending.get("from_agent"),
            "to_agent": pending.get("to_agent"),
            "pending": pending,
            "begin_target": bool(begin_target and accepted),
            "suspended_task_id": suspended_task_id,
        },
    )

    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event=event_name,
        details={
            "from_agent": pending.get("from_agent"),
            "to_agent": pending.get("to_agent"),
            "resolution": resolution,
            "command_id": cmd,
            "atomic_begin": bool(begun),
        },
    )
    if begun is not None:
        pending = {**pending, "_begun_task": begun, "_command_id": cmd}
    return pending


def accept_switch(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    command_id: Optional[str] = None,
    expected_version: Optional[int] = None,
    begin_phase: str = "ready",
    begin_awaiting: str = "task_request",
    begin_pending_ref: Optional[str] = None,
    begin_kind: Optional[str] = None,
    begin_payload: Optional[dict[str, Any]] = None,
    skip_begin: bool = False,
) -> Optional[dict[str, Any]]:
    """Atomic AcceptSwitch compound command (Model A).

    FOR UPDATE → fence → suspend prior active → clear pending_switch →
    begin target (unless ``skip_begin``) → one journal ``switch_accepted``.
    """
    return resolve_switch(
        db,
        tenant_id,
        conversation_id,
        accepted=True,
        command_id=command_id,
        expected_version=expected_version,
        begin_target=not skip_begin,
        begin_phase=begin_phase,
        begin_awaiting=begin_awaiting,
        begin_pending_ref=begin_pending_ref,
        begin_kind=begin_kind,
        begin_payload=begin_payload,
        suspend_active_on_accept=True,
    )


def set_pending_question(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    kind: str,
    source_tool: str,
    read_kind: str = "",
    candidates: list | None = None,
    original_workflow_ref: str = "",
    original_query: str = "",
    source_message_id: Optional[str] = None,
    purpose: str = "",
) -> dict[str, Any]:
    """Record a bot0 detour disambiguation that owns the next pick reply.

    ``purpose`` isolates ordinals across multi-turn streams (cost vs inventory vs
    scorecards) — see ``task_pin_contract.PURPOSE_*``.
    """
    from conversation_control_plane.pending_question import build_pending_question

    payload = build_pending_question(
        kind=kind,
        source_tool=source_tool,
        read_kind=read_kind,
        candidates=candidates,
        original_workflow_ref=original_workflow_ref,
        original_query=original_query,
        source_message_id=source_message_id,
        purpose=purpose,
    )
    _set_jsonb_key(
        db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        key="pending_question",
        value=payload,
    )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="pending_question_opened",
        details={
            "kind": kind,
            "source_tool": source_tool,
            "candidate_count": len(payload.get("candidates") or []),
        },
    )
    return payload


def clear_pending_question(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    reason: str = "resolved",
) -> None:
    """Drop ledger-tracked pending-question state."""
    current = get_control_state(db, tenant_id, conversation_id)
    pending = current.get("pending_question")
    if not pending:
        return
    _clear_context_keys(
        db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        keys=("pending_question",),
    )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="pending_question_cleared",
        details={"reason": reason, "kind": pending.get("kind")},
    )


def _sync_agent_type_column(
    db: Session,
    *,
    conversation_id: str,
    tenant_id: str,
    agent: Optional[str],
) -> None:
    """T2 (turn-integrity epic): write-through the conversations.agent_type
    summary column. The ledger's active_task.agent is THE authority for who
    owns the conversation; the column is a denormalized summary the ledger
    maintains on every transition so live readers (context hydration, sticky
    gates, guardrail agent resolution) can never diverge from the ledger.
    This retires the P2a-era rule that the ledger must not touch the column —
    that rule was correct in shadow mode and wrong once decide_turn became
    authoritative (the D1 flip)."""
    if not agent:
        return
    db.execute(
        text(
            """
            UPDATE conversations
               SET agent_type = :agent_type,
                   updated_at = now()
             WHERE conversation_id = :cid AND tenant_id = :tid
            """
        ),
        {"agent_type": agent, "cid": conversation_id, "tid": tenant_id},
    )


def sync_agent_type_summary(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    agent: Optional[str],
) -> Optional[str]:
    """The ONLY sanctioned agent_type column write outside the ledger's own
    transitions (T2). Callers that used to write the column directly (the
    Stage-1 shim on the router + worker result paths) route through here.

    Reconciling: while a task is ACTIVE, the ledger is the authority — a
    requested summary that disagrees with active_task.agent is overridden to
    the task's agent, with ``ledger_agent_type_conflict`` telemetry (authority
    before recovery: the column can no longer be steered away from the ledger
    by a stray context_update). With no active task the requested summary is
    written as-is. Returns the EFFECTIVE agent written (or None if none)."""
    if not agent:
        return None
    state = get_control_state(db, tenant_id, conversation_id)
    active = state.get("active_task") if isinstance(state.get("active_task"), dict) else None
    effective = agent
    task_agent = (active or {}).get("agent")
    if task_agent and task_agent != agent:
        effective = task_agent
        _emit(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            event="ledger_agent_type_conflict",
            details={
                "requested_agent_type": agent,
                "authoritative_agent_type": effective,
                "source": "summary_sync",
            },
        )
    _sync_agent_type_column(
        db, conversation_id=conversation_id, tenant_id=tenant_id, agent=effective,
    )
    return effective


def begin_task(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    agent: str,
    phase: str,
    awaiting: Optional[str] = None,
    pending_ref: Optional[str] = None,
    kind: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    task_id: Optional[str] = None,
    command_id: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> dict[str, Any]:
    """Start (or re-start) an active task. Single writer.

    Called from decide_turn (when it decides an active_task should exist) and
    from the mirrors in bot0.py / worker. Writes the JSONB ledger keys AND
    writes-through the conversations.agent_type summary column (T2) so the
    two can no longer diverge.

    Model A: assigns immutable ``task_id``, appends ``task_began`` journal row
    (when events table exists), and emits platform telemetry.

    ``kind`` names a sub-flow the agent owns (e.g. "drafting"); ``payload`` is
    thin control metadata (pins/gates) — never IR/graph blobs.
    ``expected_version`` fences the projection write (None = no fence).
    """
    from conversation_control_plane.ledger_journal import (
        append_control_event,
        find_event_by_command_id,
        new_command_id,
        new_task_id,
    )
    from conversation_control_plane.task_phase_registry import (
        require_valid_task_fields,
    )

    cmd = (command_id or new_command_id()).strip()
    # Idempotency: same command_id → return prior active_task snapshot if possible.
    prior = find_event_by_command_id(
        db, tenant_id=tenant_id, conversation_id=conversation_id, command_id=cmd,
    )
    if prior and prior.get("event_type") == "task_began":
        state = get_control_state(db, tenant_id, conversation_id)
        active = state.get("active_task")
        if isinstance(active, dict) and active.get("task_id") == prior.get("task_id"):
            return active

    # Model A production-grade: invalid phase/awaiting is reject, not log-and-persist.
    validation = require_valid_task_fields(
        agent=agent,
        phase=phase,
        awaiting=awaiting,
        kind=kind,
    )
    effective_kind = validation.normalized_kind if validation.normalized_kind else kind

    rev_before = get_control_revision(db, tenant_id, conversation_id)
    tid = (task_id or new_task_id()).strip()
    task = {
        "agent": agent,
        "phase": phase,
        "awaiting": awaiting,
        "pending_ref": pending_ref,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "task_id": tid,
    }
    if effective_kind is not None:
        task["kind"] = effective_kind
    if payload is not None:
        from conversation_control_plane.control_payload import (
            sanitize_control_payload,
        )

        # B5: strip IR/draft/graph — pins only on the control projection.
        task["payload"] = sanitize_control_payload(
            payload, kind=effective_kind if isinstance(effective_kind, str) else None,
        )
    _set_jsonb_key(
        db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        key="active_task",
        value=task,
        expected_version=expected_version,
    )
    _sync_agent_type_column(
        db, conversation_id=conversation_id, tenant_id=tenant_id, agent=agent,
    )
    details: dict[str, Any] = {
        "agent": agent, "phase": phase, "awaiting": awaiting, "task_id": tid,
        "command_id": cmd,
    }
    if effective_kind:
        details["kind"] = effective_kind
    # Fail-closed journal (same TX as projection) — do not swallow.
    rev = get_control_revision(db, tenant_id, conversation_id)
    append_control_event(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event_type="task_began",
        command_id=cmd,
        task_id=tid,
        agent=agent,
        kind=effective_kind if isinstance(effective_kind, str) else None,
        control_revision_before=rev_before,
        control_revision_after=rev,
        payload={"phase": phase, "awaiting": awaiting, "pending_ref": pending_ref},
    )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="task_began",
        details=details,
    )
    return task

# P4a support: write a shadow plan into the control state (visible in admin
# panel and for P4b+ execution). The orchestrator agent (later) will own
# the cognition; the ledger just stores the durable plan object.
def record_shadow_plan(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    plan: dict[str, Any],
) -> None:
    """Store a P4a shadow plan in the conversation's control state."""
    _set_jsonb_key(
        db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        key="shadow_plan",
        value=plan,
    )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="plan_shadow_generated",
        details={"goal": plan.get("goal"), "task_count": len(plan.get("tasks", []))},
    )


def record_plan(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    plan: dict[str, Any],
) -> None:
    """Store/activate the durable orchestrator plan (P4b+).

    Writes the canonical 'plan' key (see ControlState.plan). This is the
    active plan the orchestrator agent and plan-aware resume will consult.
    Single-writer discipline applies.
    """
    _set_jsonb_key(
        db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        key="plan",
        value=plan,
    )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="plan_began",
        details={"goal": plan.get("goal"), "task_count": len(plan.get("tasks", []))},
    )


def update_plan_task_status(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    task_id: str,
    status: str,
    output_ref: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """P4c: update a single task inside the active 'plan' JSONB (single writer).

    Status values: "pending" | "executing" | "done" | "failed" | "abandoned".
    Emits plan_task_completed or plan_repair_required as appropriate.
    Non-mutating read-modify via jsonb ops or full plan rewrite under lock for small object.
    """
    # For simplicity in P4c start: read current plan, patch the matching task, write back.
    # (In production would use targeted jsonb_set on the tasks array element.)
    current = get_control_state(db, tenant_id, conversation_id)
    plan = current.get("plan") or {}
    tasks = plan.get("tasks") or []
    changed = False
    for t in tasks:
        if t.get("id") == task_id:
            t["status"] = status
            if output_ref is not None:
                t["output_ref"] = output_ref
            if error is not None:
                t["error"] = error
            changed = True
            break
    if changed:
        _set_jsonb_key(db, conversation_id=conversation_id, tenant_id=tenant_id, key="plan", value=plan)
        ev = "plan_task_completed" if status == "done" else ("plan_repair_required" if status == "failed" else "plan_task_dispatched")
        _emit(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            event=ev,
            details={"task_id": task_id, "status": status, "output_ref": output_ref},
        )


_WORKFLOW_AUTHORING_AGENTS = frozenset({"workflow_builder", "workflow_editor"})


def _conv_id_from_pending_ref(ref: str | None) -> str:
    return (ref or "").rsplit(":", 1)[-1].strip()


def _prune_redundant_suspended_for_active_authoring(
    control: dict[str, Any],
) -> list[dict[str, Any]]:
    """Drop paused duplicates/noise while workflow_builder/editor actively owns this thread."""
    active = control.get("active_task")
    suspended = [
        t for t in (control.get("suspended_tasks") or []) if isinstance(t, dict)
    ]
    if not isinstance(active, dict):
        return suspended
    agent = str(active.get("agent") or "").strip()
    if agent not in _WORKFLOW_AUTHORING_AGENTS:
        return suspended
    active_conv = _conv_id_from_pending_ref(active.get("pending_ref"))
    if not active_conv:
        return suspended
    kept: list[dict[str, Any]] = []
    for entry in suspended:
        ref = entry.get("pending_ref") or ""
        conv = _conv_id_from_pending_ref(ref)
        entry_agent = str(entry.get("agent") or "").strip()
        reason = str(entry.get("suspend_reason") or "")
        if (
            conv == active_conv
            and entry_agent in _WORKFLOW_AUTHORING_AGENTS
        ):
            continue
        if reason == "drafting_detour" and entry.get("kind") == "drafting":
            continue
        kept.append(entry)
    return kept


def prune_stale_ledger_state(db: Session, tenant_id: str, conversation_id: str) -> None:
    """TTL sweeps and stale pruning per the epic (pending_switch 10m, suspended 24h, CONSULTING weak TTL).

    Emits task_resume_stale for old suspended tasks.
    Called before routing decisions to prevent old suspended tasks hijacking follow-ups.
    """
    control = get_control_state(db, tenant_id, conversation_id)

    # Active authoring hygiene — prune duplicate/noise suspended cards (conv_30cc0299).
    suspended = control.get("suspended_tasks") or []
    deduped = _prune_redundant_suspended_for_active_authoring(control)
    if len(deduped) != len(suspended):
        _set_jsonb_key(
            db,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            key="suspended_tasks",
            value=deduped,
        )
        control = {**control, "suspended_tasks": deduped}

    # pending_switch short TTL
    ps = control.get("pending_switch")
    if ps and _pending_switch_is_stale(ps, db=db):
        _clear_context_keys(db, conversation_id=conversation_id, tenant_id=tenant_id, keys=("pending_switch",))
        _emit(db, tenant_id=tenant_id, conversation_id=conversation_id, event="task_resume_stale", details={"reason": "pending_switch_ttl"})

    # suspended tasks >24h horizon -> stale
    suspended = control.get("suspended_tasks") or []
    kept = []
    now = dt.datetime.now(dt.timezone.utc)
    for t in suspended:
        if isinstance(t, dict):
            age_min = _pending_switch_age_minutes({"requested_at": t.get("suspended_at")}, now=now)  # reuse age fn
            if age_min is not None and age_min > _suspended_task_ttl_minutes(db):
                _emit(db, tenant_id=tenant_id, conversation_id=conversation_id, event="task_resume_stale", details={"agent": t.get("agent"), "reason": "suspended_ttl"})
            else:
                kept.append(t)
    if len(kept) != len(suspended):
        _set_jsonb_key(db, conversation_id=conversation_id, tenant_id=tenant_id, key="suspended_tasks", value=kept)


def update_phase(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    agent: str,
    phase: str,
    awaiting: Optional[str] = None,
    pending_ref: Optional[str] = None,
    kind: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    expected_version: Optional[int] = None,
) -> dict[str, Any]:
    """Update the phase/awaiting of the current active task (no change to agent).

    ``pending_ref`` is carried through when supplied (epic §9.1 — a CONTINUE may
    change which agent-owned artifact the task points at); when None the existing
    ``pending_ref`` is preserved. ``payload`` (a ledger-tracked task's carried
    state, e.g. a draft being refined) is likewise updated when supplied and
    preserved when None. ``kind`` is preserved automatically, or set when supplied
    by a caller that is upgrading a generic active task into a typed sub-flow.
    ``expected_version`` fences the projection write (None = no fence)."""
    # Lock for concurrency safety (invariant 7) on active_task.
    db.execute(
        text(
            "SELECT 1 FROM conversations WHERE conversation_id = :cid AND tenant_id = :tid FOR UPDATE"
        ),
        {"cid": conversation_id, "tid": tenant_id},
    )
    assert_expected_version(db, tenant_id, conversation_id, expected_version)
    current = get_control_state(db, tenant_id, conversation_id)
    task = current.get("active_task") or {}
    if task.get("agent") != agent:
        # Defensive — caller should have validated via resolve_pending first
        task = {"agent": agent}

    from conversation_control_plane.task_phase_registry import (
        require_valid_task_fields,
    )

    # Preserve task_id across phase updates (immutable instance identity).
    existing_task_id = task.get("task_id") if isinstance(task, dict) else None
    effective_kind = kind if kind is not None else task.get("kind")
    validation = require_valid_task_fields(
        agent=agent,
        phase=phase,
        awaiting=awaiting,
        kind=effective_kind if isinstance(effective_kind, str) else None,
    )
    task["phase"] = phase
    task["awaiting"] = awaiting
    if existing_task_id:
        task["task_id"] = existing_task_id
    if pending_ref is not None:
        task["pending_ref"] = pending_ref
    if validation.normalized_kind:
        task["kind"] = validation.normalized_kind
    elif kind is not None:
        task["kind"] = kind
    if payload is not None:
        from conversation_control_plane.control_payload import (
            sanitize_control_payload,
        )

        task["payload"] = sanitize_control_payload(
            payload,
            kind=(
                validation.normalized_kind
                if isinstance(validation.normalized_kind, str)
                else (kind if isinstance(kind, str) else None)
            ),
        )
    # Fence already applied at lock time; nested write unfenced in same transaction.
    _set_jsonb_key(db, conversation_id=conversation_id, tenant_id=tenant_id, key="active_task", value=task)
    # T2: keep the summary column aligned on continuation turns too.
    _sync_agent_type_column(
        db, conversation_id=conversation_id, tenant_id=tenant_id, agent=agent,
    )
    return task


def suspend_active(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    reason: str,
) -> None:
    """Move whatever is in active_task into the suspended_tasks list."""
    # Lock for concurrency safety (invariant 7) on the list-valued suspended_tasks key.
    db.execute(
        text(
            "SELECT 1 FROM conversations WHERE conversation_id = :cid AND tenant_id = :tid FOR UPDATE"
        ),
        {"cid": conversation_id, "tid": tenant_id},
    )
    current = get_control_state(db, tenant_id, conversation_id)
    active = current.get("active_task")
    if not active:
        return

    suspended = list(current.get("suspended_tasks") or [])
    # Dedupe before appending. "new task while active" fires on EVERY re-trigger, and this
    # used to append a near-identical entry each time — letting the ledger accumulate 9-15
    # duplicates of the SAME paused work. That clutter cascaded: orientation echoed
    # "Workflow Builder, Workflow Builder, Workflow Builder", and the decider's "what to do
    # next" went generic (it could not pick cleanly among many near-duplicate suspended
    # tasks). Drop any existing entry for the same paused work (same pending_ref; else same
    # agent with no ref) so suspended_tasks holds at most one entry per distinct paused task.
    _ref = active.get("pending_ref")
    _agent = active.get("agent")
    suspended = [
        t for t in suspended
        if not (
            isinstance(t, dict)
            and (
                (_ref and t.get("pending_ref") == _ref)
                or (not _ref and t.get("agent") == _agent and not t.get("pending_ref"))
            )
        )
    ]
    suspended.append({**active, "suspended_at": dt.datetime.now(dt.timezone.utc).isoformat(), "suspend_reason": reason})
    _set_jsonb_key(db, conversation_id=conversation_id, tenant_id=tenant_id, key="suspended_tasks", value=suspended)
    _clear_context_keys(db, conversation_id=conversation_id, tenant_id=tenant_id, keys=("active_task",))
    # T2: with no active task the front door owns the conversation. A
    # suspend-then-begin transition overwrites this in the same transaction.
    _sync_agent_type_column(
        db, conversation_id=conversation_id, tenant_id=tenant_id, agent="bot0",
    )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="task_suspended",
        details={"agent": active.get("agent"), "reason": reason},
    )


def resume_task(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    agent: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Resume a previously suspended task (after resolve_pending succeeded).

    Prefer ``task_id`` (immutable instance identity). ``agent`` alone is
    ambiguous when multiple suspended tasks share a specialist — used only as
    fallback when ``task_id`` is absent.
    """
    # Lock for concurrency safety (invariant 7) on suspended_tasks / active_task.
    db.execute(
        text(
            "SELECT 1 FROM conversations WHERE conversation_id = :cid AND tenant_id = :tid FOR UPDATE"
        ),
        {"cid": conversation_id, "tid": tenant_id},
    )
    current = get_control_state(db, tenant_id, conversation_id)
    suspended = [t for t in (current.get("suspended_tasks") or []) if isinstance(t, dict)]
    target = None
    remaining: list[dict[str, Any]] = []
    want_tid = (task_id or "").strip() or None
    want_agent = (agent or "").strip() or None
    for t in suspended:
        if target is None:
            if want_tid and t.get("task_id") == want_tid:
                target = t
                continue
            if not want_tid and want_agent and t.get("agent") == want_agent:
                target = t
                continue
        remaining.append(t)

    if not target:
        return None

    resume_agent = str(target.get("agent") or want_agent or "bot0")
    _set_jsonb_key(db, conversation_id=conversation_id, tenant_id=tenant_id, key="active_task", value=target)
    if remaining != suspended:
        _set_jsonb_key(db, conversation_id=conversation_id, tenant_id=tenant_id, key="suspended_tasks", value=remaining)
    # T2: the resumed task's agent owns the conversation again.
    _sync_agent_type_column(
        db, conversation_id=conversation_id, tenant_id=tenant_id, agent=resume_agent,
    )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="task_resumed",
        details={
            "agent": resume_agent,
            "task_id": target.get("task_id"),
            "resume_kind": "ledger_resume_by_task_id" if want_tid else "ledger_resume",
        },
    )
    return target


def drop_suspended_task(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    pending_ref: Optional[str] = None,
    agent: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Remove a SUSPENDED task from the ledger WITHOUT resuming it — the clear/abandon-by-reference
    point (sibling of ``resume_task``: same suspended_tasks rewrite, but the target is DISCARDED, not
    promoted to active). Matches by ``pending_ref`` (preferred — unique per session) or, failing that,
    the first entry by ``agent``. Returns the dropped task, or None when no suspended entry matches.
    The caller deletes the matching pending-workflow record (DB + memory)."""
    db.execute(
        text(
            "SELECT 1 FROM conversations WHERE conversation_id = :cid AND tenant_id = :tid FOR UPDATE"
        ),
        {"cid": conversation_id, "tid": tenant_id},
    )
    current = get_control_state(db, tenant_id, conversation_id)
    suspended = [t for t in (current.get("suspended_tasks") or []) if isinstance(t, dict)]
    target = None
    remaining = []
    for t in suspended:
        _match = (
            (pending_ref and t.get("pending_ref") == pending_ref)
            or (not pending_ref and agent and t.get("agent") == agent)
        )
        if _match and target is None:
            target = t
        else:
            remaining.append(t)

    if not target:
        return None

    if remaining != suspended:
        _set_jsonb_key(
            db, conversation_id=conversation_id, tenant_id=tenant_id,
            key="suspended_tasks", value=remaining,
        )
    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event="task_cleared",
        details={
            "agent": target.get("agent"),
            "pending_ref": target.get("pending_ref"),
            "reason": "user_clear",
        },
    )
    return target


def complete_task(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    agent: str,
    reason: str = "complete",
    task_id: Optional[str] = None,
    command_id: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> None:
    """Task is done. Clear active_task + pending_switch + all legacy sticky signals.

    ``reason`` must distinguish business outcomes:
      complete | abandon | failed | expired | superseded

    Journal event types: task_completed | task_abandoned | task_failed | …
    Projection clear is shared; event identity is not.
    ``expected_version`` fences the clear (None = no fence).
    """
    from conversation_control_plane.ledger_journal import (
        append_control_event,
        find_event_by_command_id,
        new_command_id,
    )

    reason = (reason or "complete").strip().lower() or "complete"
    event_type = {
        "complete": "task_completed",
        "abandon": "task_abandoned",
        "failed": "task_failed",
        "expired": "task_expired",
        "superseded": "task_superseded",
    }.get(reason, "task_completed")
    cmd = (command_id or new_command_id()).strip()

    # Use a single FOR UPDATE transaction for the multi-key clear (invariant 7 for concurrency;
    # single-writer is invariant 8).
    db.execute(
        text(
            """
            SELECT 1 FROM conversations
             WHERE conversation_id = :cid AND tenant_id = :tid
             FOR UPDATE
            """
        ),
        {"cid": conversation_id, "tid": tenant_id},
    )
    assert_expected_version(db, tenant_id, conversation_id, expected_version)

    # Idempotency: prior complete/abandon with same command_id → no-op.
    prior = find_event_by_command_id(
        db, tenant_id=tenant_id, conversation_id=conversation_id, command_id=cmd,
    )
    if prior and str(prior.get("event_type") or "").startswith("task_"):
        return

    state = get_control_state(db, tenant_id, conversation_id)
    active = state.get("active_task") if isinstance(state.get("active_task"), dict) else {}
    resolved_task_id = task_id or (active or {}).get("task_id")
    kind = (active or {}).get("kind")
    rev_before = int(state.get("control_revision") or 0)

    # Clear the control keys we own.
    keys_to_clear = ["active_task", "pending_switch"]
    # Also clear transitional legacy signals so nothing can resurrect them.
    keys_to_clear.extend(["advisor_active", "pipeline_step", "create_flow_state"])

    # Fence already applied; nested clear unfenced in same transaction.
    _clear_context_keys(
        db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        keys=tuple(keys_to_clear),
    )

    # T2: the canonical release point returns ownership to the front door.
    _sync_agent_type_column(
        db, conversation_id=conversation_id, tenant_id=tenant_id, agent="bot0",
    )

    # Fail-closed journal — same TX as projection clear.
    rev = get_control_revision(db, tenant_id, conversation_id)
    append_control_event(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event_type=event_type,
        command_id=cmd,
        task_id=resolved_task_id,
        agent=agent,
        kind=kind if isinstance(kind, str) else None,
        control_revision_before=rev_before,
        control_revision_after=rev,
        payload={"reason": reason},
    )

    _emit(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        event=event_type,
        details={
            "agent": agent,
            "reason": reason,
            "task_id": resolved_task_id,
            "command_id": cmd,
        },
    )


def finish_active_task(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    agent: str,
    context: Optional[dict[str, Any]] = None,
    reason: str = "complete",
    task_id: Optional[str] = None,
    command_id: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> None:
    """Complete or abandon the active task with Model A identity fields.

    Prefer this over bare ``complete_task`` from first-class handlers so
    ``task_id`` is always resolved from the ledger projection when the
    caller only has the turn ``context`` snapshot.
    """
    resolved = task_id
    if not resolved:
        active: dict[str, Any] = {}
        if isinstance(context, dict):
            at = context.get("active_task")
            if isinstance(at, dict):
                active = at
        if not active:
            state = get_control_state(db, tenant_id, conversation_id)
            at2 = state.get("active_task")
            if isinstance(at2, dict):
                active = at2
        resolved = active.get("task_id") if isinstance(active.get("task_id"), str) else None
    complete_task(
        db,
        tenant_id,
        conversation_id,
        agent=agent,
        reason=reason,
        task_id=resolved,
        command_id=command_id,
        expected_version=expected_version,
    )


def apply_transition(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    agent: str,
    transition: Any,
    phase: Optional[str] = None,
    awaiting: Optional[str] = None,
    pending_ref: Optional[str] = None,
    kind: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    task_id: Optional[str] = None,
    command_id: Optional[str] = None,
    outcome_reason: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> None:
    """The single mapping from an agent's declared lifecycle transition to ledger
    writes (epic §9.1). Agents are executors that DECLARE a ``TaskTransition``;
    the control plane (here) is the sole writer that effects it.

        BEGIN    → begin_task          CONTINUE → update_phase
        COMPLETE → complete_task(reason=complete)
        ABANDON  → complete_task(reason=abandon)  # distinct event identity
        NONE     → no control mutation (the transcript still persists upstream)

    Centralizing this is what lets the retirement slices delete the scattered
    ad-hoc control writes: every control mutation now has exactly one path in."""
    from conversation_control_plane.contract import TaskTransition

    t = transition
    if t == TaskTransition.BEGIN:
        begin_task(
            db, tenant_id, conversation_id,
            agent=agent, phase=phase or "active",
            awaiting=awaiting, pending_ref=pending_ref,
            kind=kind, payload=payload, task_id=task_id, command_id=command_id,
            expected_version=expected_version,
        )
    elif t == TaskTransition.CONTINUE:
        update_phase(
            db, tenant_id, conversation_id,
            agent=agent, phase=phase or "active",
            awaiting=awaiting, pending_ref=pending_ref,
            kind=kind, payload=payload,
            expected_version=expected_version,
        )
    elif t == TaskTransition.COMPLETE:
        complete_task(
            db, tenant_id, conversation_id, agent=agent,
            reason=outcome_reason or "complete",
            task_id=task_id, command_id=command_id,
            expected_version=expected_version,
        )
    elif t == TaskTransition.ABANDON:
        complete_task(
            db, tenant_id, conversation_id, agent=agent,
            reason=outcome_reason or "abandon",
            task_id=task_id, command_id=command_id,
            expected_version=expected_version,
        )
    # TaskTransition.NONE → intentional no-op (no control mutation).


def apply_transition_request(
    db: Session,
    tenant_id: str,
    conversation_id: str,
    *,
    agent: str,
    request: Any,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    """Map a ``TaskTransitionRequest`` (or compatible AgentTurnResult fields) to ledger writes."""
    from conversation_control_plane.contract import TaskTransitionRequest

    if isinstance(request, TaskTransitionRequest):
        apply_transition(
            db,
            tenant_id,
            conversation_id,
            agent=agent,
            transition=request.transition,
            phase=request.phase,
            awaiting=request.awaiting,
            pending_ref=request.pending_ref,
            kind=request.kind,
            payload=payload if payload is not None else request.payload_patch,
            task_id=request.task_id,
            command_id=request.command_id,
            outcome_reason=request.outcome_reason,
            expected_version=request.expected_version,
        )
        return
    # AgentTurnResult-shaped object (duck typing)
    apply_transition(
        db,
        tenant_id,
        conversation_id,
        agent=agent,
        transition=getattr(request, "transition", None),
        phase=getattr(request, "phase", None),
        awaiting=getattr(request, "awaiting", None),
        pending_ref=getattr(request, "pending_ref", None),
        kind=getattr(request, "kind", None),
        payload=payload if payload is not None else getattr(request, "payload_patch", None),
        task_id=getattr(request, "task_id", None),
        command_id=getattr(request, "command_id", None),
        outcome_reason=getattr(request, "outcome_reason", None),
        expected_version=getattr(request, "expected_version", None),
    )


# -----------------------------------------------------------------------------
# Turn claim — per-conversation turn serialization (T1, turn-integrity epic)
# -----------------------------------------------------------------------------
#
# Why: decide_turn's read-decide-write span runs on an UNLOCKED snapshot
# (get_control_state is a plain SELECT). Two turns for the same conversation
# running in parallel (double-send, two tabs, disconnect-retry while the
# shielded original still runs, worker replay racing a fresh user turn)
# interleave their ledger mutations. The claim serializes turns per
# conversation: exactly one holder at a time, TTL-bounded so a crashed
# holder can never lock a conversation forever.
#
# Design notes:
# - The claim lives at context._turn_claim and is written on its OWN
#   short-lived session (committed immediately) so it is visible across
#   uvicorn workers regardless of the request transaction's state. The
#   request transaction commits BEFORE the caller releases, so the next
#   holder always reads the finished turn's state.
# - Deliberately does NOT bump _control_revision: the claim is turn
#   scheduling metadata, not a control mutation — bumping would invalidate
#   in-flight decision envelopes.
# - Reject, don't queue: a busy claim surfaces a typed conflict to the
#   caller (409 / retryable job error). Queuing would re-run the duplicate
#   heavy turn — the disconnect-retry cost-amplification this closes.
# - Fail open on infrastructure errors: the claim is an integrity guard,
#   not a security gate; a DB blip degrades to pre-T1 behavior (unclaimed)
#   with a warning rather than blocking chat.

_TURN_CLAIM_KEY = "_turn_claim"


def _turn_claim_ttl_seconds(db: Session | None = None) -> float:
    return float(_staleness.resolve_global(db, "turn_claim_ttl_seconds"))


def _turn_claim_orphan_steal_seconds(db: Session | None = None) -> float:
    return float(_staleness.resolve_global(db, "turn_claim_orphan_steal_seconds"))


# Back-compat aliases for tests / imports that pin the historical defaults.
_TURN_CLAIM_TTL_SECONDS = int(_staleness.default("turn_claim_ttl_seconds"))
_TURN_CLAIM_ORPHAN_STEAL_SECONDS = int(_staleness.default("turn_claim_orphan_steal_seconds"))


def _turn_claim_session_factory():
    # Lazy import: app.orm.base pulls settings; keep ledger importable in
    # lightweight test contexts that never touch the claim helpers.
    from app.orm.base import get_sync_session_factory
    return get_sync_session_factory()


def read_turn_claim(
    tenant_id: str,
    conversation_id: str,
    *,
    session_factory=None,
) -> dict[str, Any] | None:
    """Return the live ``_turn_claim`` payload, or None when absent."""
    if not conversation_id or not tenant_id:
        return None
    factory = session_factory or _turn_claim_session_factory()
    session = factory()
    try:
        row = session.execute(
            text(
                """
                SELECT context->:claim_key AS claim
                  FROM conversations
                 WHERE conversation_id = :cid AND tenant_id = :tid
                """
            ),
            {
                "claim_key": _TURN_CLAIM_KEY,
                "cid": conversation_id,
                "tid": tenant_id,
            },
        ).first()
        if row is None:
            return None
        claim = row[0]
        return claim if isinstance(claim, dict) else None
    except Exception:
        import logging
        logging.getLogger(__name__).debug(
            "read_turn_claim failed: conversation=%s",
            conversation_id, exc_info=True,
        )
        return None
    finally:
        session.close()


def turn_claim_retry_after_seconds(
    tenant_id: str,
    conversation_id: str,
    *,
    orphan_steal_seconds: float | None = None,
    ttl_seconds: float | None = None,
    session_factory=None,
) -> int | None:
    orphan_steal_seconds = (
        float(orphan_steal_seconds)
        if orphan_steal_seconds is not None
        else _turn_claim_orphan_steal_seconds(None)
    )
    ttl_seconds = (
        float(ttl_seconds)
        if ttl_seconds is not None
        else _turn_claim_ttl_seconds(None)
    )
    """Seconds until ``claim_turn`` may steal an orphan/stale claim."""
    claim = read_turn_claim(
        tenant_id, conversation_id, session_factory=session_factory,
    )
    if not claim:
        return None
    from datetime import datetime, timezone

    def _parse_ts(raw: Any) -> datetime | None:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        try:
            text_val = str(raw).strip()
            if not text_val:
                return None
            if text_val.endswith("Z"):
                text_val = text_val[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text_val)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

    now = datetime.now(timezone.utc)
    claimed_at = _parse_ts(claim.get("claimed_at"))
    renewed_at = _parse_ts(claim.get("renewed_at")) or claimed_at
    steal_candidates: list[float] = []
    if renewed_at is not None:
        steal_candidates.append(
            orphan_steal_seconds - (now - renewed_at).total_seconds(),
        )
    if claimed_at is not None:
        steal_candidates.append(
            ttl_seconds - (now - claimed_at).total_seconds(),
        )
    if not steal_candidates:
        return None
    return max(0, int(min(steal_candidates)) + 1)


def turn_claim_busy_details(
    tenant_id: str,
    conversation_id: str,
    *,
    session_factory=None,
) -> dict[str, Any]:
    """Structured payload for ``ConversationTurnInFlightAppError``."""
    details: dict[str, Any] = {"conversation_id": conversation_id}
    retry = turn_claim_retry_after_seconds(
        tenant_id, conversation_id, session_factory=session_factory,
    )
    if retry is not None:
        details["retry_after_seconds"] = retry
    return details


def claim_turn(
    tenant_id: str,
    conversation_id: str,
    *,
    turn_id: str,
    ttl_seconds: float | None = None,
    orphan_steal_seconds: float | None = None,
    session_factory=None,
    fail_open_on_error: bool = False,
) -> Literal["claimed", "busy", "no_row", "unavailable"]:
    """Atomically claim the turn slot for a conversation.

    Returns:
      "claimed"     — this turn now owns the conversation; caller MUST
                      release_turn() in a finally.
      "busy"        — another turn holds a live claim; caller should surface
                      a typed conflict (never proceed).
      "no_row"      — no conversations row exists (anonymous/threadless
                      turn); nothing to serialize against — proceed unclaimed.
      "unavailable" — only when ``fail_open_on_error=True`` and infrastructure
                      failed. **Default is fail-closed** (raises
                      ``TurnClaimInfrastructureError``) so hosts never run the
                      turn unclaimed under DB errors.

    Hosts that receive "unavailable" or the raised error must **not** execute
    the turn as if claimed — that is double-run risk, the failure mode this API
    exists to prevent.
    """
    ttl_seconds = (
        float(ttl_seconds)
        if ttl_seconds is not None
        else _turn_claim_ttl_seconds(None)
    )
    orphan_steal_seconds = (
        float(orphan_steal_seconds)
        if orphan_steal_seconds is not None
        else _turn_claim_orphan_steal_seconds(None)
    )
    if not conversation_id or not tenant_id:
        return "no_row"
    factory = session_factory or _turn_claim_session_factory()
    session = None
    try:
        session = factory()
        result = session.execute(
            text(
                """
                UPDATE conversations
                   SET context = jsonb_set(
                           COALESCE(context, '{}'::jsonb),
                           ARRAY[:claim_key]::text[],
                           jsonb_build_object(
                               'turn_id', CAST(:turn_id AS text),
                               'claimed_at', now(),
                               'renewed_at', now()
                           ),
                           true
                       ),
                       updated_at = now()
                 WHERE conversation_id = :cid AND tenant_id = :tid
                   AND (
                        context->:claim_key IS NULL
                        OR (context->:claim_key->>'claimed_at') IS NULL
                        OR (context->:claim_key->>'claimed_at')::timestamptz
                             < now() - make_interval(secs => :ttl)
                        OR COALESCE(
                               (context->:claim_key->>'renewed_at')::timestamptz,
                               (context->:claim_key->>'claimed_at')::timestamptz
                           ) < now() - make_interval(secs => :orphan_ttl)
                   )
                """
            ),
            {
                "claim_key": _TURN_CLAIM_KEY,
                "turn_id": turn_id,
                "cid": conversation_id,
                "tid": tenant_id,
                "ttl": float(ttl_seconds),
                "orphan_ttl": float(orphan_steal_seconds),
            },
        )
        if result.rowcount == 1:
            session.commit()
            return "claimed"
        session.rollback()
        row = session.execute(
            text(
                """
                SELECT 1 FROM conversations
                 WHERE conversation_id = :cid AND tenant_id = :tid
                """
            ),
            {"cid": conversation_id, "tid": tenant_id},
        ).first()
        if row is None:
            return "no_row"
        _emit(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            event="turn_claim_conflict",
            details={
                "turn_id": turn_id,
                "orphan_steal_seconds": orphan_steal_seconds,
            },
        )
        session.commit()
        return "busy"
    except Exception as exc:
        import logging

        logging.getLogger(__name__).error(
            "claim_turn failed (fail-closed default): conversation=%s",
            conversation_id,
            exc_info=True,
        )
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        if fail_open_on_error:
            logging.getLogger(__name__).warning(
                "claim_turn fail_open_on_error=True → unavailable: conversation=%s",
                conversation_id,
            )
            return "unavailable"
        from conversation_control_plane.failure_modes import (
            TurnClaimInfrastructureError,
        )

        raise TurnClaimInfrastructureError(
            "turn claim infrastructure unavailable",
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            cause=exc,
        ) from exc
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def mark_turn_completed(
    db: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    turn_id: str,
) -> None:
    """T8 (turn-integrity epic): record the last COMPLETED turn on the
    conversation, written on the REQUEST session immediately before the
    turn's final commit — so the marker is durable exactly when the turn's
    writes are. A ledger row whose ``updated_at`` (or control mutations)
    postdate ``_last_completed_turn.completed_at`` ran AHEAD of a completed
    turn (crash/disconnect before the client saw the reply) — the detection
    affordance A3 needs, and the timestamp source for the session-staleness
    re-orientation gate. No ``_control_revision`` bump: turn bookkeeping, not
    a control mutation. Best-effort: failures log and never break the turn."""
    if not conversation_id or not tenant_id or not turn_id:
        return
    try:
        db.execute(
            text(
                """
                UPDATE conversations
                   SET context = jsonb_set(
                           COALESCE(context, '{}'::jsonb),
                           ARRAY['_last_completed_turn']::text[],
                           jsonb_build_object(
                               'turn_id', CAST(:turn_id AS text),
                               'completed_at', now()
                           ),
                           true
                       )
                 WHERE conversation_id = :cid AND tenant_id = :tid
                """
            ),
            {"turn_id": turn_id, "cid": conversation_id, "tid": tenant_id},
        )
    except Exception:  # noqa: BLE001 — bookkeeping must not break the turn
        import logging
        logging.getLogger(__name__).warning(
            "mark_turn_completed failed: conversation=%s", conversation_id,
            exc_info=True,
        )


def commit_conversation_session_boundary(db: Session) -> None:
    """Commit control-plane writes before long LLM awaits.

    SSE/sync heartbeat renewals call ``renew_turn_claim`` on a separate
    short-lived connection. An uncommitted transaction that has touched
    ``conversations`` row-locks the row and blocks that renewal forever
    (conv_7a953788 worker, conv_66a6cced SSE). Call after decide_turn and
    other ledger write bursts that precede slow work — same contract as the
    async-handoff commit in ``_persist_async_handoff_context``.
    """
    try:
        db.commit()
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "commit_conversation_session_boundary failed", exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
        raise


def renew_turn_claim(
    tenant_id: str,
    conversation_id: str,
    *,
    turn_id: str,
    session_factory=None,
    db: Session | None = None,
) -> bool:
    """Refresh renewed_at for the live holder (SSE / sync heartbeat paths).

    claimed_at is the hard TTL anchor (set once at claim); renewed_at is
    the orphan-steal signal (stale when the holder stops heartbeating).

    When ``db`` is supplied, the UPDATE runs on that request/worker session
    instead of opening a separate connection. The workflow_builder_turn
    handler must pass its lease-time session when the handler holds an open
    transaction on ``conversations``. SSE/sync /chat instead commit session
    boundaries (``commit_conversation_session_boundary``) so this path can
    safely use a separate connection (observed conv_7a953788, 2026-07-04;
    conv_66a6cced, 2026-07-06).

    Returns True when the claim was renewed. False when there is no
    matching claim (already released / taken over) — callers ignore.
    """
    if not conversation_id or not tenant_id or not turn_id:
        return False

    _renew_sql = text(
        """
        UPDATE conversations
           SET context = jsonb_set(
                   context,
                   ARRAY[:claim_key]::text[],
                   COALESCE(context->:claim_key, '{}'::jsonb)
                       || jsonb_build_object('renewed_at', now()),
                   true
               ),
               updated_at = now()
         WHERE conversation_id = :cid AND tenant_id = :tid
           AND context->:claim_key->>'turn_id' = :turn_id
        """
    )
    _renew_params = {
        "claim_key": _TURN_CLAIM_KEY,
        "turn_id": turn_id,
        "cid": conversation_id,
        "tid": tenant_id,
    }

    if db is not None:
        try:
            result = db.execute(_renew_sql, _renew_params)
            return int(result.rowcount or 0) == 1
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "renew_turn_claim failed (non-fatal): conversation=%s",
                conversation_id, exc_info=True,
            )
            return False

    factory = session_factory or _turn_claim_session_factory()
    session = factory()
    try:
        result = session.execute(_renew_sql, _renew_params)
        renewed = int(result.rowcount or 0) == 1
        if renewed:
            session.commit()
        else:
            session.rollback()
        return renewed
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "renew_turn_claim failed (non-fatal): conversation=%s",
            conversation_id, exc_info=True,
        )
        try:
            session.rollback()
        except Exception:
            pass
        return False
    finally:
        session.close()


def release_turn(
    tenant_id: str,
    conversation_id: str,
    *,
    turn_id: str,
    session_factory=None,
) -> None:
    """Release a turn claim. Idempotent; only removes OUR claim (turn_id
    must match) so a TTL takeover's claim is never clobbered by the
    original holder's late finally. Failures are logged, never raised —
    the TTL is the backstop."""
    if not conversation_id or not tenant_id or not turn_id:
        return
    factory = session_factory or _turn_claim_session_factory()
    session = factory()
    try:
        session.execute(
            text(
                """
                UPDATE conversations
                   SET context = context - :claim_key,
                       updated_at = now()
                 WHERE conversation_id = :cid AND tenant_id = :tid
                   AND context->:claim_key->>'turn_id' = :turn_id
                """
            ),
            {
                "claim_key": _TURN_CLAIM_KEY,
                "turn_id": turn_id,
                "cid": conversation_id,
                "tid": tenant_id,
            },
        )
        session.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "release_turn failed (TTL will reap): conversation=%s",
            conversation_id, exc_info=True,
        )
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        session.close()


# -----------------------------------------------------------------------------
# Internal helpers (will be cleaned up as the shim is retired)
# -----------------------------------------------------------------------------

def _emit(
    db: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    event: str,
    details: dict[str, Any],
    account_id: Optional[str] = None,
) -> None:
    log_platform_event(
        db,
        event,
        "info",
        f"Conversation control: {event}",
        tenant_id=tenant_id,
        account_id=account_id,
        details={"conversation_id": conversation_id, **details},
    )
