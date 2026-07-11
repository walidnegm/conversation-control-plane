"""Typed failure-mode contract for the conversation control plane.

Stable codes for observability, frontend recovery, and auto-coder integration.
Compensation hooks are advisory — callers decide whether to retry or clarify.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

# Stable codes (pin in regression + SDK §13).
CODE_TURN_IN_FLIGHT = "conversation_turn_in_flight"
CODE_HOT_POTATO_LOOP = "handoff_ping_pong_blocked"
CODE_AGENT_RESOLUTION_MISS = "conversational_agent_unresolved"
CODE_STALE_CONTROL_REVISION = "control_revision_stale"
CODE_TURN_CLAIM_UNAVAILABLE = "turn_claim_unavailable"
CODE_CLASSIFIER_FAIL_OPEN = "classifier_fail_open"
CODE_UNCLEAR_INTENT = "intent_unclear"
CODE_TRANSIENT_ROUTING_FAILURE = "transient_routing_failure"
CODE_DETOUR_REPEAT_BLOCKED = "detour_repeat_blocked"


@dataclass(frozen=True)
class ControlPlaneFailure:
    code: str
    message: str
    hint: Optional[str] = None
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            out["hint"] = self.hint
        if self.retryable:
            out["retryable"] = True
        return out


FAILURE_TURN_IN_FLIGHT = ControlPlaneFailure(
    code=CODE_TURN_IN_FLIGHT,
    message="A previous turn is still executing for this conversation.",
    hint="Wait a few seconds and send again.",
    retryable=True,
)

FAILURE_HOT_POTATO = ControlPlaneFailure(
    code=CODE_HOT_POTATO_LOOP,
    message="That handoff would bounce between specialists without advancing your task.",
    hint="Stay on the current specialist or say explicitly which one you want.",
)

FAILURE_AGENT_UNRESOLVED = ControlPlaneFailure(
    code=CODE_AGENT_RESOLUTION_MISS,
    message="The requested specialist is not registered.",
    hint="Fall back to the front door and retry with a clearer goal.",
)

FAILURE_STALE_REVISION = ControlPlaneFailure(
    code=CODE_STALE_CONTROL_REVISION,
    message="Conversation control state changed before this decision could run.",
    hint="Refresh the thread and send your message again.",
    retryable=True,
)

FAILURE_TURN_CLAIM_UNAVAILABLE = ControlPlaneFailure(
    code=CODE_TURN_CLAIM_UNAVAILABLE,
    message="Could not serialize this conversation turn (claim infrastructure failed).",
    hint="Retry in a moment. Do not send a second concurrent turn for the same thread.",
    retryable=True,
)


class TurnClaimInfrastructureError(Exception):
    """Raised when claim_turn cannot reach a live claim decision (DB/SQL failure).

    Fail-closed default: hosts must **not** run the turn unclaimed. Opt into
    ``claim_turn(..., fail_open_on_error=True)`` only for degraded local extract
    hosts that deliberately accept double-run risk.
    """

    def __init__(
        self,
        message: str = "turn claim infrastructure unavailable",
        *,
        conversation_id: str = "",
        tenant_id: str = "",
        cause: BaseException | None = None,
    ) -> None:
        self.conversation_id = conversation_id or ""
        self.tenant_id = tenant_id or ""
        self.cause = cause
        self.code = CODE_TURN_CLAIM_UNAVAILABLE
        super().__init__(message)

    def to_failure(self) -> ControlPlaneFailure:
        return FAILURE_TURN_CLAIM_UNAVAILABLE


class StaleControlRevisionError(Exception):
    """Raised when a mutation's ``expected_version`` does not match live revision.

    Callers may map this to ``FAILURE_STALE_REVISION`` / HTTP 409 without
    re-deriving meaning from free text.
    """

    def __init__(
        self,
        *,
        expected: int,
        actual: int,
        conversation_id: str = "",
        tenant_id: str = "",
    ) -> None:
        self.expected = int(expected)
        self.actual = int(actual)
        self.conversation_id = conversation_id or ""
        self.tenant_id = tenant_id or ""
        self.code = CODE_STALE_CONTROL_REVISION
        super().__init__(
            f"control_revision stale: expected={self.expected} actual={self.actual}"
            + (f" conversation={self.conversation_id}" if self.conversation_id else "")
        )

    def to_failure(self) -> ControlPlaneFailure:
        return FAILURE_STALE_REVISION

FAILURE_CLASSIFIER_FAIL_OPEN = ControlPlaneFailure(
    code=CODE_CLASSIFIER_FAIL_OPEN,
    message="Intent classification was unavailable; routing used safe fallbacks.",
)

FAILURE_UNCLEAR_INTENT = ControlPlaneFailure(
    code=CODE_UNCLEAR_INTENT,
    message="Could not determine how this message relates to the active task.",
    hint="Rephrase or pick a numbered option if one was offered.",
)

FAILURE_TRANSIENT_ROUTING = ControlPlaneFailure(
    code=CODE_TRANSIENT_ROUTING_FAILURE,
    message="Routing was temporarily unavailable — your active task is unchanged.",
    hint="Send your message again to continue where you left off.",
    retryable=True,
)

FAILURE_DETOUR_REPEAT = ControlPlaneFailure(
    code=CODE_DETOUR_REPEAT_BLOCKED,
    message="That detour already ran — continuing your active task instead.",
    hint="Say **continue** or name the next step on your current workflow.",
)


def should_resume_active_task_on_failure(
    code: str,
    *,
    active_task: dict | None,
) -> bool:
    """Transient failures keep the ledger task; only unrecoverable paths drop to bot0."""
    if not isinstance(active_task, dict) or not active_task.get("agent"):
        return False
    return code in {
        CODE_TRANSIENT_ROUTING_FAILURE,
        CODE_CLASSIFIER_FAIL_OPEN,
        CODE_STALE_CONTROL_REVISION,
        CODE_TURN_IN_FLIGHT,
    }


_COMPENSATION_HOOKS: dict[str, Callable[..., Any]] = {}


def register_compensation_hook(code: str, handler: Callable[..., Any]) -> None:
    """Register an optional recovery handler for a failure code."""
    _COMPENSATION_HOOKS[code] = handler


def run_compensation(code: str, **kwargs: Any) -> Any:
    """Invoke a registered compensation hook, or return None."""
    handler = _COMPENSATION_HOOKS.get(code)
    if handler is None:
        return None
    return handler(**kwargs)


__all__ = [
    "CODE_AGENT_RESOLUTION_MISS",
    "CODE_CLASSIFIER_FAIL_OPEN",
    "CODE_DETOUR_REPEAT_BLOCKED",
    "CODE_HOT_POTATO_LOOP",
    "CODE_STALE_CONTROL_REVISION",
    "CODE_TRANSIENT_ROUTING_FAILURE",
    "CODE_TURN_IN_FLIGHT",
    "CODE_UNCLEAR_INTENT",
    "ControlPlaneFailure",
    "FAILURE_AGENT_UNRESOLVED",
    "FAILURE_CLASSIFIER_FAIL_OPEN",
    "FAILURE_DETOUR_REPEAT",
    "FAILURE_HOT_POTATO",
    "FAILURE_STALE_REVISION",
    "FAILURE_TRANSIENT_ROUTING",
    "FAILURE_TURN_IN_FLIGHT",
    "FAILURE_UNCLEAR_INTENT",
    "register_compensation_hook",
    "run_compensation",
    "should_resume_active_task_on_failure",
]