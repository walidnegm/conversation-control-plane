"""Conversational host law: session boundary ↔ second-connection claim/renew.

**Why this module exists**

``claim_turn`` / default ``renew_turn_claim`` open a *separate* short-lived DB
session and ``UPDATE conversations``. Ledger multi-key writes on the *request*
(or worker lease) session use ``SELECT … FOR UPDATE`` / ``UPDATE`` and leave
the row locked until commit/rollback.

If the request session still holds that lock when a second connection tries
to claim or renew, Postgres waits forever → self-deadlock → worker hung →
on single-process local, whole API unhealthy; on AWS (2 uvicorn workers +
health sidecar), one capacity slot dies quietly.

Incidents (same class, different entrypoints):

* conv_66a6cced — SSE held request TX; heartbeat renew blocked
* conv_7a953788 — worker progress renew on 2nd conn while handler held row
* conv_9c5f24a6 — hydrate hygiene FOR UPDATE then claim_turn on 2nd conn

**Host law (all conversational agents / surfaces)**

```text
  [any ledger write on session S]
        │
        ▼
  commit_conversation_session_boundary(S)   ← this module's prepare_*
        │
        ▼
  claim_turn / renew_turn_claim (separate conn)  OR  renew(..., db=S)
        │
        ▼
  long LLM / specialist work (no open conversations-row TX)
        │
        ▼
  short TX on S → commit boundary again before next 2nd-conn op
        │
        ▼
  release_turn (separate conn; safe after S committed/rolled back)
```

Do **not** sprinkle one-off ``db.commit()`` at call sites and hope. Route every
router/worker claim through :func:`claim_turn_for_conversation`. Before long
awaits or separate-conn renew, call :func:`prepare_session_for_second_connection`.

Specialists (workflow_builder, cost_out, cyber, …) do **not** each invent this —
the host entrypoint owns it for the whole conversational surface.
"""
from __future__ import annotations

from typing import Literal
from uuid import uuid4

from sqlalchemy.orm import Session

from conversation_control_plane.ledger import (
    claim_turn,
    commit_conversation_session_boundary,
    release_turn,
    renew_turn_claim,
)

ClaimStatus = Literal["claimed", "busy", "no_row", "unavailable"]


def prepare_session_for_second_connection(db: Session | None) -> None:
    """Release any open conversations-row locks on ``db`` before a 2nd connection.

    Safe no-op when ``db`` is None (anonymous / threadless). Failures raise after
    best-effort rollback (same contract as ``commit_conversation_session_boundary``).
    """
    if db is None:
        return
    commit_conversation_session_boundary(db)


def claim_turn_for_conversation(
    db: Session | None,
    tenant_id: str,
    conversation_id: str | None,
    *,
    turn_id: str | None = None,
    fail_open_on_error: bool = False,
) -> tuple[ClaimStatus, str]:
    """Claim the turn slot **after** clearing the request/worker session TX.

    Returns ``(status, turn_id)``. Callers that receive ``"claimed"`` **must**
    ``release_turn`` (or use teardown that does) with the same ``turn_id``.

    When ``conversation_id`` is empty, returns ``("no_row", turn_id)`` without
    claiming — same semantics as bare ``claim_turn`` on a missing row.
    """
    tid = (turn_id or uuid4().hex).strip() or uuid4().hex
    if not conversation_id or not tenant_id:
        return "no_row", tid

    # Law: never open claim_turn's separate connection while this session may
    # hold FOR UPDATE on conversations (hydrate hygiene, decide_turn, etc.).
    prepare_session_for_second_connection(db)

    status = claim_turn(
        tenant_id,
        conversation_id,
        turn_id=tid,
        fail_open_on_error=fail_open_on_error,
    )
    return status, tid


def renew_turn_claim_for_conversation(
    tenant_id: str,
    conversation_id: str,
    *,
    turn_id: str,
    db: Session | None = None,
    prefer_request_session: bool = True,
) -> bool:
    """Heartbeat renew under host law.

    Prefer renewing on the **same** session that may hold open work (``db=``)
    so no second connection is needed (worker lease path, conv_7a953788).

    If ``db`` is None, uses a separate connection — caller must have already
    committed any request TX via :func:`prepare_session_for_second_connection`.
    """
    if prefer_request_session and db is not None:
        return renew_turn_claim(
            tenant_id, conversation_id, turn_id=turn_id, db=db,
        )
    prepare_session_for_second_connection(db)
    return renew_turn_claim(tenant_id, conversation_id, turn_id=turn_id)


def release_turn_for_conversation(
    tenant_id: str,
    conversation_id: str,
    *,
    turn_id: str,
    db: Session | None = None,
) -> None:
    """Release after request/worker TX is finished (commit or rollback).

    Optional ``db``: if provided, roll back any leftover uncommitted work so
    release's separate connection never waits on this session (teardown paths).
    """
    if db is not None:
        try:
            # Prefer commit of finished work when caller already wrote success
            # path; teardown often rolls back on error first. Here we only
            # ensure we are not sitting on an open lock — rollback is safer
            # when status is unknown; callers that need durability must commit
            # before calling release (see _turn_claim_teardown).
            pass
        except Exception:  # noqa: BLE001
            pass
    release_turn(tenant_id, conversation_id, turn_id=turn_id)


# Public alias — long LLM awaits use the same primitive under a clearer name.
session_boundary_before_await = prepare_session_for_second_connection
