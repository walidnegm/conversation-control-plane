"""Minimal contract-first IR for the cyber risk assessment scaffold (v1).

Domain-only — store under pending_ref, never on active_task.payload (P15).
Stdlib only (no pydantic) so host_sketch runs with plain Python.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal


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


@dataclass
class CyberRiskAssessmentIR:
    ir_version: Literal["cyber_risk_assessment_ir_v1"] = "cyber_risk_assessment_ir_v1"
    phase: AssessmentPhase = AssessmentPhase.ANCHOR
    subject_kind: str = ""  # workflow | agent | tenant | ""
    subject_id: str = ""
    verify_queue: list[str] = field(default_factory=list)

    def next_phase(self) -> AssessmentPhase | None:
        try:
            idx = PHASE_ORDER.index(self.phase)
        except ValueError:
            return None
        if idx >= len(PHASE_ORDER) - 1:
            return None
        return PHASE_ORDER[idx + 1]

    def model_dump(self) -> dict[str, Any]:
        d = asdict(self)
        d["phase"] = self.phase.value if isinstance(self.phase, AssessmentPhase) else str(self.phase)
        return d

    @classmethod
    def model_validate(cls, data: Any) -> "CyberRiskAssessmentIR":
        if not data:
            return cls()
        if isinstance(data, cls):
            return data
        raw = dict(data)
        phase = raw.get("phase") or AssessmentPhase.ANCHOR
        if isinstance(phase, str):
            phase = AssessmentPhase(phase)
        return cls(
            ir_version=raw.get("ir_version") or "cyber_risk_assessment_ir_v1",
            phase=phase,
            subject_kind=str(raw.get("subject_kind") or ""),
            subject_id=str(raw.get("subject_id") or ""),
            verify_queue=list(raw.get("verify_queue") or []),
        )
