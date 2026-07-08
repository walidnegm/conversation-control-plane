"""Cyber risk assessment — ConversationalAgent stub (SDK §9.1 bounded pattern)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from .assessment_ir import (
    AssessmentPhase,
    CyberRiskAssessmentIR,
)


@dataclass(frozen=True)
class TaskTransition:
    intent: Literal["begin", "continue", "complete", "detour", "abandon"]
    phase: Optional[str] = None
    awaiting: Optional[str] = None


@dataclass
class AgentTurnResult:
    answer: dict
    transition: TaskTransition
    phase: Optional[str] = None
    awaiting: Optional[str] = None
    pending_ref: Optional[str] = None
    context_updates: dict = field(default_factory=dict)


class CyberRiskAssessmentAgent:
    """Bounded specialist — terminal COMPLETE clears stickiness."""

    agent_id = "cyber_risk_assessment"
    task_kind: Literal["bounded", "unbounded"] = "bounded"

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
        payload = (context or {}).get("active_task", {}).get("payload") or {}
        ir = CyberRiskAssessmentIR.model_validate(payload.get("ir") or {})

        if ir.phase == AssessmentPhase.COMPLETE:
            return AgentTurnResult(
                answer={"answer": "Assessment is complete.", "sources": [], "blocks": []},
                transition=TaskTransition(intent="complete"),
            )

        # Stub: advance phase on any non-empty turn after anchor.
        if ir.phase == AssessmentPhase.ANCHOR and (query or "").strip():
            ir.phase = AssessmentPhase.DISCOVER

        next_phase = ir.next_phase()
        transition = TaskTransition(
            intent="continue",
            phase=ir.phase.value,
            awaiting="in_progress",
        )
        return AgentTurnResult(
            answer={
                "answer": f"Cyber assessment stub — phase **{ir.phase.value}**.",
                "sources": ["cyber_risk_assessment_stub"],
                "blocks": [],
            },
            transition=transition,
            phase=ir.phase.value,
            awaiting="in_progress",
            pending_ref=self.pending_ref_for(thread_id or ""),
            context_updates={"ir": ir.model_dump()},
        )