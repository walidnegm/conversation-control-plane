"""Conversation control event journal (Model A — historical authority).

Projection (conversations.context) = routing authority.
Journal (conversation_control_events) = history / audit / replay authority.

Successful lifecycle commands **must** insert a journal row in the **same**
transaction as the projection update (fail-closed). Platform telemetry / outbox
export may mirror journal events downstream; they are not the ledger of record.

Sequence: prefer ``control_revision_after`` as the event sequence when provided
(avoids SELECT MAX races under the conversation row lock). Fall back to MAX+1
only when revision is unknown.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

JOURNAL_SCHEMA_VERSION = 1


def new_command_id() -> str:
    return f"cmd_{uuid.uuid4().hex[:16]}"


def new_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:16]}"


def _canonical_event_bytes(
    *,
    tenant_id: str,
    conversation_id: str,
    seq: int,
    command_id: str,
    event_type: str,
    task_id: Optional[str],
    agent: Optional[str],
    kind: Optional[str],
    control_revision_after: Optional[int],
    body: dict[str, Any],
    prev_event_hash: Optional[str],
) -> bytes:
    """Deterministic serialization for L3 hash-chain (no wall-clock)."""
    material = {
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "seq": seq,
        "command_id": command_id,
        "event_type": event_type,
        "task_id": task_id,
        "agent": agent,
        "kind": kind,
        "control_revision_after": control_revision_after,
        "payload": body,
        "prev_event_hash": prev_event_hash or "",
    }
    return json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )


def compute_event_hash(
    *,
    tenant_id: str,
    conversation_id: str,
    seq: int,
    command_id: str,
    event_type: str,
    task_id: Optional[str],
    agent: Optional[str],
    kind: Optional[str],
    control_revision_after: Optional[int],
    body: dict[str, Any],
    prev_event_hash: Optional[str],
) -> str:
    digest = hashlib.sha256(
        _canonical_event_bytes(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            seq=seq,
            command_id=command_id,
            event_type=event_type,
            task_id=task_id,
            agent=agent,
            kind=kind,
            control_revision_after=control_revision_after,
            body=body,
            prev_event_hash=prev_event_hash,
        )
    ).hexdigest()
    return f"sha256:{digest}"


def _latest_event_hash(
    db: Session,
    *,
    tenant_id: str,
    conversation_id: str,
) -> Optional[str]:
    row = db.execute(
        text(
            """
            SELECT payload_json->>'event_hash' AS h
              FROM conversation_control_events
             WHERE tenant_id = :tid AND conversation_id = :cid
             ORDER BY seq DESC
             LIMIT 1
            """
        ),
        {"tid": tenant_id, "cid": conversation_id},
    ).fetchone()
    if not row or not row[0]:
        return None
    return str(row[0])


def append_control_event(
    db: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    event_type: str,
    command_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent: Optional[str] = None,
    kind: Optional[str] = None,
    control_revision_after: Optional[int] = None,
    control_revision_before: Optional[int] = None,
    causation_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    source_message_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    schema_version: int = JOURNAL_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Insert one immutable journal row; returns the inserted row summary.

    Fail-closed: raises on insert failure. Callers must not swallow this inside
    a lifecycle command transaction — abort the command so projection + journal
    stay atomic.

    Sequence is per (tenant_id, conversation_id). Prefer
    ``control_revision_after`` as seq (version-as-sequence); else MAX(seq)+1.

    L3: each row carries ``event_hash`` + ``prev_event_hash`` (hash-chain) inside
    payload_json for optional notary / tamper-evidence without a second store.
    """
    cmd = (command_id or new_command_id()).strip()
    if control_revision_after is not None and int(control_revision_after) > 0:
        seq = int(control_revision_after)
    else:
        row = db.execute(
            text(
                """
                SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq
                  FROM conversation_control_events
                 WHERE tenant_id = :tid AND conversation_id = :cid
                """
            ),
            {"tid": tenant_id, "cid": conversation_id},
        ).fetchone()
        seq = int(row[0] if row else 1)

    event_id = f"cev_{uuid.uuid4().hex[:16]}"
    body = dict(payload or {})
    # Causal / version envelope (compact — no IR/graph blobs).
    if control_revision_before is not None:
        body.setdefault("previous_version", int(control_revision_before))
    if control_revision_after is not None:
        body.setdefault("new_version", int(control_revision_after))
    body.setdefault("schema_version", int(schema_version))
    if source_message_id:
        body.setdefault("source_message_id", str(source_message_id))

    prev_hash = _latest_event_hash(
        db, tenant_id=tenant_id, conversation_id=conversation_id,
    )
    # Hash material excludes event_hash itself (computed below).
    body_for_hash = {k: v for k, v in body.items() if k not in ("event_hash", "prev_event_hash")}
    event_hash = compute_event_hash(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        seq=seq,
        command_id=cmd,
        event_type=event_type,
        task_id=task_id,
        agent=agent,
        kind=kind,
        control_revision_after=control_revision_after,
        body=body_for_hash,
        prev_event_hash=prev_hash,
    )
    body["prev_event_hash"] = prev_hash
    body["event_hash"] = event_hash

    db.execute(
        text(
            """
            INSERT INTO conversation_control_events (
                event_id, tenant_id, conversation_id, seq, command_id,
                event_type, task_id, agent, kind, control_revision_after,
                causation_id, correlation_id, payload_json
            ) VALUES (
                :event_id, :tid, :cid, :seq, :command_id,
                :event_type, :task_id, :agent, :kind, :rev,
                :causation_id, :correlation_id, CAST(:payload AS jsonb)
            )
            """
        ),
        {
            "event_id": event_id,
            "tid": tenant_id,
            "cid": conversation_id,
            "seq": seq,
            "command_id": cmd,
            "event_type": event_type,
            "task_id": task_id,
            "agent": agent,
            "kind": kind,
            "rev": control_revision_after,
            "causation_id": causation_id,
            "correlation_id": correlation_id or source_message_id,
            "payload": json.dumps(body),
        },
    )
    return {
        "event_id": event_id,
        "seq": seq,
        "command_id": cmd,
        "event_type": event_type,
        "task_id": task_id,
        "control_revision_after": control_revision_after,
        "schema_version": int(schema_version),
        "event_hash": event_hash,
        "prev_event_hash": prev_hash,
    }


def verify_hash_chain(
    events: list[dict[str, Any]],
    *,
    tenant_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Verify L3 hash-chain over an ordered event list. Returns ok + breaks."""
    prev: Optional[str] = None
    breaks: list[str] = []
    for ev in events:
        payload = ev.get("payload_json") or ev.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:  # noqa: BLE001
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        stored = payload.get("event_hash")
        stored_prev = payload.get("prev_event_hash")
        if stored_prev != prev and not (stored_prev is None and prev is None):
            # allow null/None mismatch for first event only
            if not (prev is None and not stored_prev):
                breaks.append(f"seq={ev.get('seq')}:prev_hash_mismatch")
        body_for_hash = {
            k: v for k, v in payload.items() if k not in ("event_hash", "prev_event_hash")
        }
        expected = compute_event_hash(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            seq=int(ev.get("seq") or 0),
            command_id=str(ev.get("command_id") or ""),
            event_type=str(ev.get("event_type") or ""),
            task_id=ev.get("task_id"),
            agent=ev.get("agent"),
            kind=ev.get("kind"),
            control_revision_after=ev.get("control_revision_after"),
            body=body_for_hash,
            prev_event_hash=prev,
        )
        if stored and stored != expected:
            breaks.append(f"seq={ev.get('seq')}:hash_mismatch")
        prev = stored or expected
    return {"ok": len(breaks) == 0, "breaks": breaks, "tip_hash": prev}


def merkle_root(event_hashes: list[str]) -> Optional[str]:
    """Optional L3 notary material — Merkle root of event hashes (SHA-256)."""
    if not event_hashes:
        return None
    layer = [
        hashlib.sha256(h.encode("utf-8")).digest()
        for h in event_hashes
        if h
    ]
    if not layer:
        return None
    while len(layer) > 1:
        nxt: list[bytes] = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else left
            nxt.append(hashlib.sha256(left + right).digest())
        layer = nxt
    return f"sha256:{layer[0].hex()}"


def find_event_by_command_id(
    db: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    command_id: str,
) -> Optional[dict[str, Any]]:
    """Idempotency lookup: prior accepted command for this conversation."""
    if not command_id:
        return None
    row = db.execute(
        text(
            """
            SELECT event_id, seq, command_id, event_type, task_id, agent, kind,
                   control_revision_after, payload_json, created_at
              FROM conversation_control_events
             WHERE tenant_id = :tid AND conversation_id = :cid
               AND command_id = :cmd
             ORDER BY seq ASC
             LIMIT 1
            """
        ),
        {"tid": tenant_id, "cid": conversation_id, "cmd": command_id},
    ).mappings().first()
    return dict(row) if row else None


def list_control_events(
    db: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    after_seq: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT event_id, seq, command_id, event_type, task_id, agent, kind,
                   control_revision_after, payload_json, created_at, export_status
              FROM conversation_control_events
             WHERE tenant_id = :tid AND conversation_id = :cid
               AND seq > :after
             ORDER BY seq ASC
             LIMIT :lim
            """
        ),
        {
            "tid": tenant_id,
            "cid": conversation_id,
            "after": after_seq,
            "lim": max(1, min(int(limit), 1000)),
        },
    ).mappings().all()
    return [dict(r) for r in rows]


def rebuild_projection_hints(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Lightweight audit reducer — last-write-wins hints from journal events.

    Not the hot-path routing authority (projection remains source of truth for
    live turns). Used for recovery/debug and replay-equivalence smoke tests.
    """
    active: Optional[dict[str, Any]] = None
    last_switch: Optional[dict[str, Any]] = None
    for ev in events:
        et = str(ev.get("event_type") or "")
        payload = ev.get("payload_json") or ev.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:  # noqa: BLE001
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if et == "task_began":
            active = {
                "task_id": ev.get("task_id"),
                "agent": ev.get("agent"),
                "kind": ev.get("kind"),
                "phase": payload.get("phase"),
                "awaiting": payload.get("awaiting"),
                "pending_ref": payload.get("pending_ref"),
            }
        elif et in ("task_completed", "task_abandoned", "task_failed", "task_superseded", "task_expired"):
            active = None
        elif et == "switch_accepted":
            last_switch = {
                "to_agent": payload.get("to_agent"),
                "from_agent": payload.get("from_agent"),
            }
            begun = payload.get("pending") if isinstance(payload.get("pending"), dict) else {}
            if begun.get("to_agent") and not active:
                active = {"agent": begun.get("to_agent")}
        elif et == "switch_declined":
            last_switch = {
                "to_agent": payload.get("to_agent"),
                "resolution": "declined",
            }
    return {
        "active_task": active,
        "last_switch": last_switch,
        "event_count": len(events),
    }


__all__ = [
    "JOURNAL_SCHEMA_VERSION",
    "append_control_event",
    "compute_event_hash",
    "find_event_by_command_id",
    "list_control_events",
    "merkle_root",
    "new_command_id",
    "new_task_id",
    "rebuild_projection_hints",
    "verify_hash_chain",
]
