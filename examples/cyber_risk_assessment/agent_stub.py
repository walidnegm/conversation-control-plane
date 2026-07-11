"""Cyber risk assessment — contract-complete specialist scaffold (not product code).

This is the **coding-agent-facing shape** of a sole-continue specialist under
SDK production-grade L2 (Model A) + multi-turn stream + KindSpec + thin payload.

Not shipped: production scoring, tenant corpora, LangGraph strategist, product UI.
Wait for a full agent dump only if you need domain depth — most adopters need
this contract + the host sketch + the SDK adopter brief.

Host must:

- register :data:`kind_spec.CYBER_RISK_KIND_SPEC`
- ``begin_task(kind=cyber_risk_assessment)`` when starting (ledger assigns ``task_id``)
- store domain IR under ``pending_ref`` (specialist store) — **not** fat projection
- pin entity ids on thin payload after resolve
- gate continue turns — ``multi_turn_stream_contract``
- write control keys **only** via ``decide_turn`` / ledger APIs
- map COMPLETE vs ABANDON distinctly (journal event types differ)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol
from uuid import uuid4

try:
    from .assessment_ir import AssessmentPhase, CyberRiskAssessmentIR
    from .kind_spec import KIND, CYBER_RISK_KIND_SPEC
except ImportError:  # running as a script next to this file
    from assessment_ir import AssessmentPhase, CyberRiskAssessmentIR
    from kind_spec import KIND, CYBER_RISK_KIND_SPEC


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
    # P15 thin projection only — pins + routing keys, never full IR/draft/graph.
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
    # Domain-only side channel for the host to persist under pending_ref.
    domain_patch: dict = field(default_factory=dict)
    task_id: Optional[str] = None
    kind: Optional[str] = None
    command_id: Optional[str] = None
    outcome_reason: Optional[str] = None


class DomainStore(Protocol):
    """Specialist store keyed by pending_ref — owns IR / score artifacts."""

    def load_ir(self, pending_ref: str) -> dict: ...
    def save_ir(self, pending_ref: str, ir: dict) -> None: ...


class InMemoryDomainStore:
    """Tiny default for local demos — replace with Redis/Postgres table in product."""

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    def load_ir(self, pending_ref: str) -> dict:
        return dict(self._rows.get(pending_ref) or {})

    def save_ir(self, pending_ref: str, ir: dict) -> None:
        self._rows[pending_ref] = dict(ir)


def _new_command_id() -> str:
    return f"cmd_{uuid4().hex[:16]}"


def _thin_payload(
    *,
    workflow_id: str = "",
    subject_id: str = "",
    subject_kind: str = "",
) -> dict:
    """P15: only pin keys that KindSpec.allowed_payload_keys permits."""
    out: dict = {}
    if workflow_id:
        out["workflow_id"] = workflow_id
    if subject_id:
        out["subject_id"] = subject_id
    if subject_kind:
        out["subject_kind"] = subject_kind
    # Drop anything not allowed (defense in depth for coding agents).
    allowed = CYBER_RISK_KIND_SPEC.allowed_payload_keys
    return {k: v for k, v in out.items() if k in allowed}


class CyberRiskAssessmentAgent:
    """Bounded specialist — terminal COMPLETE / ABANDON clear stickiness via host."""

    agent_id = "cyber_risk_assessment"
    task_kind: Literal["bounded", "unbounded"] = "bounded"
    KIND = KIND
    KIND_SPEC = CYBER_RISK_KIND_SPEC

    def __init__(self, domain: Optional[DomainStore] = None) -> None:
        self.domain: DomainStore = domain or InMemoryDomainStore()

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
        """Execute one turn — returns transition intent; host writes ledger."""
        _ = (db, tenant_id, history)  # host injects; specialist does not write control keys
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

        conv = thread_id or str((context or {}).get("conversation_id") or "local")
        pref = (
            str(active.get("pending_ref") or "").strip()
            if isinstance(active, dict)
            else ""
        ) or self.pending_ref_for(conv)

        # Domain IR lives under pending_ref — not in active_task.payload (P15).
        ir = CyberRiskAssessmentIR.model_validate(self.domain.load_ir(pref) or {})
        pinned_wf = str(payload.get("workflow_id") or ir.subject_id or "").strip()
        cmd = _new_command_id()
        q = (query or "").strip().lower()

        # Finite cancel grammar only (armed cancel) — not general NL routing.
        if q in ("cancel", "stop", "abort", "exit") or q.startswith("cancel "):
            req = TaskTransitionRequest(
                transition="abandon",
                task_id=task_id,
                kind=self.KIND,
                phase="cancelled",
                command_id=cmd,
                outcome_reason="abandon",
                pending_ref=pref,
            )
            return AgentTurnResult(
                answer={"answer": "Cyber risk assessment cancelled.", "sources": [], "blocks": []},
                transition=req,
                phase="cancelled",
                task_id=task_id,
                kind=self.KIND,
                command_id=cmd,
                outcome_reason="abandon",
                pending_ref=pref,
            )

        if ir.phase == AssessmentPhase.COMPLETE:
            req = TaskTransitionRequest(
                transition="complete",
                task_id=task_id,
                kind=self.KIND,
                phase=AssessmentPhase.COMPLETE.value,
                command_id=cmd,
                outcome_reason="complete",
                pending_ref=pref,
            )
            return AgentTurnResult(
                answer={"answer": "Assessment is complete.", "sources": [], "blocks": []},
                transition=req,
                phase=AssessmentPhase.COMPLETE.value,
                task_id=task_id,
                kind=self.KIND,
                command_id=cmd,
                outcome_reason="complete",
                pending_ref=pref,
            )

        # First turn: declare BEGIN so host assigns task_id (agent never invents it).
        if not task_id:
            ir.phase = AssessmentPhase.ANCHOR
            self.domain.save_ir(pref, ir.model_dump())
            req = TaskTransitionRequest(
                transition="begin",
                kind=self.KIND,
                phase=ir.phase.value,
                awaiting="subject",
                pending_ref=pref,
                command_id=cmd,
                payload_patch=_thin_payload(),
            )
            return AgentTurnResult(
                answer={
                    "answer": (
                        "Starting cyber assessment (**scaffold**). "
                        "Pin a workflow/subject id, then continue."
                    ),
                    "sources": ["cyber_risk_assessment_scaffold"],
                    "blocks": [],
                },
                transition=req,
                phase=ir.phase.value,
                awaiting="subject",
                pending_ref=pref,
                domain_patch={"ir": ir.model_dump()},
                kind=self.KIND,
                command_id=cmd,
            )

        # Anchor: pin from a simple id token (host may resolve names before this).
        # Coding agents: replace with real entity resolve only while phase allows.
        if ir.phase == AssessmentPhase.ANCHOR and (query or "").strip():
            token = (query or "").strip()
            # If host already pinned, keep it; else treat query as subject id pin demo.
            if not pinned_wf:
                pinned_wf = token.split()[0][:64]
                ir.subject_id = pinned_wf
                ir.subject_kind = "workflow"
            ir.phase = AssessmentPhase.DISCOVER
            awaiting = "in_progress"
        elif ir.phase == AssessmentPhase.VERIFY:
            # HITL seam: wait for supervisor approve (finite grammar when armed).
            if q in ("approve", "approved", "lgtm", "yes"):
                ir.phase = AssessmentPhase.SCORE
                awaiting = "in_progress"
            else:
                awaiting = "human_approval"
        elif ir.phase == AssessmentPhase.SCORE:
            ir.phase = AssessmentPhase.COMPLETE
            awaiting = None
            self.domain.save_ir(pref, ir.model_dump())
            req = TaskTransitionRequest(
                transition="complete",
                task_id=task_id,
                kind=self.KIND,
                phase=AssessmentPhase.COMPLETE.value,
                command_id=cmd,
                outcome_reason="complete",
                pending_ref=pref,
                payload_patch=_thin_payload(
                    workflow_id=pinned_wf,
                    subject_id=ir.subject_id,
                    subject_kind=ir.subject_kind,
                ),
            )
            return AgentTurnResult(
                answer={
                    "answer": "Assessment **complete** (scaffold score placeholder).",
                    "sources": ["cyber_risk_assessment_scaffold"],
                    "blocks": [],
                },
                transition=req,
                phase=AssessmentPhase.COMPLETE.value,
                task_id=task_id,
                kind=self.KIND,
                command_id=cmd,
                outcome_reason="complete",
                pending_ref=pref,
                domain_patch={"ir": ir.model_dump()},
            )
        else:
            # Advance one step on any non-empty continue (demo only).
            nxt = ir.next_phase()
            if nxt and nxt != AssessmentPhase.COMPLETE:
                ir.phase = nxt
            awaiting = (
                "human_approval"
                if ir.phase == AssessmentPhase.VERIFY
                else "in_progress"
            )

        self.domain.save_ir(pref, ir.model_dump())
        thin = _thin_payload(
            workflow_id=pinned_wf,
            subject_id=ir.subject_id,
            subject_kind=ir.subject_kind,
        )
        req = TaskTransitionRequest(
            transition="continue",
            task_id=task_id,
            kind=self.KIND,
            phase=ir.phase.value,
            awaiting=awaiting,
            pending_ref=pref,
            command_id=cmd,
            payload_patch=thin,
        )
        pin_note = f" pin=`{pinned_wf}`" if pinned_wf else ""
        hitl = (
            " Waiting for supervisor **approve**."
            if awaiting == "human_approval"
            else ""
        )
        return AgentTurnResult(
            answer={
                "answer": (
                    f"Cyber assessment **scaffold** — phase **{ir.phase.value}**"
                    f"{pin_note}.{hitl} Not product scoring code."
                ),
                "sources": ["cyber_risk_assessment_scaffold"],
                "blocks": [],
            },
            transition=req,
            phase=ir.phase.value,
            awaiting=awaiting,
            pending_ref=pref,
            domain_patch={"ir": ir.model_dump()},
            task_id=task_id,
            kind=self.KIND,
            command_id=cmd,
        )
