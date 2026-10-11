"""TC-L — a claimed turn must complete.

**Law (SDK TARGET):** if a claimant takes the turn it owes a complete
outcome or an explicit refusal. Hollow = the turn **spoke** and
**neither plane moved**.

| Complete | Incomplete (hollow) |
|----------|---------------------|
| Control mutation (ledger begin/advance/complete) | Answer + stale ``active_task`` |
| Declared read-only (glossary, inventory list) | Answer + no declaration |
| Typed refuse | Half-answer / fail-soft with no awaiting |

**Not** a ``chat()`` rewrite. Both host rails call
:func:`finalize_claimed_turn`:

* ``bot0._validate_output`` (inline chat)
* ``workflow_builder_turn`` **after** the ledger mirror (async worker)

Worker re-entry sets :func:`set_defer_plane_report` so the inline rail does
not fire ``turn_plane_unmoved`` **before** the worker writes the ledger
(conv_4ac10b7c Continue to staffing).

Fat-leaf answers must arm the matching ``awaiting``
(:func:`fat_leaf_awaiting_matches` · ``ledger_phase_awaiting_from_blocks``).

Incident: ``conv_4ac10b7c``. Failure class: ``claimed_turn_incomplete``.
"""
from __future__ import annotations

from typing import Any

FAILURE_CLASS = "claimed_turn_incomplete"
INCIDENT = "conv_4ac10b7c"
SDK_ANCHOR = "sdk-target-claimed-turn-complete"

#: Pickers whose finite grammar is a chip, not yes/ok. Exact confirm here is
#: fail-soft: re-show the card. Confirm that ADVANCES a gate lives in
#: ``CONFIRM_AWAITING_GATES`` (IR / commit / review) — not this set.
#: conv_7eb60d26 / conv_40db3389: domain picker on screen, user typed "ok",
#: continue cleared awaiting and the LLM answered with blocks=[].
FAT_LEAF_CONFIRM_IS_NOT_ADVANCE: frozenset[str] = frozenset({"domain"})


def claimed_turn_is_complete(
    *,
    answered: bool,
    plane_moved: bool,
    read_only_declared: bool,
    typed_refuse: bool = False,
) -> bool:
    """True when an answering turn satisfied TC-L."""
    if not answered:
        return True
    return bool(plane_moved or read_only_declared or typed_refuse)


def fat_leaf_awaiting_matches(
    blocks: Any,
    awaiting: str | None,
) -> bool:
    """Shipped fat leaf must match ledger awaiting (or there is no fat leaf)."""
    try:
        from conversation_control_plane.dispatch_phase import (
            ledger_phase_awaiting_from_blocks,
        )
    except Exception:  # noqa: BLE001
        return True
    _phase, expected = ledger_phase_awaiting_from_blocks(blocks)
    if not expected:
        return True
    return str(awaiting or "").strip() == str(expected).strip()


def arm_fat_leaf_awaiting(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    result: Any = None,
    blocks: Any = None,
) -> str | None:
    """Write the awaiting the shipped card implies. Returns what it armed.

    **The inline half of TC-L.** ``ledger_phase_awaiting_from_blocks`` already
    knows that a ``workflow_domain_picker`` means ``awaiting="domain"`` — the
    map is right and has been. Only the async worker ever *wrote* it. On the
    inline rail the same derivation was called for one purpose: to decide
    whether to put ``fat_leaf_awaiting_mismatch`` in a log line.

    So a card asking a bounded question could reach the user with the ledger
    owning nothing, and the next turn had nothing to continue — AGENTS §2
    *open-leaf arming*: the package that asks must arm who owns the reply.

    Incident ``conv_40db3389``: staffing accepted, the domain picker shipped,
    ``awaiting`` stayed null while ``phase`` said ``domain_picker``, and "ok"
    fell through to the conversational LLM — *"Great! If you have any more
    questions…"* — with ``blocks=[]``. Measured at the time: **20 of 138** live
    ``workflow_build`` tasks held a phase and no awaiting, and
    ``domain_picker`` appeared BOTH armed (2) and unarmed (1), which is the
    two-rails signature rather than randomness.

    Deliberately narrow, because an arming write is an authority:

    * only for a block type in the closed ``_FAT_LEAF_LEDGER`` map;
    * only when an active task **already exists** — this never mints one
      (``threadless_turn_bind_contract``: protocol surfaces do not mint);
    * only when the task's agent owns the card;
    * only when the derived awaiting **differs**, so it is idempotent;
    * never raises — a turn must not fail because its bookkeeping did.

    ``blocks=`` is the delivery-choke-point entry (2026-09-16). This was wired
    to ONE rail — ``_finalize_result``, 37 call sites — while **149** leaves in
    bot0.py return straight through ``_validate_output`` / ``_deliver_grounded``
    and never reached it. Every ``pre_decide_short_circuit`` leaf is in that
    second group, so a code-dispatch host could ship a Draft IR card with the
    ledger owning nothing. Measured: all **5** post-fix ``workflow_ir_review``
    asks-without-a-reader were such leaves — ``authoring_checkpoint`` (3,
    09-11) and ``ir_gate_finite_token_worker_exclusive`` (2, 09-14, in
    ``conv_4ac10b7c`` — this contract's own anchor incident). Same shape as the
    path picker before ``arm_discovery_path_pick`` moved to the choke point:
    *a leaf gets its reader by rendering the block, not by remembering to.*
    """
    if db is None or not conversation_id:
        return None
    try:
        from conversation_control_plane.dispatch_phase import (
            ledger_phase_awaiting_from_blocks,
        )
        from conversation_control_plane.ledger import (
            get_control_state,
            update_phase,
        )
    except Exception:  # noqa: BLE001
        return None

    if blocks is None:
        answer = result.get("answer") if isinstance(result, dict) else None
        blocks = answer.get("blocks") if isinstance(answer, dict) else None
    try:
        phase, awaiting = ledger_phase_awaiting_from_blocks(blocks)
    except Exception:  # noqa: BLE001
        return None
    if not awaiting:
        return None

    try:
        state = get_control_state(db, tenant_id or "", conversation_id) or {}
        task = state.get("active_task")
        if not isinstance(task, dict) or not task.get("agent"):
            # No open task: the card is not a continuation of anything this
            # rail owns, and minting one here would be the bind this contract
            # forbids elsewhere.
            return None
        if str(task.get("awaiting") or "").strip() == str(awaiting).strip():
            return None
        update_phase(
            db,
            tenant_id=tenant_id or "",
            conversation_id=conversation_id,
            agent=str(task.get("agent")),
            phase=phase or str(task.get("phase") or "active"),
            awaiting=awaiting,
        )
        return awaiting
    except Exception:  # noqa: BLE001 — bookkeeping never breaks a turn
        import logging

        logging.getLogger(__name__).debug(
            "fat leaf awaiting arm skipped", exc_info=True,
        )
        return None


#: How far back to look for the card the reader was actually shown. A hollow
#: turn can follow it, so "the last message" is not the answer — measured on
#: 2026-09-14, 6 of 15 recoverable threads needed more than one step back.
STRANDED_LOOKBACK_MESSAGES: int = 8


def heal_stranded_awaiting(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    active_task: Any,
) -> str | None:
    """Recover a lost ``awaiting`` from the last card the user was shown.

    ``arm_fat_leaf_awaiting`` stops new strandings; it cannot reach the ones
    that already exist, and those threads are stuck precisely because nothing
    ships a card any more — the turn falls through to prose, so there is
    nothing to arm from. Measured 2026-09-14: **20** live ``workflow_build``
    tasks held a phase and no awaiting, **15** recoverable this way.

    Why it scans back rather than reading the last message: the hollow turn
    that strands a thread is itself the newest message, and it buried the card.
    ``conv_40db3389``'s domain picker is one step behind *"Great! If you have
    any more questions…"*. Reading only the last message recovers 9 of 20; the
    scan recovers 15.

    Narrow for the same reason arming is: a phase with no awaiting, an agent
    that owns it, and a card in the closed map. Never mints, never raises, and
    idempotent because the write it makes fails its own guard next time.
    """
    if db is None or not conversation_id:
        return None
    if not isinstance(active_task, dict):
        return None
    if str(active_task.get("awaiting") or "").strip():
        return None
    agent = str(active_task.get("agent") or "").strip()
    phase = str(active_task.get("phase") or "").strip()
    if not agent or not phase:
        return None

    try:
        import json as _json

        from sqlalchemy import text as _text

        from conversation_control_plane.dispatch_phase import (
            ledger_phase_awaiting_from_blocks,
        )
        from conversation_control_plane.ledger import update_phase

        rows = db.execute(
            _text(
                "SELECT blocks FROM conversation_messages "
                "WHERE conversation_id = :cid AND role = 'assistant' "
                "ORDER BY created_at DESC LIMIT :lim",
            ),
            {"cid": conversation_id, "lim": STRANDED_LOOKBACK_MESSAGES},
        ).fetchall()
    except Exception:  # noqa: BLE001
        return None

    for (raw,) in rows or []:
        blocks = raw
        if isinstance(blocks, str):
            try:
                blocks = _json.loads(blocks)
            except Exception:  # noqa: BLE001
                continue
        try:
            found_phase, awaiting = ledger_phase_awaiting_from_blocks(blocks)
        except Exception:  # noqa: BLE001
            continue
        if not awaiting:
            continue
        try:
            update_phase(
                db,
                tenant_id=tenant_id or "",
                conversation_id=conversation_id,
                agent=agent,
                phase=found_phase or phase,
                awaiting=awaiting,
            )
        except Exception:  # noqa: BLE001 — a repair never blocks routing
            import logging

            logging.getLogger(__name__).debug(
                "stranded awaiting heal skipped", exc_info=True,
            )
            return None
        return awaiting
    return None


def confirm_fails_soft_to_redisplay(
    *,
    awaiting: str | None,
    query: str | None,
) -> bool:
    """True when yes/ok must re-show the fat leaf, not advance or LLM.

    Domain chips are the grammar. ``ok`` is not a domain. Clearing awaiting
    on continue then handing the turn to the builder LLM is how
    conv_7eb60d26 sat mute until refresh.
    """
    aw = str(awaiting or "").strip()
    if aw not in FAT_LEAF_CONFIRM_IS_NOT_ADVANCE:
        return False
    try:
        from conversation_control_plane.finite_confirm_grammar import (
            CONFIRM_AWAITING_GATES,
            is_exact_confirm_or_decline,
        )
    except Exception:  # noqa: BLE001
        return False
    if aw in CONFIRM_AWAITING_GATES:
        return False
    return is_exact_confirm_or_decline(query or "")


def _fat_leaf_type(blocks: Any) -> str:
    """Which card the reader is looking at — for the report, not for policy."""
    try:
        from conversation_control_plane.dispatch_phase import (
            _FAT_LEAF_LEDGER,
        )
    except Exception:  # noqa: BLE001
        return "?"
    for b in (blocks or []):
        if isinstance(b, dict) and str(b.get("type") or "") in _FAT_LEAF_LEDGER:
            return str(b.get("type"))
    return "?"


def finalize_claimed_turn(
    *,
    conversation_id: str = "",
    dispatch: str = "",
    answer_len: int = 0,
    extra: Any = None,
    blocks: Any = None,
    awaiting: str | None = None,
) -> bool:
    """Output-rail hook: report plane-unmoved; note fat-leaf awaiting mismatch.

    Returns True when an unmoved answering turn was reported.
    """
    from conversation_control_plane.plane_movement import (
        report_unmoved_turn,
        should_defer_plane_report,
    )

    if should_defer_plane_report():
        return False
    detail: list[Any] = []
    if extra is not None:
        if isinstance(extra, (list, tuple)):
            detail.extend(extra)
        else:
            detail.append(extra)
    if blocks is not None and not fat_leaf_awaiting_matches(blocks, awaiting):
        # After `arm_fat_leaf_awaiting` runs on the same rail this is no longer
        # "worth noting" — the card shipped, the writer had everything it
        # needed, and the ledger still disagrees. Say which card, so the next
        # instance names itself instead of being found in a transcript.
        detail.append(
            f"fat_leaf_awaiting_mismatch:{_fat_leaf_type(blocks)}"
            f":ledger={awaiting or 'null'}",
        )
    return report_unmoved_turn(
        conversation_id=conversation_id,
        dispatch=dispatch,
        answer_len=answer_len,
        extra=detail or None,
    )


__all__ = [
    "FAILURE_CLASS",
    "INCIDENT",
    "SDK_ANCHOR",
    "STRANDED_LOOKBACK_MESSAGES",
    "FAT_LEAF_CONFIRM_IS_NOT_ADVANCE",
    "arm_fat_leaf_awaiting",
    "confirm_fails_soft_to_redisplay",
    "claimed_turn_is_complete",
    "fat_leaf_awaiting_matches",
    "heal_stranded_awaiting",
    "finalize_claimed_turn",
]
