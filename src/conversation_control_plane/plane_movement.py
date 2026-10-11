"""Did this turn move the control plane?

Every bug in findings C2, C3, A2 and the value-metrics loop is one rule broken:
**a turn that answers the user must move the plane** — begin a task, advance it,
complete it, or explicitly declare that it is a read-only turn.

Break it one way and the next turn has nothing to continue, so it re-enters from
scratch and repeats itself (conv_c3aacaed: "already has value metrics", twice,
because the already-complete branch called no ledger API). Break it the other
way and a finished task stays armed, so resumption reads a stale position
(conv_c3aacaed again: `engagement_pack_plan` armed 11h, "Next: Simulation
project for to-be").

Every one of those was found by reading a transcript *after* a user hit it.
This module exists so the next one reports itself on the turn it happens.

Mechanism: the ledger marks movement; the output rail checks the mark. No extra
DB read, and no handler has to remember anything — a handler that writes through
the ledger is compliant by construction, and one that stamps the projection
directly is not, which is exactly the distinction findings C2/S9 measure.
"""
from __future__ import annotations

import contextvars
import logging
from typing import Any

logger = logging.getLogger(__name__)

_moved: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "bot0_plane_moved", default=None,
)
_read_only: contextvars.ContextVar[str] = contextvars.ContextVar(
    "bot0_plane_read_only", default="",
)
# Worker re-entry: chat() must not report unmoved before the handler
# writes the ledger (TC-L · conv_4ac10b7c).
_defer_report: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "bot0_plane_defer_report", default=False,
)


def reset_plane_movement() -> None:
    """Call at turn start."""
    _moved.set([])
    _read_only.set("")
    _defer_report.set(False)


def set_defer_plane_report(defer: bool) -> None:
    """Worker re-entry: report after the ledger mirror, not inside chat()."""
    _defer_report.set(bool(defer))


def should_defer_plane_report() -> bool:
    return bool(_defer_report.get())


def mark_plane_moved(op: str) -> None:
    """Called by the ledger writers. ``op`` is begin_task / complete_task / …"""
    cur = _moved.get()
    if cur is None:
        cur = []
        _moved.set(cur)
    cur.append(str(op or "?"))


def declare_read_only_turn(reason: str) -> None:
    """This turn legitimately answers without moving the plane.

    A glossary answer, an inventory listing, a status read. Declaring it is the
    point: it separates "nothing needed to move" from "we forgot", which today
    are indistinguishable and which is why the value-metrics loop survived four
    user attempts.
    """
    _read_only.set(str(reason or "unspecified"))


def plane_movements() -> list[str]:
    return list(_moved.get() or [])


def turn_moved_the_plane() -> bool:
    return bool(_moved.get())


# Dispatches that answer without moving the plane *because nothing needed to
# move*. Declared here rather than as a call in each handler: these are read
# surfaces scattered across bot0.py and the tool layer, and the module's promise
# is that no handler has to remember anything.
#
# This is a declaration, not a mute. Each entry states why it reads. In the
# first 16 days the instrument reported 1,441 turns and ~60% were these -- noise
# that buried ~220 real ones (set_value_metrics_finite 91, discovery_detour 87).
#
# NOT listed on purpose: inventory_name_resolve (129) and inventory_entity_resolve
# (17). They look like lookups, but pre_decide_owner_contract documents
# inventory_name_resolve as "pick project / input state while pick_state" -- a
# pick pins conversation state, and a pin that never reaches the ledger is
# exactly the bug this instrument hunts. They keep reporting until someone reads
# one and decides.
READ_ONLY_DISPATCHES: dict[str, str] = {
    "concept_gate": "answers a concept/product-knowledge question; no task state",
    "referential_list": "lists workflows/projects the tenant already has",
    "show_org_design_viewer": "opens a viewer over already-committed state",
}


def report_unmoved_turn(*, conversation_id: str = "", dispatch: str = "",
                        answer_len: int = 0, extra: Any = None) -> bool:
    """Log a turn that answered without moving the plane. True when reported."""
    if should_defer_plane_report():
        return False
    declared = READ_ONLY_DISPATCHES.get((dispatch or "").strip())
    if declared and not _read_only.get():
        # Same outcome as the handler having called declare_read_only_turn --
        # one code path, so "declared read-only" never means two things.
        _read_only.set(declared)
    # ONE decider. This function used to open-code TC-L's rule — moved,
    # read-only, declared-dispatch — while `claimed_turn_is_complete` sat in
    # the contract module named for it with no caller anywhere. That is not
    # "a declaration with no reader", it is the sharper failure the backlog
    # records three times: a second, weaker resolver beside the real one.
    # They agreed today. Nothing made them agree tomorrow.
    from conversation_control_plane.claimed_turn_complete_contract import (
        claimed_turn_is_complete,
    )

    if claimed_turn_is_complete(
        answered=True,
        plane_moved=turn_moved_the_plane(),
        read_only_declared=bool(_read_only.get()),
    ):
        return False
    logger.warning(
        "PLANE_UNMOVED conv=%s dispatch=%s answer_len=%d — a turn answered "
        "without beginning, advancing or completing a task, and did not "
        "declare itself read-only. The next turn will have nothing to "
        "continue. extra=%s",
        conversation_id or "?", dispatch or "?", answer_len, extra,
    )
    # A warning nobody reads is an instrument that does not exist. The
    # stray-write ratchet was honest and invisible for weeks; this one lands in
    # the durable event log so the ~12 static write-site candidates can be
    # replaced by the handful that actually fire, each with a conversation id.
    try:
        from api.services.event_logger import log_platform_event_bg

        log_platform_event_bg(
            "turn_plane_unmoved",
            "warning",
            "Turn answered without moving the control plane",
            details={
                "conversation_id": conversation_id or "",
                "dispatch": dispatch or "",
                "answer_len": int(answer_len),
                "sources": list(extra) if isinstance(extra, (list, tuple)) else [],
            },
            reference_id=conversation_id or None,
        )
    except Exception:  # noqa: BLE001 - telemetry never breaks a turn
        logger.debug("plane_unmoved event emit skipped", exc_info=True)
    return True
