"""Transactional outbox for conversation control journal events (Model A).

The journal table *is* the outbox: each accepted lifecycle event starts as
``export_status=pending``. Exporters claim batches, publish (platform_events /
CloudEvents adapter), then mark ``exported``. Dual-write to an external bus is
not required for correctness — the journal remains historical authority.

Not the ledger of record for routing (that is the L1 projection).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

EXPORT_PENDING = "pending"
EXPORT_EXPORTED = "exported"
EXPORT_SKIPPED = "skipped"


def to_cloudevent(row: dict[str, Any], *, source: str = "bot0/conversation-control") -> dict[str, Any]:
    """Map a journal row to a CloudEvents-shaped dict (export packaging only)."""
    payload = row.get("payload_json") or row.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:  # noqa: BLE001
            payload = {"raw": payload}
    event_type = str(row.get("event_type") or "control.unknown")
    return {
        "specversion": "1.0",
        "id": str(row.get("event_id") or ""),
        "source": source,
        "type": f"com.bot0.conversation_control.{event_type}",
        "time": str(row.get("created_at") or ""),
        "subject": str(row.get("conversation_id") or ""),
        "datacontenttype": "application/json",
        "data": {
            "tenant_id": row.get("tenant_id"),
            "conversation_id": row.get("conversation_id"),
            "seq": row.get("seq"),
            "command_id": row.get("command_id"),
            "event_type": event_type,
            "task_id": row.get("task_id"),
            "agent": row.get("agent"),
            "kind": row.get("kind"),
            "control_revision_after": row.get("control_revision_after"),
            "payload": payload if isinstance(payload, dict) else {},
        },
    }


def claim_export_batch(
    db: Session,
    *,
    limit: int = 50,
    tenant_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Claim pending journal rows for export (SKIP LOCKED).

    Marks claimed rows as in-flight by leaving them pending until
    :func:`mark_exported` — caller should process then mark. Concurrent
    claimers skip locked rows.
    """
    lim = max(1, min(int(limit), 500))
    params: dict[str, Any] = {"lim": lim}
    tenant_clause = ""
    if tenant_id:
        tenant_clause = "AND tenant_id = :tid"
        params["tid"] = tenant_id
    rows = db.execute(
        text(
            f"""
            SELECT event_id, tenant_id, conversation_id, seq, command_id,
                   event_type, task_id, agent, kind, control_revision_after,
                   payload_json, created_at, export_status
              FROM conversation_control_events
             WHERE export_status = :pending
               {tenant_clause}
             ORDER BY created_at ASC, seq ASC
             LIMIT :lim
             FOR UPDATE SKIP LOCKED
            """
        ),
        {**params, "pending": EXPORT_PENDING},
    ).mappings().all()
    return [dict(r) for r in rows]


def mark_exported(
    db: Session,
    event_ids: list[str],
    *,
    status: str = EXPORT_EXPORTED,
) -> int:
    """Mark claimed events as exported (or skipped). Returns rows updated."""
    ids = [str(e).strip() for e in (event_ids or []) if str(e).strip()]
    if not ids:
        return 0
    st = (status or EXPORT_EXPORTED).strip().lower()
    if st not in (EXPORT_EXPORTED, EXPORT_SKIPPED):
        st = EXPORT_EXPORTED
    result = db.execute(
        text(
            """
            UPDATE conversation_control_events
               SET export_status = :st,
                   exported_at = now()
             WHERE event_id = ANY(:ids)
               AND export_status = :pending
            """
        ),
        {"st": st, "ids": ids, "pending": EXPORT_PENDING},
    )
    return int(getattr(result, "rowcount", 0) or 0)


def export_batch_to_platform_events(
    db: Session,
    *,
    limit: int = 50,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Default sink: mirror journal rows as platform_events, then mark exported.

    Safe to call from a worker / cron. Failures leave rows pending for retry.
    """
    try:
        from api.services.event_logger import log_platform_event
    except ImportError:  # public extract without monorepo host
        def log_platform_event(*_a, **_k):  # type: ignore[misc]
            return None

    claimed = claim_export_batch(db, limit=limit, tenant_id=tenant_id)
    if not claimed:
        return {"claimed": 0, "exported": 0, "failed": 0}

    exported_ids: list[str] = []
    failed = 0
    for row in claimed:
        try:
            ce = to_cloudevent(row)
            log_platform_event(
                db,
                "conversation_control.export",
                "info",
                f"Control journal export: {row.get('event_type')}",
                tenant_id=str(row.get("tenant_id") or ""),
                details={
                    "conversation_id": row.get("conversation_id"),
                    "event_id": row.get("event_id"),
                    "command_id": row.get("command_id"),
                    "task_id": row.get("task_id"),
                    "seq": row.get("seq"),
                    "cloudevent_type": ce.get("type"),
                    "payload": ce.get("data"),
                },
            )
            exported_ids.append(str(row.get("event_id")))
        except Exception:  # noqa: BLE001
            failed += 1
            logger.warning(
                "control outbox export failed event_id=%s",
                row.get("event_id"),
                exc_info=True,
            )
    n = mark_exported(db, exported_ids)
    return {"claimed": len(claimed), "exported": n, "failed": failed}


__all__ = [
    "EXPORT_EXPORTED",
    "EXPORT_PENDING",
    "EXPORT_SKIPPED",
    "claim_export_batch",
    "export_batch_to_platform_events",
    "mark_exported",
    "to_cloudevent",
]
