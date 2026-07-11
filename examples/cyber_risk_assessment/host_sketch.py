"""Minimal host sketch — sole writer of control keys (in-memory).

Shows begin → continue → VERIFY human_approval → complete without Postgres.
Replace FakeLedger with your ledger.begin_task / apply_transition_request port.

Run:
  python -m examples.cyber_risk_assessment.host_sketch
  # or from this directory: python host_sketch.py
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional
from uuid import uuid4

from agent_stub import CyberRiskAssessmentAgent, TaskTransitionRequest
from kind_spec import CYBER_RISK_KIND_SPEC, register_in


class FakeLedger:
    """In-memory projection + journal — teaching shape only."""

    def __init__(self) -> None:
        self.context: dict[str, Any] = {}
        self.journal: list[dict] = []
        self._revision = 0
        self.kinds: dict = {}
        register_in(self.kinds)

    def begin_task(
        self,
        *,
        kind: str,
        phase: str,
        pending_ref: str,
        command_id: str,
        payload: Optional[dict] = None,
        agent: str = "cyber_risk_assessment",
    ) -> dict:
        assert kind in self.kinds, f"unregistered kind {kind}"
        task_id = f"task_{uuid4().hex[:12]}"
        active = {
            "task_id": task_id,
            "kind": kind,
            "phase": phase,
            "pending_ref": pending_ref,
            "payload": dict(payload or {}),
            "agent": agent,
        }
        self.context["active_task"] = active
        self._revision += 1
        self.journal.append(
            {
                "type": "task_began",
                "task_id": task_id,
                "command_id": command_id,
                "seq": len(self.journal) + 1,
            }
        )
        return deepcopy(active)

    def apply_transition(
        self,
        request: TaskTransitionRequest,
        *,
        agent: str = "cyber_risk_assessment",
    ) -> dict:
        active = self.context.get("active_task") or {}
        if request.transition == "begin":
            return self.begin_task(
                kind=request.kind or CYBER_RISK_KIND_SPEC.kind,
                phase=request.phase or "anchor",
                pending_ref=request.pending_ref or "",
                command_id=request.command_id or f"cmd_{uuid4().hex[:8]}",
                payload=request.payload_patch,
                agent=agent,
            )
        if request.transition == "abandon":
            tid = request.task_id or active.get("task_id")
            self.journal.append(
                {
                    "type": "task_abandoned",
                    "task_id": tid,
                    "command_id": request.command_id,
                    "seq": len(self.journal) + 1,
                }
            )
            self.context.pop("active_task", None)
            self._revision += 1
            return {}
        if request.transition == "complete":
            tid = request.task_id or active.get("task_id")
            self.journal.append(
                {
                    "type": "task_completed",
                    "task_id": tid,
                    "command_id": request.command_id,
                    "seq": len(self.journal) + 1,
                }
            )
            self.context.pop("active_task", None)
            self._revision += 1
            return {}
        # continue
        if not active:
            raise RuntimeError("continue without active_task")
        if request.task_id and request.task_id != active.get("task_id"):
            raise RuntimeError("task_id mismatch — refuse invent/replace")
        active["phase"] = request.phase or active.get("phase")
        if request.awaiting is not None:
            active["awaiting"] = request.awaiting
        if request.pending_ref:
            active["pending_ref"] = request.pending_ref
        if request.payload_patch:
            # Merge thin pins only
            payload = dict(active.get("payload") or {})
            payload.update(request.payload_patch)
            active["payload"] = payload
        self.context["active_task"] = active
        self._revision += 1
        self.journal.append(
            {
                "type": "task_progress",
                "task_id": active.get("task_id"),
                "command_id": request.command_id,
                "phase": active.get("phase"),
                "seq": len(self.journal) + 1,
            }
        )
        return deepcopy(active)


def run_dialogue() -> None:
    ledger = FakeLedger()
    agent = CyberRiskAssessmentAgent()
    conversation_id = "conv_demo"

    def turn(user: str) -> None:
        ctx = {
            "conversation_id": conversation_id,
            "active_task": deepcopy(ledger.context.get("active_task")),
        }
        result = agent.handle_turn(
            None,
            "tenant_demo",
            query=user,
            context=ctx,
            thread_id=conversation_id,
        )
        # Host sole writer
        ledger.apply_transition(result.transition)
        active = ledger.context.get("active_task")
        print(f"\nUSER: {user}")
        print(f"BOT:  {result.answer.get('answer')}")
        print(
            f"LEDGER: phase={active and active.get('phase')} "
            f"task_id={active and active.get('task_id')} "
            f"payload={active and active.get('payload')} "
            f"awaiting={active and active.get('awaiting')}"
        )
        # Domain IR not in projection
        pref = (active or {}).get("pending_ref") or result.pending_ref
        if pref:
            print(f"DOMAIN[{pref}]: {agent.domain.load_ir(pref)}")

    turn("start cyber assessment")
    turn("wf_demo_001")  # pin
    turn("continue discovery")
    turn("continue project")
    # VERIFY → human supervisor gate
    turn("looks ready")  # lands/stays verify awaiting human_approval
    turn("approve")  # supervisor
    turn("finish score")

    print("\n--- journal (COMPLETE ≠ ABANDON) ---")
    for row in ledger.journal:
        print(row)


if __name__ == "__main__":
    run_dialogue()
