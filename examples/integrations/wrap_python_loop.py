"""Minimal host wrap — raw Python specialist (sketch).

~10-line idea: claim → decide → handle_turn → apply transition → release.
Replace Fake* with your Postgres-backed ledger + decide_turn port.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional


# --- thinned types (mirror public contract; use package types in production) ---

@dataclass
class TaskTransitionRequest:
    transition: Literal["begin", "continue", "complete", "abandon", "none"]
    kind: Optional[str] = None
    phase: Optional[str] = None
    task_id: Optional[str] = None
    command_id: Optional[str] = None


@dataclass
class AgentTurnResult:
    answer: dict
    transition: TaskTransitionRequest


class EchoAgent:
    """Stand-in for your existing agent. No ledger imports."""

    agent_id = "echo"

    def handle_turn(self, query: str, *, context: dict) -> AgentTurnResult:
        active = (context or {}).get("active_task") or {}
        task_id = active.get("task_id")
        return AgentTurnResult(
            answer={"answer": f"Echo: {query}"},
            transition=TaskTransitionRequest(
                transition="continue" if task_id else "begin",
                kind="echo_task",
                phase="active",
                task_id=task_id,
            ),
        )


# --- host (sole writer) — sketch of your chat entrypoint ---

def handle_user_message(
    db: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    query: str,
    context: dict,
    worker_id: str = "worker-1",
) -> dict:
    # claim_turn(db, tenant_id, conversation_id, holder=worker_id)
    try:
        # plan = decide_turn(context, router_labels)  # → which agent_id
        agent = EchoAgent()
        result = agent.handle_turn(query, context=context)
        # apply_transition_request(db, tenant_id, conversation_id,
        #     agent=agent.agent_id, request=result.transition)
        return result.answer
    finally:
        # release_turn_claim(db, tenant_id, conversation_id, holder=worker_id)
        pass


if __name__ == "__main__":
    print(handle_user_message(None, tenant_id="t", conversation_id="c", query="hi", context={}))
