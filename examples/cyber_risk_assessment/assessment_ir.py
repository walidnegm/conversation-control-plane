"""Minimal contract-first IR for the cyber risk assessment example (v1 stub)."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AssessmentPhase(str, Enum):
    ANCHOR = "anchor"
    DISCOVER = "discover"
    PROJECT = "project"
    VERIFY = "verify"
    SCORE = "score"
    COMPLETE = "complete"


PHASE_ORDER: tuple[AssessmentPhase, ...] = (
    AssessmentPhase.ANCHOR,
    AssessmentPhase.DISCOVER,
    AssessmentPhase.PROJECT,
    AssessmentPhase.VERIFY,
    AssessmentPhase.SCORE,
    AssessmentPhase.COMPLETE,
)


class InferenceField(BaseModel):
    """High-value fields only — full inference object on score-driving facts."""

    value: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    provenance: Literal["inferred", "retrieved", "confirmed", "user"] = "inferred"


class CyberRiskAssessmentIR(BaseModel):
    ir_version: Literal["cyber_risk_assessment_ir_v1"] = "cyber_risk_assessment_ir_v1"
    phase: AssessmentPhase = AssessmentPhase.ANCHOR
    subject_kind: Literal["workflow", "agent", "tenant", ""] = ""
    subject_id: str = ""
    verify_queue: list[str] = Field(default_factory=list)

    def next_phase(self) -> AssessmentPhase | None:
        try:
            idx = PHASE_ORDER.index(self.phase)
        except ValueError:
            return None
        if idx >= len(PHASE_ORDER) - 1:
            return None
        return PHASE_ORDER[idx + 1]