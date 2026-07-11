"""Cyber risk assessment — ConversationalAgent stub (SDK §9.1 + Model A L2).

Design stub only: no production scoring, no tenant data. Host must:

- ``begin_task(kind=cyber_risk_assessment)`` when starting (ledger assigns ``task_id``)
- pin entity ids on the payload after resolve
- gate continue turns (no greenfield re-resolve) — see multi_turn_stream_contract
- write control keys **only** via ``decide_turn`` / ledger APIs
- map COMPLETE vs ABANDON distinctly (journal event types differ)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from uuid import uuid4

from .assessment_ir import (
    AssessmentPhase,
    CyberRiskAssessmentIR,
)


# ---------------------------------------------------------------------------
# Thinned public contract (mirrors monorepo contract.py Model A fields)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskTransitionRequest:
    """Declarative lifecycle command — host maps this to ledger writes.

    Prefer this over ad-hoc kwargs. ``task_id`` is required for CONTINUE /
    COMPLETE / ABANDON once the task was begun with an id.
    """

    transition: Literal["begin", "continue", "complete", "abandon", "none"]
    task_id: Optional[str] = None
    kind: Optional[str] = None
    phase: Optional[str] = None
    awaiting: Optional[str] = None
    pending_ref: Optional[str] = None
    payload_patch: Optional[dict] = None
    outcome_reason: Optional[str] = None
    command_id: Optional[str] = None


@dataclass
class AgentTurnResult:
    """Return value from ``handle_turn`` — domain answer + lifecycle declaration.

    The agent never writes ``active_task`` / control keys. The host's
    ``decide_turn`` / ``apply_transition_request`` is the sole writer.
    """

    answer: dict
    transition: TaskTransitionRequest
    phase: Optional[str] = None
    awaiting: Optional[str] = None
    pending_ref: Optional[str] = None
    context_updates: dict = field(default_factory=dict)
    # Model A identity (optional on first turn; required after pin).
    task_id: Optional[str] = None
    kind: Optional[str] = None
    command_id: Optional[str] = None
    outcome_reason: Optional[str] = None


def _new_command_id() -> str:
    return f"cmd_{uuid4().hex[:16]}"


class CyberRiskAssessmentAgent:
    """Bounded specialist — terminal COMPLETE / ABANDON clear stickiness via host."""

    agent_id = "cyber_risk_assessment"
    task_kind: Literal["bounded", "unbounded"] = "bounded"
    KIND = "cyber_risk_assessment"

    def pending_ref_for(self, conversation_id: str) -> str:
        return f"cyber_risk:{conversation_id}"

    def handle_turn(
        self,
        db: Any,
        tenant_id: str,
        *,
        query: str,
        history: Optional[list[tuple[str, str]]] = None,
        context: Optional[dict] = None,
        thread_id: Optional[str] = None,
    ) -> AgentTurnResult:
        """Execute one turn — returns transition intent; decide_turn writes ledger."""
        active = (context or {}).get("active_task") or {}
        payload = active.get("payload") if isinstance(active, dict) else {}
        if not isinstance(payload, dict):
            payload = {}
        # Model A: never invent a task_id — only echo the projection's id.
        task_id = (
            str(active.get("task_id") or "").strip()
            if isinstance(active, dict)
            else ""
        ) or None
        ir = CyberRiskAssessmentIR.model_validate(payload.get("ir") or {})
        # Pin display only — never re-resolve identity from ambient last_read here.
        pinned_wf = str(payload.get("workflow_id") or "").strip()
        cmd = _new_command_id()
        q = (query or "").strip().lower()

        # Finite cancel grammar (host may also perceive abandon via classifier).
        if q in ("cancel", "stop", "abort", "exit") or q.startswith("cancel "):
            req = TaskTransitionRequest(
                transition="abandon",
                task_id=task_id,
                kind=self.KIND,
                command_id=cmd,
                outcome_reason="abandon",
            )
            return AgentTurnResult(
                answer={
                    "answer": "Cyber risk assessment cancelled.",
                    "sources": [],
                    "blocks": [],
                },
                transition=req,
                task_id=task_id,
                kind=self.KIND,
                command_id=cmd,
                outcome_reason="abandon",
            )

        if ir.phase == AssessmentPhase.COMPLETE:
            req = TaskTransitionRequest(
                transition="complete",
                task_id=task_id,
                kind=self.KIND,
                command_id=cmd,
                outcome_reason="complete",
            )
            return AgentTurnResult(
                answer={
                    "answer": "Assessment is complete.",
                    "sources": [],
                    "blocks": [],
                },
                transition=req,
                task_id=task_id,
                kind=self.KIND,
                command_id=cmd,
                outcome_reason="complete",
            )

        # Stub: advance phase on any non-empty turn after anchor.
        if ir.phase == AssessmentPhase.ANCHOR and (query or "").strip():
            ir.phase = AssessmentPhase.DISCOVER

        req = TaskTransitionRequest(
            transition="continue",
            task_id=task_id,
            kind=self.KIND,
            phase=ir.phase.value,
            awaiting="in_progress",
            pending_ref=self.pending_ref_for(thread_id or ""),
            command_id=cmd,
            payload_patch={"ir": ir.model_dump()},
        )
        pin_note = f" (pinned `{pinned_wf}`)" if pinned_wf else ""
        return AgentTurnResult(
            answer={
                "answer": (
                    f"Cyber assessment **stub** — phase **{ir.phase.value}**{pin_note}. "
                    "Not production product code."
                ),
                "sources": ["cyber_risk_assessment_stub"],
                "blocks": [],
            },
            transition=req,
            phase=ir.phase.value,
            awaiting="in_progress",
            pending_ref=self.pending_ref_for(thread_id or ""),
            context_updates={"ir": ir.model_dump()},  # domain-only
            task_id=task_id,
            kind=self.KIND,
            command_id=cmd,
        )
