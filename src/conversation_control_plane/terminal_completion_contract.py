"""I3 — a terminal outcome closes its ledger task, and nothing else does.

**The law:** exactly one predicate decides whether an agent turn ended the unit
of work it was doing. Every sink that writes ``complete_task`` reads that
predicate; no sink re-derives it from the result dict on its own.

## Why this exists

`conv_b899a066` (the coherence epic's anchor) is two faults sharing one cause.
At msg 23 the builder committed ``wf_f426d922`` and the ledger kept an open
``active_task`` (workflow_builder, ``awaiting: null``); five messages later
"How can we start **simulating** on the keynote workflow?" was captured by that
stale task and answered with a *new-build interview*. A committed build that
does not close its task turns every later message into the builder's property.

The opposite failure is `conv_9c5f24a6`: an idle **reorientation** card carries
``{"agent_type": None}`` in its ``context_updates`` — a release of the response
agent, not a completion of the work — and the worker read that as terminal and
wrote ``task_completed`` for a task that was still open. The worker was fixed
in place with a local ``_is_reorient`` guard. The two other sinks never got it.

So the rule has two halves and both are load-bearing:

* a real terminal (commit, project created, delivered answer, cancel/recovery)
  **must** close the task — otherwise `conv_b899a066`;
* an idle/reorient/continue turn **must not**, however its context_updates look
  — otherwise `conv_9c5f24a6`.

## The four terminal paths (epic §5, slice S1)

``TERMINAL_PATHS`` names them. Each *emits* a terminal signal at its own site;
this module does not change what they emit, it fixes what happens next.

## The three sinks

``COMPLETION_SINKS`` names every place that turns a signal into a ledger write.
Before this contract each carried its own copy of the condition and the copies
had already diverged: the worker excluded reorientation and accepted
``workflow_created``; ``bot0._finalize_result`` did neither; the control-plane
adapter accepted ``workflow_created`` but not an explicit agent release. One
law, three readings — which is the same shape as the bug it was meant to stop.

Consumers: ``bot0._finalize_result`` · ``workers.handlers.workflow_builder_turn``
· ``conversation_control.contract`` adapter · ratchet
``test_s1_terminal_completion``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

#: The two outcomes that close a task. ``complete`` and ``abandon`` share the
#: projection clear and differ only in journal event identity (``task_completed``
#: vs ``task_abandoned``) — see ``ledger.complete_task``.
TERMINAL_SIGNALS: frozenset[str] = frozenset({"complete", "abandon"})

#: Declared transitions that are explicitly NOT terminal. ``reorient`` is the
#: idle card; ``continue`` advances the same task (``update_phase``).
NON_TERMINAL_SIGNALS: frozenset[str] = frozenset({"reorient", "continue", "begin"})

#: A block type whose presence means the turn rendered the idle/staleness card.
REORIENTATION_BLOCK_TYPE = "session_reorientation"


class TerminalKind(str, Enum):
    """The four outcomes the epic requires to close their task."""

    WORKFLOW_COMMIT = "workflow_commit_success"
    PROJECT_CREATE = "project_create"
    ANSWER_DELIVERED = "answer_delivered"
    BUILD_FAILURE_RECOVERY = "build_failure_recovery"


@dataclass(frozen=True)
class TerminalPath:
    """One production site that ends a unit of work."""

    kind: TerminalKind
    module: str
    #: The signal that site emits, as it appears in the agent turn result.
    signal: str
    note: str


#: **The inventory.** Traced 2026-09-05 for S1-R1: every one of the four spec'd
#: paths does emit a terminal signal at its own site. The slice's finding was
#: never a missing emitter — it was the sinks disagreeing about what an emitter
#: means. Add a row when a new terminal outcome ships.
TERMINAL_PATHS: tuple[TerminalPath, ...] = (
    TerminalPath(
        TerminalKind.WORKFLOW_COMMIT,
        "api/services/bot0.py",
        "complete",
        "workflow_created → _workflow_builder_context_updates(agent_type=None) "
        "+ transition=complete, then release_post_commit_builder",
    ),
    TerminalPath(
        TerminalKind.WORKFLOW_COMMIT,
        "api/services/conversation_control/authoring_gate_turn.py",
        "complete",
        "_saved_status_reply: workflow_created=True + transition=complete",
    ),
    TerminalPath(
        TerminalKind.PROJECT_CREATE,
        "api/services/recommender_plan_executor.py",
        "complete",
        "create_project_from_workflow ctx_updates carry transition=complete — "
        "project create is terminal for the planning task",
    ),
    TerminalPath(
        TerminalKind.ANSWER_DELIVERED,
        "api/services/advisor_graph.py",
        "complete",
        "advisor phase DONE / create_flow_state=simulated → transition=complete, "
        "awaiting=None: the bounded advisor task delivered its answer",
    ),
    TerminalPath(
        TerminalKind.BUILD_FAILURE_RECOVERY,
        "agent/workflow_builder/agent.py",
        "abandon",
        "draft discarded / builder cancelled after a blocked or failed commit — "
        "abandon, so free text is not stuck on a hollow ir_review (conv_74fdf662)",
    ),
)


@dataclass(frozen=True)
class CompletionSink:
    """One place that converts a terminal signal into a ledger write."""

    name: str
    module: str
    note: str


#: Every sink that may call ``complete_task`` off the back of an agent turn
#: result. Each must read this module's predicate rather than re-deriving it.
COMPLETION_SINKS: tuple[CompletionSink, ...] = (
    CompletionSink(
        "_finalize_result",
        "api/services/bot0.py",
        "the synchronous chat() sink — ~28 call sites feed it",
    ),
    CompletionSink(
        "workflow_builder_turn",
        "api/workers/handlers/workflow_builder_turn.py",
        "the async builder sink; a heavy build commits here, not in chat()",
    ),
    CompletionSink(
        "handle_turn",
        "api/services/conversation_control/contract.py",
        "the control-plane adapter's AgentTurnResult mapping",
    ),
)

SINK_MODULES: tuple[str, ...] = tuple(s.module for s in COMPLETION_SINKS)


def _blocks_of(result: Mapping[str, Any] | None) -> list:
    """Content blocks, wherever this result shape carries them."""
    if not isinstance(result, Mapping):
        return []
    blocks = result.get("blocks")
    if not isinstance(blocks, list):
        answer = result.get("answer")
        blocks = answer.get("blocks") if isinstance(answer, Mapping) else None
    return blocks if isinstance(blocks, list) else []


def declared_transition(
    result: Mapping[str, Any] | None,
    context_updates: Mapping[str, Any] | None = None,
) -> str:
    """The transition this turn declared, normalised ('' when it declared none)."""
    raw = None
    if isinstance(result, Mapping):
        raw = result.get("transition")
    if not raw and isinstance(context_updates, Mapping):
        raw = context_updates.get("transition")
    if not raw and isinstance(result, Mapping):
        cu = result.get("context_updates")
        if isinstance(cu, Mapping):
            raw = cu.get("transition")
    return str(raw or "").strip().lower()


def explicit_agent_release(context_updates: Mapping[str, Any] | None) -> bool:
    """``{"agent_type": None}`` was written *explicitly* by this turn.

    T2 (turn-integrity epic): the key must be PRESENT and falsy. Absent is not a
    release — before T2 an absent key fell through to ``response_agent_type``
    and re-began the task the turn had just finished.
    """
    return (
        isinstance(context_updates, Mapping)
        and "agent_type" in context_updates
        and not context_updates.get("agent_type")
    )


def is_reorientation(
    result: Mapping[str, Any] | None,
    context_updates: Mapping[str, Any] | None = None,
) -> bool:
    """This turn showed the idle / session-staleness card, not an outcome.

    `conv_9c5f24a6`: the reorient card releases ``agent_type`` and declares no
    transition. That is a release of the *responder*, never a completion of the
    *work*, and reading it as terminal closes a task the user is still in.
    """
    if isinstance(context_updates, Mapping) and context_updates.get(
        "session_reorientation_pending"
    ):
        return True
    if isinstance(result, Mapping):
        cu = result.get("context_updates")
        if isinstance(cu, Mapping) and cu.get("session_reorientation_pending"):
            return True
    if declared_transition(result, context_updates) == "reorient":
        return True
    return any(
        isinstance(b, Mapping) and b.get("type") == REORIENTATION_BLOCK_TYPE
        for b in _blocks_of(result)
    )


def terminal_outcome(
    result: Mapping[str, Any] | None,
    context_updates: Mapping[str, Any] | None = None,
) -> Optional[str]:
    """``"complete"`` / ``"abandon"`` when this turn closes its task, else None.

    The single reading of I3. Terminal when the turn *declares* a terminal
    transition, *committed a workflow*, or *explicitly released the agent* — and
    never when it merely reoriented or continued.
    """
    if is_reorientation(result, context_updates):
        return None

    transition = declared_transition(result, context_updates)
    if transition in TERMINAL_SIGNALS:
        return transition
    if transition in NON_TERMINAL_SIGNALS:
        return None

    if isinstance(result, Mapping) and result.get("workflow_created"):
        return "complete"
    if explicit_agent_release(context_updates):
        return "complete"
    return None


def is_terminal(
    result: Mapping[str, Any] | None,
    context_updates: Mapping[str, Any] | None = None,
) -> bool:
    """Boolean form of :func:`terminal_outcome`."""
    return terminal_outcome(result, context_updates) is not None


def crawl_completion_sinks(root: Any = None) -> tuple[str, ...]:
    """Sink modules that do not read this contract — a finding per module.

    Cheap by design: a sink either imports the predicate or it is carrying its
    own copy of the rule, which is the defect this module exists to close.
    """
    from pathlib import Path

    base = Path(root) if root else Path(__file__).resolve().parents[3]
    findings: list[str] = []
    for sink in COMPLETION_SINKS:
        path = base / sink.module
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            findings.append(f"{sink.module}: unreadable")
            continue
        if "terminal_outcome" not in src:
            findings.append(
                f"{sink.module}::{sink.name} re-derives terminal completion "
                "instead of reading terminal_completion_contract"
            )
    return tuple(findings)
