"""Host wrap around an OpenAI-style chat/tool loop (sketch).

Your existing assistant / chat.completions loop stays intact.
Only the *host* maps structured tool output → TaskTransitionRequest.
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
    payload_patch: Optional[dict] = None


def run_openai_style_turn(
    client: Any,
    *,
    messages: list[dict],
    tools: list[dict],
    active_task: Optional[dict] = None,
) -> tuple[str, TaskTransitionRequest]:
    """Illustrative — replace client.chat.completions with your SDK call."""
    # response = client.chat.completions.create(model=..., messages=messages, tools=tools)
    # Parse tool call e.g. complete_task / update_phase from the model.
    # Below: deterministic stub for docs / unit demos.
    _ = (client, messages, tools)
    task_id = (active_task or {}).get("task_id")
    text = "Working on your request…"
    transition = TaskTransitionRequest(
        transition="continue" if task_id else "begin",
        kind="assistant_task",
        phase="in_progress",
        task_id=task_id,
    )
    return text, transition


def handle_user_message(
    db: Any,
    client: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    user_text: str,
    context: dict,
    worker_id: str = "worker-1",
) -> dict:
    # claim_turn(...)
    try:
        # plan = decide_turn(context, labels)
        messages = [{"role": "user", "content": user_text}]
        answer, transition = run_openai_style_turn(
            client,
            messages=messages,
            tools=[],  # your tool schemas
            active_task=(context or {}).get("active_task"),
        )
        # apply_transition_request(db, ..., request=transition)
        return {"answer": answer, "transition": transition.transition}
    finally:
        # release_turn_claim(...)
        pass
