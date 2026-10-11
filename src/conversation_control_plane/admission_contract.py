"""Admission before execution — one decision, then the ledger (B-240).

conv_b4bc0ea1 (2026-10-09): a pasted work system was answered by the
workflow builder, and the ledger ended the turn holding a SUSPENDED
Transformation Advisor task that nobody had asked for and nothing executed.
The journal showed why:

    14:18:16  task_began  transformation_advisor  (decide default branch)
    14:18:23  router      workflow_builder        (the turn's real owner)
    14:18:32  advisor suspended — no journal row, no resumption condition

`decide_turn`'s default branch opened a ledger task from the router's PROPOSAL
("P2a shadow default / classification proxy"). Everything downstream of decide
may still hand the turn to another leaf, so a proposal that never executed was
left as admitted work, and the drafting open that displaced it wrote nothing
to the journal.

The law (AGENTS §TARGET, epic #1e "Admission before execution"):

1. A router output is a PROPOSAL. Decide records it here; it opens no task.
2. Work is ADMITTED where its owner actually executes: the dispatch entry of
   the heavy agent. Only the proposed agent is admitted, and only when no task
   is active — this is the same admission the default branch made, moved to
   the point where it is true.
3. A proposal that never executed is DISPOSED as ``not_admitted`` on the
   routing record — never left behind in the ledger.
4. The routing record carries provenance: what was proposed, what was
   admitted, who executes, who actually answered, and the outcome. When the
   proposal and the responder disagree it is logged as a DISAGREEMENT, not
   resolved by a second instruction.

No wordlists, no precedence table: the only inputs are the enum the router
emitted, the agent whose dispatch entry is running, and the ledger.
"""
from __future__ import annotations

import contextvars
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: The heavy agents whose work is a ledger task. Same set the decide default
#: branch admitted for before B-240; admission moved, the set did not.
ADMITTED_AGENTS: frozenset[str] = frozenset({
    "workflow_builder",
    "transformation_advisor",
    "transformation_recommender",
    "workflow_editor",
})

#: What a proposal can end as on the turn that made it.
DISPOSITIONS: frozenset[str] = frozenset({
    "admitted",        # the proposed agent executed and its task was opened
    "already_active",  # the proposed agent executed under a task already open
    "not_admitted",    # the turn was answered by something else
    "blocked_by_active",  # another task became active before dispatch
})


_record: contextvars.ContextVar[Optional[dict[str, Any]]] = contextvars.ContextVar(
    "bot0_turn_admission", default=None,
)
#: The message this turn is answering, as a hash. The worker re-runs the same
#: message after the main process admitted its task, so a task opened by this
#: message must not be read as an older task the message displaces.
_source: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "bot0_turn_source_message", default=None,
)


def _canonical(agent: Any) -> str:
    from conversation_control_plane.contract import canonical_agent

    a = str(agent or "").strip()
    return canonical_agent(a) or a


def reset_turn_admission() -> None:
    """Call at turn start (``turn_telemetry.start_turn_trace``)."""
    _record.set(None)
    _source.set(None)


def set_turn_source(message: Any) -> None:
    """Name the message this turn answers (before decide runs)."""
    import hashlib

    text = str(message or "").strip()
    _source.set(f"sha256:{hashlib.sha256(text.encode()).hexdigest()}" if text else None)


def turn_source_hash() -> Optional[str]:
    return _source.get()


def opened_by_this_message(task: Any) -> bool:
    """True when ``task`` was opened by the message this turn answers."""
    src = _source.get()
    return bool(src) and isinstance(task, dict) and task.get("source_message_hash") == src


def current_admission() -> Optional[dict[str, Any]]:
    rec = _record.get()
    return dict(rec) if isinstance(rec, dict) else None


def propose(
    *,
    agent: str,
    router_intent: Optional[str],
    router_layer: Optional[str],
    kind: Optional[str],
) -> None:
    """Decide's default branch: record the proposal. Opens nothing."""
    proposed = _canonical(agent)
    if proposed not in ADMITTED_AGENTS:
        return
    _record.set({
        "proposed_agent": proposed,
        "proposed_by": "decide_default",
        "router_intent": str(router_intent or "") or None,
        "router_layer": str(router_layer or "") or None,
        "kind": kind,
        "admitted_agent": None,
        "disposition": None,
    })


def admit_at_dispatch(
    db: Any,
    tenant_id: str,
    conversation_id: Optional[str],
    *,
    executing_agent: str,
) -> Optional[str]:
    """The heavy agent's dispatch entry: admit the proposal if it is this agent.

    Returns the disposition written, or None when there was no proposal (the
    turn's task, if any, was opened by whoever owned it — a resume, a
    continue, a worker re-entry).
    """
    rec = _record.get()
    if not isinstance(rec, dict):
        return None
    if rec.get("disposition"):  # already decided at an earlier entry this turn
        return str(rec["disposition"])
    executing = _canonical(executing_agent)
    if executing != rec.get("proposed_agent") or not conversation_id:
        return None
    from conversation_control_plane.ledger import begin_task, get_control_state

    active = (get_control_state(db, tenant_id, conversation_id) or {}).get("active_task")
    if isinstance(active, dict) and active:
        disposition = (
            "already_active" if _canonical(active.get("agent")) == executing
            else "blocked_by_active"
        )
    else:
        begin_task(
            db, tenant_id, conversation_id, agent=executing,
            phase="active", awaiting="in_progress",
            kind=rec.get("kind"),
            pending_ref=f"admitted:{executing}:{conversation_id}",
        )
        disposition = "admitted"
        rec["admitted_agent"] = executing
    rec["disposition"] = disposition
    _record.set(rec)
    return disposition


def stamp_provenance(routing: dict, *, actual_responder: Optional[str]) -> None:
    """Write the admission record onto the routing record. Logs disagreement."""
    if not isinstance(routing, dict):
        return
    rec = _record.get()
    if not isinstance(rec, dict):
        return
    actual = _canonical(actual_responder) or None
    disposition = rec.get("disposition") or "not_admitted"
    routing["admission"] = {
        "proposed_responder": rec.get("proposed_agent"),
        "detected_intent": rec.get("router_intent"),
        "admitted_work": rec.get("admitted_agent"),
        "execution_owner": rec.get("admitted_agent") or (
            rec.get("proposed_agent") if disposition == "already_active" else None
        ),
        "actual_responder": actual,
        "candidate_disposition": disposition,
        "outcome": "agreed" if actual == rec.get("proposed_agent") else "disagreed",
    }
    if actual != rec.get("proposed_agent"):
        logger.info(
            "admission_disagreement proposed=%s actual=%s disposition=%s layer=%s",
            rec.get("proposed_agent"), actual, disposition, rec.get("router_layer"),
        )


__all__ = [
    "ADMITTED_AGENTS",
    "DISPOSITIONS",
    "admit_at_dispatch",
    "current_admission",
    "opened_by_this_message",
    "propose",
    "reset_turn_admission",
    "set_turn_source",
    "stamp_provenance",
    "turn_source_hash",
]
