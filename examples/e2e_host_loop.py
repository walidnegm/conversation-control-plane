"""End-to-end host loop demo — real package imports + FakeOwnershipLedger.

Does **not** require LangGraph/OpenAI. Exercises:
  - ``conversation_control_plane`` import surface
  - single-writer convention (``strip_control_keys``)
  - COMPLETE vs ABANDON as distinct journal event types
  - thin host: claim → decide-shaped plan → apply → release (in-memory)

Run from package root after ``pip install -e .``:

  python examples/e2e_host_loop.py
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional
from uuid import uuid4

from conversation_control_plane import (
    TaskTransition,
    TurnPlan,
    strip_control_keys,
)


class FakeOwnershipLedger:
    """In-memory projection + journal — portable teaching ledger."""

    def __init__(self) -> None:
        self.context: dict[str, Any] = {}
        self.journal: list[dict[str, Any]] = []
        self._revision = 0
        self._claim: Optional[dict[str, Any]] = None

    def claim(self, holder: str) -> bool:
        if self._claim and self._claim.get("holder") != holder:
            return False
        self._claim = {"holder": holder}
        return True

    def release(self, holder: str) -> None:
        if self._claim and self._claim.get("holder") == holder:
            self._claim = None

    def begin(
        self,
        *,
        kind: str,
        phase: str,
        command_id: str,
        agent: str = "demo",
        pending_ref: str = "",
    ) -> dict[str, Any]:
        task_id = f"task_{uuid4().hex[:12]}"
        active = {
            "task_id": task_id,
            "kind": kind,
            "phase": phase,
            "agent": agent,
            "pending_ref": pending_ref,
            "payload": {},
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

    def apply_complete(self, *, command_id: str) -> None:
        active = self.context.get("active_task") or {}
        self.journal.append(
            {
                "type": "task_completed",
                "task_id": active.get("task_id"),
                "command_id": command_id,
                "seq": len(self.journal) + 1,
            }
        )
        self.context["active_task"] = None
        self._revision += 1

    def apply_abandon(self, *, command_id: str) -> None:
        active = self.context.get("active_task") or {}
        self.journal.append(
            {
                "type": "task_abandoned",
                "task_id": active.get("task_id"),
                "command_id": command_id,
                "seq": len(self.journal) + 1,
            }
        )
        self.context["active_task"] = None
        self._revision += 1


def decide_shaped(
    *,
    query: str,
    context: dict[str, Any],
) -> TurnPlan:
    """Minimal decide shape — not the full monorepo decide_turn DB path.

    Exact reset → command/abandon; else continue active or fresh.
    """
    q = (query or "").strip().lower()
    active = context.get("active_task")
    if q in ("reset", "cancel this", "forget this", "scrap this"):
        return TurnPlan(agent="bot0", mode="command", reason="Reset command — abandon")
    if isinstance(active, dict) and active:
        return TurnPlan(
            agent=str(active.get("agent") or "bot0"),
            mode="active_task",
            reason="continue active",
        )
    return TurnPlan(agent="bot0", mode="fresh", reason="no active task")


def run_demo() -> None:
    led = FakeOwnershipLedger()
    worker = "worker-1"
    assert led.claim(worker)

    # Specialist-shaped updates must not smuggle control keys.
    agent_updates = strip_control_keys(
        {"active_task": {"evil": True}, "note": "domain only"}
    )
    assert "active_task" not in agent_updates
    assert agent_updates["note"] == "domain only"

    led.begin(kind="demo", phase="open", command_id="cmd_begin")
    plan = decide_shaped(query="continue", context=led.context)
    assert plan.mode == "active_task"

    led.apply_complete(command_id="cmd_done")
    assert led.journal[-1]["type"] == "task_completed"
    assert TaskTransition.COMPLETE.value == "complete"
    assert TaskTransition.ABANDON.value == "abandon"
    assert TaskTransition.COMPLETE != TaskTransition.ABANDON

    led.begin(kind="demo", phase="open", command_id="cmd_begin2")
    plan2 = decide_shaped(query="reset", context=led.context)
    assert "abandon" in (plan2.reason or "").lower()
    led.apply_abandon(command_id="cmd_abandon")
    assert led.journal[-1]["type"] == "task_abandoned"

    led.release(worker)
    print("e2e_host_loop OK")
    print("  journal types:", [e["type"] for e in led.journal])
    print("  complete ≠ abandon:", TaskTransition.COMPLETE != TaskTransition.ABANDON)


if __name__ == "__main__":
    run_demo()
