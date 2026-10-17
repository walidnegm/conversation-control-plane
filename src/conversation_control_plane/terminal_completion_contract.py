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

#: **B-10.** Dispatches that DELIVER a product-concept answer and therefore end
#: their unit of work.
#:
#: Measured 2026-09-15 across the local ledger: **99 `concept_thread` tasks
#: began, 24 were superseded by a later turn, and exactly ONE completed.** The
#: cause was a registration gap rather than a broken handler —
#: `kind_spec` declares `terminal=frozenset({"complete"})` for
#: `concept_thread`, and no path emitted it. `ANSWER_DELIVERED` existed but was
#: declared as `advisor_graph.py`'s, a different owner.
#:
#: What the survivors cost: `package_drafting_orientation` claims any turn with
#: an active_task, so one abandoned concept task hands every LATER question in
#: that conversation to the where-you-are coach and the concept gate never
#: runs. conv_12a87447 is the worked case — two turns asking how to build a
#: workflow answered with "Where you are: questions about the product" and
#: prose, `hops=4`, `path=unlabeled`, neither the binder nor the composer
#: called at all.
CONCEPT_ANSWER_DISPATCHES: frozenset[str] = frozenset({
    "concept_gate",
    "product_concept",
})


def delivered_concept_answer(result: Mapping[str, Any] | None) -> bool:
    """True when this turn DELIVERED a product-concept answer.

    Read off the routing the concept sites already stamp, not off the prose:
    `_code_owned_dispatch_routing(dispatch="concept_gate", ...)` is the common
    factory behind every one of them, so this needs no edit at six return
    sites and cannot drift from what they actually emit.

    An EMPTY answer is not a delivery. The concept path returns
    `{"answer": "", "blocks": []}` when packaging declines, and completing a
    task on a refusal would close work the user never got.
    """
    if not isinstance(result, Mapping):
        return False
    routing = result.get("routing")
    if not isinstance(routing, Mapping):
        return False
    # TWO SPELLINGS, BOTH REAL. `_code_owned_dispatch_routing(dispatch=…)`
    # takes a `dispatch` argument but emits it as `layer="code_dispatch:<name>"`
    # — the `dispatch` key only survives on the internal turn result, not on
    # what persistence receives. Reading only the key cost a live re-test:
    # the card was delivered, the predicate said no, and the task stayed open.
    dispatch = str(routing.get("dispatch") or "").strip().lower()
    if not dispatch:
        layer = str(routing.get("layer") or "").strip().lower()
        if layer.startswith("code_dispatch:"):
            dispatch = layer.split(":", 1)[1].strip()
    if dispatch not in CONCEPT_ANSWER_DISPATCHES:
        return False
    answer = result.get("answer")
    if not isinstance(answer, Mapping):
        return False
    spoken = str(answer.get("answer") or "").strip()
    blocks = answer.get("blocks")
    return bool(spoken) or bool(isinstance(blocks, (list, tuple)) and blocks)


class TerminalKind(str, Enum):
    """The four outcomes the epic requires to close their task."""

    WORKFLOW_COMMIT = "workflow_commit_success"
    PROJECT_CREATE = "project_create"
    ANSWER_DELIVERED = "answer_delivered"
    BUILD_FAILURE_RECOVERY = "build_failure_recovery"
    #: B-10, 2026-09-15. A delivered glossary/product-concept answer. The
    #: fifth outcome, and the one nobody had registered.
    CONCEPT_ANSWER = "concept_answer_delivered"
    #: #1e S1, 2026-09-16. A cost profile published to the simulator. The
    #: sixth, found the same way as the fifth: 21 tasks began, 0 completed.
    COST_PROFILE_PUBLISHED = "cost_profile_published"


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
        TerminalKind.CONCEPT_ANSWER,
        "api/services/conversation_control/terminal_completion_contract.py",
        "complete",
        "B-10: a concept_gate / product_concept dispatch that delivered a "
        "non-empty answer. Recognised HERE rather than emitted at the six "
        "concept return sites in bot0.py — they share one routing factory, so "
        "one reading cannot drift from six copies. 99 began / 1 completed "
        "before this row existed.",
    ),
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
        TerminalKind.COST_PROFILE_PUBLISHED,
        "api/services/agent_cost_pricing_pipeline.py",
        "complete",
        "#1e S1: publish_profile_to_sim returned status=published, so the "
        "pricing task is done. 21 began / 0 completed before this row. The "
        "site already moved the task to its own declared terminal phase "
        "(`published`) and stopped there \u2014 KindSpec.terminal_phases is "
        "declared on all 15 kinds and read by nothing, so reaching a terminal "
        "phase does not end a task.",
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
    # B-10: a delivered concept answer ends its unit of work. Last, so an
    # explicitly declared NON-terminal transition on a concept turn still
    # wins — a thread that says it is continuing is continuing.
    if delivered_concept_answer(result):
        return "complete"
    return None


def is_terminal(
    result: Mapping[str, Any] | None,
    context_updates: Mapping[str, Any] | None = None,
) -> bool:
    """Boolean form of :func:`terminal_outcome`."""
    return terminal_outcome(result, context_updates) is not None


# ---------------------------------------------------------------------------
# What FOLLOWS a completion (10-17, Walid: "make the ledger rule fix — we have
# to continue to harden our control plane").
#
# The half above says what ENDS a unit of work. This half says what comes
# AFTER it: every ledger kind declares either the continuum edges its
# completion arms (an offer + the pin that lets "yes please" advance it —
# `product_continuum_next_step_contract.CONTINUUM_EDGE_TABLE`) or, in words,
# why nothing follows. "End" is a valid declaration; silence is not.
#
# Why: the 10-17 audit found completions that offered nothing although the
# product had a next step — a saved work system already simulation-ready,
# value metrics saved on their own (conv_f5aea25d), the cost save that
# confirms in chat, a published cost profile — and one edge marked sealed
# whose arm had no production caller. Each was one site that forgot; nothing
# could see it. The table makes the decision once per kind, the ratchet
# (`test_every_completion_says_what_follows`) holds it, and the completion
# sinks report a completion of an edge-declaring kind that armed no next step.
#
# Not determinism: code records only the offer it just made. Whether a reply
# means "yes" stays exact chip grammar or the router's own judgement.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WhatFollows:
    """What follows one kind's completion: continuum edges, or a stated end."""

    #: Edge ids in CONTINUUM_EDGE_TABLE this kind's completion may arm.
    edges: tuple[str, ...] = ()
    #: Why nothing follows, in words — required when ``edges`` is empty.
    end: str = ""


KIND_WHAT_FOLLOWS: dict[str, WhatFollows] = {
    "workflow_build": WhatFollows(edges=("workflow_save_to_outcome_value", "workflow_save_to_recommend")),
    "outcome_value_setup": WhatFollows(edges=("ovs_saved_to_create_project",)),
    "cost_out": WhatFollows(edges=("cost_save_to_recommend",)),
    "agent_cost_pricing": WhatFollows(edges=("cost_save_to_recommend",)),
    "input_state_setup": WhatFollows(edges=("iss_done_to_goal_seek", "rec20_edit_inputs_to_iss_and_back")),
    "project_workspace": WhatFollows(edges=("project_ready_to_goal_seek",)),
    "cyber_risk_assessment": WhatFollows(end=(
        "Walid 10-17: nothing comes next after an assessment is saved — the "
        "report card holds it."
    )),
    "recommendation_setup": WhatFollows(end=(
        "Walid 10-17: no more offers after the result — the run's results "
        "card links to the full results."
    )),
    "engagement_pack_plan": WhatFollows(end=(
        "The end-of-plan ceremony is the end: it names its destinations "
        "(designer, project, all workflows) as links."
    )),
    "drafting": WhatFollows(end=(
        "Drafting ends by beginning workflow_build (referential_turn); the "
        "build card is what follows, not an offer."
    )),
    "concept_thread": WhatFollows(end=(
        "A delivered answer ends it. Where the answer names a simulation "
        "pattern and a work system is pinned, glossary_pattern_to_sim_run "
        "arms a run — an answer, not a completion edge."
    )),
    "scorecard_interrogate": WhatFollows(end=(
        "A read stream: it ends when another task supersedes it, with that "
        "task's own card."
    )),
    "risk_catalog_learning": WhatFollows(end=(
        "A browse stream: it ends when another task supersedes it."
    )),
    "realization_intake": WhatFollows(end=(
        "The generated package is the result; its card links to the "
        "Realization Studio. Nothing is offered in chat after it."
    )),
    "pattern_midflight": WhatFollows(end=(
        "Results are the end; the card says follow-ups are free text or "
        "'stop'."
    )),
}


def completion_without_next(
    kind: str | None,
    result: Mapping[str, Any] | None,
    context_updates: Mapping[str, Any] | None = None,
) -> Optional[str]:
    """A finding when a kind that declares edges completed with no next step
    armed, else None. Read by the completion sinks; it reports, never blocks."""
    follows = KIND_WHAT_FOLLOWS.get(str(kind or ""))
    if follows is None or not follows.edges:
        return None
    if terminal_outcome(result, context_updates) != "complete":
        return None
    cus = [context_updates] if isinstance(context_updates, Mapping) else []
    if isinstance(result, Mapping) and isinstance(result.get("context_updates"), Mapping):
        cus.append(result["context_updates"])
    for cu in cus:
        # An offer was pinned, or the turn began the next unit of work.
        if cu.get("pending_continuum_next_step") or cu.get("active_task"):
            return None
    return f"{kind} completed without arming any of {', '.join(follows.edges)}"


def report_completion_without_next(
    kind: str | None,
    result: Mapping[str, Any] | None,
    context_updates: Mapping[str, Any] | None = None,
    *,
    context: Mapping[str, Any] | None = None,
    tenant_id: str | None = None,
    conversation_id: str | None = None,
) -> Optional[str]:
    """The sinks' one call: the finding, as a platform event (warning).

    ``kind`` None: the result's own ``kind``, else the open task's in
    ``context`` — the unit of work this turn completed."""
    if not kind:
        kind = (result or {}).get("kind") if isinstance(result, Mapping) else None
    if not kind and isinstance(context, Mapping) and isinstance(context.get("active_task"), Mapping):
        kind = context["active_task"].get("kind")
    finding = completion_without_next(kind, result, context_updates)
    if not finding:
        return None
    try:
        from api.services.event_logger import log_platform_event_bg

        log_platform_event_bg(
            "continuum_unarmed_completion", "warning", finding,
            details={"kind": kind, "conversation_id": conversation_id},
            tenant_id=tenant_id,
        )
    except Exception:  # noqa: BLE001 — a report never breaks the turn
        pass
    return finding


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
