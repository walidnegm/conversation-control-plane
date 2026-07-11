"""Host wrap — LangGraph runs *inside* one specialist turn (sketch).

LangGraph owns mid-turn graph state / checkpoints.
This SDK owns cross-turn conversation ownership on the shared chat thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional


@dataclass
class TaskTransitionRequest:
    transition: Literal["begin", "continue", "complete", "abandon", "none"]
    kind: Optional[str] = None
    phase: Optional[str] = None
    task_id: Optional[str] = None
    pending_ref: Optional[str] = None  # point at your domain / checkpoint store


class LangGraphSpecialist:
    """Wrap an existing compiled graph. No ledger imports here."""

    agent_id = "langgraph_specialist"

    def __init__(self, graph: Any) -> None:
        self.graph = graph  # compiled StateGraph or Runnable

    def handle_turn(self, query: str, *, context: dict, thread_id: str) -> dict:
        active = (context or {}).get("active_task") or {}
        task_id = active.get("task_id")
        # Prefer ledger pin / pending_ref for continuity — not ambient last_read alone.
        config = {"configurable": {"thread_id": thread_id}}
        # out = self.graph.invoke({"messages": [("user", query)]}, config=config)
        _ = (self.graph, query, config)
        out = {"messages": [], "phase": "active"}

        transition = TaskTransitionRequest(
            transition="continue" if task_id else "begin",
            kind="langgraph_task",
            phase=str(out.get("phase") or "active"),
            task_id=task_id,
            # Domain / graph checkpoint stays in LangGraph's store — thin ledger pin only:
            pending_ref=f"lg:{thread_id}",
        )
        return {
            "answer": {"answer": "LangGraph turn complete (stub).", "sources": []},
            "transition": transition,
        }


def handle_user_message(
    db: Any,
    graph: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    query: str,
    context: dict,
    worker_id: str = "worker-1",
) -> dict:
    # claim_turn(db, tenant_id, conversation_id, holder=worker_id)
    try:
        # plan = decide_turn(context, labels)  # may route here while kind is sticky
        agent = LangGraphSpecialist(graph)
        result = agent.handle_turn(query, context=context, thread_id=conversation_id)
        # apply_transition_request(db, ..., request=result["transition"])
        return result["answer"]
    finally:
        # release_turn_claim(...)
        pass
