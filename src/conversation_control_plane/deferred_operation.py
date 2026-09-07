"""Deferred operation continuity — portable Control Plane SDK contract.

Once an authorized operation returns ``DEFERRED``, the originating task
remains authoritative until that operation reaches a terminal state. A
host MUST preserve the operation reference and MUST NOT reinterpret the
deferred outcome as a completed conversational answer.

This module owns the *semantic* fact that execution left the current
turn. It does **not** own:

* worker / Temporal / LangGraph / Bedrock execution
* poll vs SSE vs WebSocket
* chat-row or card persistence
* product card UX

``execution_ref`` is opaque — same shape as ``pending_ref``. Hosts map
it to a job id, workflow id, run id, or any other runtime handle.

Lifecycle (``TaskTransition``) is a sibling, not a substitute:
``BEGIN`` / ``CONTINUE`` / ``COMPLETE`` answer *who owns the task*.
``OperationOutcome`` answers *whether authorized execution finished
inside this turn*.

    LLM proposes; code owns.
    Runtime executes; control plane owns continuity.

Host experience laws (observable, durable, reopenable conversation
artifacts) sit *above* this module. They are not this package.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

DEFERRED_CONTINUITY_LAW = (
    "Once an authorized operation returns DEFERRED, the originating "
    "task remains authoritative until that operation reaches a terminal "
    "state. A host MUST preserve the operation reference and MUST NOT "
    "reinterpret the deferred outcome as a completed conversational answer."
)

# TaskTransition values that keep the originating task alive.
DEFERRED_LEGAL_LIFECYCLES = frozenset({"begin", "continue"})

# COMPLETE ends stickiness; NONE means the turn had no task semantics.
# Either one drops authority while execution is still running.
DEFERRED_ILLEGAL_LIFECYCLES = frozenset({"complete", "none"})

# Host actions that mean "this turn is a finished conversational answer."
# Product adapters (queued / watching / deferred) must use a different token.
COMPLETED_CONVERSATIONAL_ACTIONS = frozenset({
    "answer",
    "complete",
    "completed",
})


class OperationOutcome(str, Enum):
    """Did authorized execution finish inside this turn?

    Not a sixth ``TaskTransition``. Lifecycle stays BEGIN/CONTINUE/COMPLETE/
    ABANDON/NONE. This enum is the execution-boundary result.
    """

    COMPLETED = "completed"
    DEFERRED = "deferred"
    FAILED = "failed"


class DeferredContinuation(str, Enum):
    """What the originating task is waiting on.

    Closed portable set. Hosts may map product phases onto these; they
    must not invent a parallel ownership machine.
    """

    AWAIT_RESULT = "await_result"
    AWAIT_TERMINAL = "await_terminal"


@dataclass(frozen=True)
class DeferredOperation:
    """Opaque continuation of an authorized operation.

    ``execution_ref`` is host-runtime identity. The control plane stores
    and correlates it; it does not parse it.
    """

    operation_id: str
    task_id: str
    originating_turn_id: str
    execution_ref: str
    continuation: str = DeferredContinuation.AWAIT_RESULT.value
    owner: Optional[str] = None


def is_deferred_outcome(outcome: OperationOutcome | str | None) -> bool:
    if outcome is None:
        return False
    value = outcome.value if isinstance(outcome, OperationOutcome) else str(outcome)
    return value.strip().lower() == OperationOutcome.DEFERRED.value


def is_completed_conversational_action(host_action: str | None) -> bool:
    action = (host_action or "").strip().lower()
    return action in COMPLETED_CONVERSATIONAL_ACTIONS


def make_deferred_operation(
    *,
    operation_id: str,
    task_id: str,
    originating_turn_id: str,
    execution_ref: str,
    continuation: str = DeferredContinuation.AWAIT_RESULT.value,
    owner: str | None = None,
) -> DeferredOperation:
    """Fail closed if any correlation identity is missing."""
    op = DeferredOperation(
        operation_id=(operation_id or "").strip(),
        task_id=(task_id or "").strip(),
        originating_turn_id=(originating_turn_id or "").strip(),
        execution_ref=(execution_ref or "").strip(),
        continuation=(continuation or DeferredContinuation.AWAIT_RESULT.value).strip(),
        owner=(owner or "").strip() or None,
    )
    missing = deferred_identity_errors(op)
    if missing:
        raise ValueError("; ".join(missing))
    return op


def deferred_identity_errors(deferred: DeferredOperation | None) -> list[str]:
    if deferred is None:
        return ["DEFERRED requires a DeferredOperation"]
    errors: list[str] = []
    if not deferred.operation_id:
        errors.append("operation_id is required")
    if not deferred.task_id:
        errors.append("task_id is required")
    if not deferred.originating_turn_id:
        errors.append("originating_turn_id is required")
    if not deferred.execution_ref:
        errors.append("execution_ref is required and must stay opaque")
    return errors


def deferred_continuity_errors(
    *,
    outcome: OperationOutcome | str | None,
    host_action: str | None = None,
    lifecycle: str | None = None,
    deferred: DeferredOperation | None = None,
) -> list[str]:
    """Host-conformance errors. Empty list = the envelope is legal.

    A host path that receives ``DEFERRED`` and returns a completed
    conversational answer has violated the Control Plane contract.
    """
    if not is_deferred_outcome(outcome):
        return []
    errors: list[str] = []
    errors.extend(deferred_identity_errors(deferred))
    action = (host_action or "").strip().lower()
    if not action or is_completed_conversational_action(action):
        errors.append(
            "DEFERRED must not be reinterpreted as a completed conversational "
            "answer (host action "
            f"{action!r} is empty or in COMPLETED_CONVERSATIONAL_ACTIONS)"
        )
    life = (lifecycle or "").strip().lower()
    if life in DEFERRED_ILLEGAL_LIFECYCLES:
        errors.append(
            f"DEFERRED requires lifecycle begin|continue; got {life!r}"
        )
    if life and life not in DEFERRED_LEGAL_LIFECYCLES | {"abandon"}:
        if life not in DEFERRED_ILLEGAL_LIFECYCLES:
            errors.append(
                f"DEFERRED does not recognize lifecycle {life!r}"
            )
    return errors


def violates_deferred_continuity(
    *,
    outcome: OperationOutcome | str | None,
    host_action: str | None = None,
    lifecycle: str | None = None,
    deferred: DeferredOperation | None = None,
) -> bool:
    return bool(
        deferred_continuity_errors(
            outcome=outcome,
            host_action=host_action,
            lifecycle=lifecycle,
            deferred=deferred,
        )
    )


__all__ = [
    "COMPLETED_CONVERSATIONAL_ACTIONS",
    "DEFERRED_CONTINUITY_LAW",
    "DEFERRED_ILLEGAL_LIFECYCLES",
    "DEFERRED_LEGAL_LIFECYCLES",
    "DeferredContinuation",
    "DeferredOperation",
    "OperationOutcome",
    "deferred_continuity_errors",
    "deferred_identity_errors",
    "is_completed_conversational_action",
    "is_deferred_outcome",
    "make_deferred_operation",
    "violates_deferred_continuity",
]
