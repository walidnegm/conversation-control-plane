"""Hot-potato (ping-pong) handoff detection for the control plane.

Specialist A → B → A loops burn tokens and confuse users. This module records
recent agent transitions and blocks immediate bounce-backs before ``begin_task``.
"""
from __future__ import annotations

from typing import Any, Optional

from api.services.conversation_control.contract import canonical_agent

_HANDOFF_TRACE_KEY = "_handoff_trace"
_DETOUR_TRACE_KEY = "_detour_delivery_trace"
_MAX_TRACE_LEN = 12
_MAX_DETOUR_TRACE_LEN = 16
_DEFAULT_DETOUR_REPEAT_BUDGET = 2


def read_handoff_trace(context: dict | None) -> list[dict[str, str]]:
    raw = (context or {}).get(_HANDOFF_TRACE_KEY)
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fr = canonical_agent(item.get("from")) or str(item.get("from") or "").strip()
        to = canonical_agent(item.get("to")) or str(item.get("to") or "").strip()
        if fr and to and fr != to:
            out.append({"from": fr, "to": to})
    return out[-_MAX_TRACE_LEN:]


def would_ping_pong(
    trace: list[dict[str, str]],
    *,
    from_agent: str,
    to_agent: str,
) -> bool:
    """True when ``from_agent → to_agent`` would immediately reverse the last hop."""
    if would_handoff_cycle(trace, from_agent=from_agent, to_agent=to_agent):
        return True
    fr = canonical_agent(from_agent) or (from_agent or "").strip()
    to = canonical_agent(to_agent) or (to_agent or "").strip()
    if not fr or not to or fr == to or not trace:
        return False
    window = trace[-4:]
    pair_hits = sum(
        1 for t in window
        if t.get("from") == fr and t.get("to") == to
    )
    return pair_hits >= 1 and len(window) >= 2


def would_handoff_cycle(
    trace: list[dict[str, str]],
    *,
    from_agent: str,
    to_agent: str,
) -> bool:
    """True when the proposed hop closes a 3+ agent cycle (A→B→C→A)."""
    fr = canonical_agent(from_agent) or (from_agent or "").strip()
    to = canonical_agent(to_agent) or (to_agent or "").strip()
    if not fr or not to or fr == to or not trace:
        return False
    last = trace[-1]
    if last.get("from") == to and last.get("to") == fr:
        return True
    if len(trace) < 2:
        return False
    path = [t.get("from") or "" for t in trace[-5:]] + [fr, to]
    compact: list[str] = []
    for node in path:
        if not node:
            continue
        if compact and compact[-1] == node:
            continue
        compact.append(node)
    if len(compact) < 4:
        return False
    return compact[-1] == compact[0] and len(set(compact)) >= 3


def push_handoff_trace(
    trace: list[dict[str, str]],
    *,
    from_agent: str,
    to_agent: str,
) -> list[dict[str, str]]:
    """Return an updated in-memory trace (caller persists when appropriate)."""
    fr = canonical_agent(from_agent) or (from_agent or "").strip()
    to = canonical_agent(to_agent) or (to_agent or "").strip()
    if not fr or not to or fr == to:
        return list(trace)
    updated = list(trace) + [{"from": fr, "to": to}]
    return updated[-_MAX_TRACE_LEN:]


def persist_handoff_trace(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    trace: list[dict[str, str]],
) -> None:
    """Write ``_handoff_trace`` on the conversation row (bookkeeping, not a control key)."""
    if not db or not tenant_id or not conversation_id:
        return
    import json

    from sqlalchemy import text

    try:
        db.execute(
            text(
                """
                UPDATE conversations
                   SET context = jsonb_set(
                           COALESCE(context, '{}'::jsonb),
                           ARRAY[:trace_key]::text[],
                           CAST(:trace_json AS jsonb),
                           true
                       ),
                       updated_at = now()
                 WHERE conversation_id = :cid AND tenant_id = :tid
                """
            ),
            {
                "trace_key": _HANDOFF_TRACE_KEY,
                "trace_json": json.dumps(trace),
                "cid": conversation_id,
                "tid": tenant_id,
            },
        )
    except Exception:  # noqa: BLE001 — trace must not break routing
        import logging
        logging.getLogger(__name__).warning(
            "persist_handoff_trace failed: conversation=%s", conversation_id, exc_info=True,
        )


def append_handoff_trace(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    from_agent: str,
    to_agent: str,
    prior_trace: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Append one hop and persist. Returns the new trace."""
    trace = push_handoff_trace(prior_trace or [], from_agent=from_agent, to_agent=to_agent)
    persist_handoff_trace(
        db, tenant_id=tenant_id, conversation_id=conversation_id, trace=trace,
    )
    return trace


def read_detour_trace(context: dict | None) -> list[str]:
    raw = (context or {}).get(_DETOUR_TRACE_KEY)
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        label = str(item or "").strip().lower()
        if label:
            out.append(label)
    return out[-_MAX_DETOUR_TRACE_LEN:]


def detour_repeat_exceeded(
    trace: list[str],
    *,
    kind: str,
    budget: int = _DEFAULT_DETOUR_REPEAT_BUDGET,
) -> bool:
    """True when the same front-door detour kind fired too often in-window."""
    label = (kind or "").strip().lower()
    if not label or budget < 1:
        return False
    hits = sum(1 for k in trace if k == label)
    return hits >= budget


def push_detour_trace(trace: list[str], *, kind: str) -> list[str]:
    label = (kind or "").strip().lower()
    if not label:
        return list(trace)
    return (list(trace) + [label])[-_MAX_DETOUR_TRACE_LEN:]


def persist_detour_trace(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    trace: list[str],
) -> None:
    if not db or not tenant_id or not conversation_id:
        return
    import json

    from sqlalchemy import text

    try:
        db.execute(
            text(
                """
                UPDATE conversations
                   SET context = jsonb_set(
                           COALESCE(context, '{}'::jsonb),
                           ARRAY[:trace_key]::text[],
                           CAST(:trace_json AS jsonb),
                           true
                       ),
                       updated_at = now()
                 WHERE conversation_id = :cid AND tenant_id = :tid
                """
            ),
            {
                "trace_key": _DETOUR_TRACE_KEY,
                "trace_json": json.dumps(trace),
                "cid": conversation_id,
                "tid": tenant_id,
            },
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "persist_detour_trace failed: conversation=%s", conversation_id, exc_info=True,
        )


def record_detour_delivery(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    kind: str,
    prior_trace: list[str] | None = None,
    context: dict | None = None,
) -> list[str]:
    trace = push_detour_trace(
        prior_trace if prior_trace is not None else read_detour_trace(context),
        kind=kind,
    )
    persist_detour_trace(
        db, tenant_id=tenant_id, conversation_id=conversation_id, trace=trace,
    )
    return trace


__all__ = [
    "append_handoff_trace",
    "detour_repeat_exceeded",
    "persist_detour_trace",
    "persist_handoff_trace",
    "push_detour_trace",
    "push_handoff_trace",
    "read_detour_trace",
    "read_handoff_trace",
    "record_detour_delivery",
    "would_handoff_cycle",
    "would_ping_pong",
]