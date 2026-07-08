"""Executable contracts for the conversation control plane.

These types are the single source of truth for what a conversational agent must provide
and what the ledger / decide_turn exchange looks like.

Matches the shapes in docs/epics/cross-agent-conversation-orchestration_exploration.md
(with review-driven clarifications for Stage-1 shim compatibility and async handoff).

Sibling SDK modules (typed envelopes — import from their modules, not inlined here):

- ``turn_timeout`` — inline POST /chat + SSE turn wall-clock cap + ``chat_turn_timed_out`` error code.
- ``session_staleness`` — idle-thread reorientation gate before acting on stale context.

Official name: Conversation Control Plane SDK — reference implementation by Bot0.ai
(``sdk_identity.py``). Prose integration contract (not standalone package yet):
``docs/epics/conversation-control-plane-sdk.md`` — §0 pillars, §0.0 naming, §1 bootstrap, §2.1 coding-agent
guardrails (distilled from ``AGENTS.md``), §3.1 hard questions, §9.1 integration patterns (Bot0 catalog: agent-architecture §1.1), §11.1 routing trace,
§15 shipped checklist. Full monorepo playbook: ``AGENTS.md``. Modules: ``handoff_guard``, ``failure_modes``,
``render_state``, ``agent_base``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Optional, Protocol

# -----------------------------------------------------------------------------
# Task lifecycle (returned by agents; control plane maps to ledger writes)
# -----------------------------------------------------------------------------

class TaskTransition(Enum):
    """Declarative transition reported by a conversational agent on each turn.

    Agents MUST return one of these. They MUST NOT write control keys
    (agent_type, pending_switch, active_task, suspended_tasks, advisor_active, etc.)
    directly into context_updates. Control keys here are a contract violation.
    """
    BEGIN = "begin"          # Agent is starting a new task (provide phase + pending_ref)
    CONTINUE = "continue"    # Same task continues (possibly new phase/awaiting)
    COMPLETE = "complete"    # Task finished successfully — control plane must release ALL stickiness
    ABANDON = "abandon"      # User explicitly bailed or reset — release ALL stickiness
    NONE = "none"            # Turn had no task semantics (pure Q&A / bot0). Never sticky.


# The control-plane keys agents MUST NOT write (epic §9.2). The control plane is
# their sole writer; an agent's context_updates is domain-only. Used by the
# domain-only guard below and by the authority-matrix ratchet.
CONTROL_KEYS = frozenset({
    "agent_type",
    "pending_switch",
    "pending_question",
    "active_task",
    "suspended_tasks",
    "advisor_active",
    "pipeline_step",
    "create_flow_state",
    # Turn-serialization claim (T1, turn-integrity epic). Written only by
    # ledger.claim_turn/release_turn on their own sessions; an agent must
    # never be able to steal or drop another turn's claim via context_updates.
    "_turn_claim",
    # Last-completed-turn marker (T8) — ledger.mark_turn_completed only.
    "_last_completed_turn",
    # Monotonic control-coherence counter (epic §8.2) — ledger-bumped only.
    "_control_revision",
})


def strip_control_keys(context_updates: Optional[dict]) -> dict:
    """Return a copy of an agent's ``context_updates`` with any control keys
    removed, so control state cannot leak from an agent result (epic §9.2).

    Domain keys (project_id, workflow_id, scenario_id, and other durable
    user-facing references) pass through untouched. This is the single chokepoint
    that makes "agents emit domain-only updates" enforceable rather than
    aspirational."""
    if not context_updates:
        return {}
    return {k: v for k, v in context_updates.items() if k not in CONTROL_KEYS}


# -----------------------------------------------------------------------------
# Agent contract (what every conversational agent must implement)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentTurnResult:
    """Return value from a conversational agent's handle_turn (or equivalent).

    answer: The normal Bot0ChatOut-shaped payload (blocks, sources, action, etc.).
            Unchanged from pre-substrate behavior.
    transition: The code-owned lifecycle signal (see TaskTransition).
    phase: Current or new phase name (routing-safe, e.g. "awaiting_name").
    awaiting: What the agent is now waiting for (e.g. "workflow_name", "switch_confirmation").
    pending_ref: Stable reference to the agent's own durable state
                 (e.g. "pending_workflow:conv_abc123", "advisor_session:conv_abc123").
                 The ledger stores only the ref; the agent owns the payload.
    context_updates: DOMAIN-ONLY keys (project_id, workflow_id, scenario_id, etc.).
                     MUST NOT contain control keys. The control plane will add
                     ledger-managed keys after processing the transition.
    """
    answer: dict
    transition: TaskTransition
    phase: Optional[str] = None
    awaiting: Optional[str] = None
    pending_ref: Optional[str] = None
    context_updates: dict = field(default_factory=dict)


class ConversationalAgent(Protocol):
    """Uniform interface that every conversational (heavy) agent must satisfy
    so the control plane can coordinate without knowing private shapes.

    agent_id: Stable string used in the ledger and TurnPlan (e.g. "workflow_builder").
    task_kind: "bounded" (has natural terminal state, strong capture) or
               "unbounded" (free consultation, weak sticky + short TTL).
    """
    agent_id: str
    task_kind: Literal["bounded", "unbounded"]

    def handle_turn(
        self,
        db: Any,                    # SQLAlchemy Session (kept as Any to avoid import cycles)
        tenant_id: str,
        *,
        query: str,
        history: Optional[list[tuple[str, str]]] = None,
        context: Optional[dict] = None,
        thread_id: Optional[str] = None,
    ) -> AgentTurnResult:
        """Execute one turn. Return declarative result + domain-only updates."""
        ...

    def classify_phase(
        self,
        db: Any,
        tenant_id: str,
        *,
        conversation_id: str,
    ) -> Optional[str]:
        """Return the current phase name from the agent's own durable state, or None if idle.

        Used by the ledger / decide_turn to decide "are we mid-task?" without the
        router re-classifying text. For builder this wraps classify_agent_state over
        the pending row. For advisor it will read the create-flow state or session.
        """
        ...

    def resolve_pending(
        self,
        db: Any,
        tenant_id: str,
        pending_ref: str,
    ) -> "PendingResolution":
        """Given a pending_ref the ledger previously stored, return whether the
        underlying agent-owned state still exists and is usable for resume.

        status:
          "exists"  — state is present and fresh enough
          "stale"   — state exists but is past the agent's own TTL / idle horizon
          "missing" — state was promoted, deleted, or expired

        summary: Small, routing-safe human string (e.g. "awaiting name for intake workflow").
                 Never leaks full task details.
        """
        ...


@dataclass(frozen=True)
class PendingResolution:
    status: Literal["exists", "stale", "missing"]
    summary: Optional[str] = None


# -----------------------------------------------------------------------------
# Control-plane exchange types (TurnPlan is the output of decide_turn)
# -----------------------------------------------------------------------------

WORKFLOW_BUILD_KIND = "workflow_build"
WORKFLOW_AUTHORING_AGENTS = frozenset({"workflow_builder", "workflow_editor"})


def ledger_kind_for_agent(agent: str | None) -> str | None:
    """Typed ``active_task.kind`` for agents that own a ledger-tracked sub-flow."""
    aid = (agent or "").strip()
    if aid in WORKFLOW_AUTHORING_AGENTS:
        return WORKFLOW_BUILD_KIND
    return None


@dataclass(frozen=True)
class ActiveTask:
    """Coarse view of the foreground task (what the ledger stores for routing)."""
    agent: str                    # e.g. "workflow_builder"
    phase: str
    awaiting: Optional[str] = None
    pending_ref: Optional[str] = None
    started_at: Optional[str] = None
    # Ledger-tracked-task tier (agent-architecture §4b): `kind` names a sub-flow the
    # agent owns (e.g. "drafting"); `payload` is its conversation-scoped state (e.g.
    # the current draft) — carried in the LEDGER, not ad-hoc context flags.
    kind: Optional[str] = None
    payload: Optional[dict] = None


@dataclass(frozen=True)
class PendingSwitch:
    """Server-authored pending agent-switch confirmation state."""
    from_agent: str
    to_agent: str
    original_message: str
    source_message_id: Optional[str] = None
    requested_at: Optional[str] = None
    decision_id: Optional[str] = None
    control_revision: int = 0
    task_text: Optional[str] = None


class ControlAct(str, Enum):
    """Closed control-plane act set for a user turn."""

    NONE = "none"
    HANDOFF = "handoff"
    STAY = "stay"
    RESUME = "resume"
    ABANDON = "abandon"
    NEW_CHAT = "new_chat"


@dataclass(frozen=True)
class ConversationTurnEnvelope:
    """Validated separation between conversation control and domain work.

    ``task_text`` is the only text a domain agent may receive after a handoff.
    A null value means the turn is control-only and MUST be consumed without
    invoking a domain executor.
    """

    schema_version: int
    source_message_id: Optional[str]
    control_act: ControlAct
    target_agent: Optional[str]
    task_text: Optional[str]
    decision_id: str
    control_revision: int
    confidence: float = 0.0
    source: str = "classifier"


@dataclass(frozen=True)
class ActiveAgentProjection:
    """Server-owned projection of who owns the conversation's next turn."""

    active_agent_type: str
    response_agent_type: Optional[str]
    control_revision: int
    pending_target_agent_type: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "active_agent_type": self.active_agent_type,
            "response_agent_type": self.response_agent_type,
            "control_revision": self.control_revision,
            "pending_target_agent_type": self.pending_target_agent_type,
        }


@dataclass(frozen=True)
class TurnPlan:
    """The single decision the control plane returns for a turn.

    This is what replaces the ad-hoc _route + sticky checks in bot0.py.
    """
    agent: str                    # who should handle this turn
    mode: str                     # "active_task" | "resume" | "detour" | "switch_confirm"
                                  # | "fresh" | "command" | "discovery"
    task: Optional[ActiveTask] = None
    reason: str = ""              # Observability trace (why this decision)
    discovery_kind: str = "none"  # S2 coherence epic


@dataclass(frozen=True)
class DecisionEnvelope:
    """The authoritative control decision for one user turn, carried across the
    queue boundary so the worker honors it instead of minting a second one
    (epic §8 — Decision Envelope & Worker Validation Contract).

    Lightweight + JSON-serializable: it embeds the resolved ``TurnPlan`` plus the
    source-message identity and the ledger ``control_revision`` it was issued
    against, so a worker can detect a *stale* decision (the ledger moved, or the
    message changed) before executing — without re-deriving lifecycle from the
    transcript. ``decision_id`` is the idempotency key.
    """
    decision_id: str
    conversation_id: str
    tenant_id: str
    source_message_id: Optional[str]
    source_message_hash: Optional[str]
    control_revision: int
    issued_at: str
    issued_by: str
    turn_plan: TurnPlan

    def to_dict(self) -> dict:
        tp = self.turn_plan
        task = tp.task
        return {
            "decision_id": self.decision_id,
            "conversation_id": self.conversation_id,
            "tenant_id": self.tenant_id,
            "source_message_id": self.source_message_id,
            "source_message_hash": self.source_message_hash,
            "control_revision": self.control_revision,
            "issued_at": self.issued_at,
            "issued_by": self.issued_by,
            "turn_plan": {
                "agent": tp.agent,
                "mode": tp.mode,
                "reason": tp.reason,
                "task": (
                    {
                        "agent": task.agent,
                        "phase": task.phase,
                        "awaiting": task.awaiting,
                        "pending_ref": task.pending_ref,
                        "started_at": task.started_at,
                    }
                    if task else None
                ),
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DecisionEnvelope":
        tp = (d or {}).get("turn_plan") or {}
        task_d = tp.get("task")
        task = (
            ActiveTask(
                agent=task_d.get("agent", ""),
                phase=task_d.get("phase", ""),
                awaiting=task_d.get("awaiting"),
                pending_ref=task_d.get("pending_ref"),
                started_at=task_d.get("started_at"),
            )
            if isinstance(task_d, dict) else None
        )
        return cls(
            decision_id=d.get("decision_id", ""),
            conversation_id=d.get("conversation_id", ""),
            tenant_id=d.get("tenant_id", ""),
            source_message_id=d.get("source_message_id"),
            source_message_hash=d.get("source_message_hash"),
            control_revision=int(d.get("control_revision") or 0),
            issued_at=d.get("issued_at", ""),
            issued_by=d.get("issued_by", ""),
            turn_plan=TurnPlan(
                agent=tp.get("agent", "bot0"),
                mode=tp.get("mode", "fresh"),
                task=task,
                reason=tp.get("reason", ""),
            ),
        )


# Full conversation control snapshot (what gets stored in context + surfaced to admin).
@dataclass(frozen=True)
class ControlState:
    agent_type: Optional[str] = None          # summary / display cache (ledger is truth after P3)
    pending_switch: Optional[PendingSwitch] = None
    active_task: Optional[ActiveTask] = None
    suspended_tasks: list[ActiveTask] = field(default_factory=list)
    # P4+: the durable orchestrator plan (active multi-task decomposition)
    plan: Optional[dict] = None


# -----------------------------------------------------------------------------
# Conversational agent registry (for orchestrator delegation, P4c+)
# The orchestrator uses this as its toolset. Values are stable agent_ids or
# callables / classes satisfying ConversationalAgent. For P4c start this is
# the source of truth for which agents can be delegated to.
# -----------------------------------------------------------------------------
AGENT_REGISTRY: dict[str, str] = {
    "transformation_advisor": "api.services.transformation_advisor.TransformationAdvisor",
    "transformation_recommender": "api.services.transformation_recommender.TransformationRecommender",
    "workflow_builder": "agent.workflow_builder.agent",
    "workflow_editor": "agent.workflow_editor.agent",
    "bot0": "api.services.bot0",  # lightweight / fallback
}

# -----------------------------------------------------------------------------
# Canonical agent-id aliasing — THE single source (this module is a leaf, so
# every control-plane module can import it without a cycle). Covers agents that
# appear in the ledger but aren't delegatable-via-class (catalog_role_create,
# personal_score) in addition to the AGENT_REGISTRY set. These are the INTERNAL
# control-plane agents — NOT the marketplace `agents` catalog. Do not re-inline
# `{"advisor": "transformation_advisor"}` anywhere; call canonical_agent().
# -----------------------------------------------------------------------------
_AGENT_ALIASES: dict[str, str] = {
    "advisor": "transformation_advisor",
    "transformation advisor": "transformation_advisor",
    "transformation_advisor": "transformation_advisor",
    "recommender": "transformation_recommender",
    "transformation recommender": "transformation_recommender",
    "transformation_recommender": "transformation_recommender",
    "workflow builder": "workflow_builder",
    "workflow_builder": "workflow_builder",
    "workflow editor": "workflow_editor",
    "workflow_editor": "workflow_editor",
    "catalog_role_create": "catalog_role_create",
    "catalog role create": "catalog_role_create",
    "personal_score": "personal_score",
    "personal score": "personal_score",
    "bot0": "bot0",
    "bot0 assistant": "bot0",
}


def canonical_agent(value: object) -> Optional[str]:
    """Canonical agent_id for a loose label (e.g. 'advisor' → 'transformation_advisor'),
    or None if unknown. THE canonicalizer for internal control-plane agents. Callers
    that want passthrough for unknowns use ``canonical_agent(x) or x``."""
    return _AGENT_ALIASES.get(str(value or "").strip().lower())


def canonical_agent_ids() -> set[str]:
    """The set of canonical internal agent_ids (the alias-map values)."""
    return set(_AGENT_ALIASES.values())


def delegatable_agent_ids() -> frozenset[str]:
    """Stable ``agent_id`` values registered for orchestrator delegation."""
    return frozenset(AGENT_REGISTRY.keys())


def workflow_agent_ids() -> frozenset[str]:
    """Workflow-family specialists — derived from ``AGENT_REGISTRY``, not a standalone set."""
    return frozenset(aid for aid in AGENT_REGISTRY if "workflow" in aid)


def registry_route_intent_labels() -> frozenset[str]:
    """L2/L3 route-classifier labels that name registered specialists (+ front-door labels)."""
    labels: set[str] = {"bot0", "ambiguous"}
    for aid in AGENT_REGISTRY:
        if aid == "transformation_advisor":
            labels.update({"advisor", "transformation_advisor"})
        elif aid == "transformation_recommender":
            labels.update({"recommender", "transformation_recommender"})
        else:
            labels.add(aid)
    return frozenset(labels)


def get_registered_agent(agent_id: str) -> str | None:
    """Return the module/class path for a registered conversational agent, or None."""
    if not agent_id:
        return None
    aid = canonical_agent(agent_id) or agent_id.lower()
    return AGENT_REGISTRY.get(aid)

# (Real P4c will resolve to an object that implements the Protocol and can be .handle_turn()'ed.)

def resolve_conversational_agent(agent_id: str, db: Any, tenant_id: str) -> Any:
    """P4c: Resolve a registered agent to an object with handle_turn (and other protocol methods).

    Returns something that can be called as agent.handle_turn(db, tenant_id, query=..., ... ) -> AgentTurnResult.
    For now, thin adapters for known agents (advisor class already implements; builder wrapped).
    """
    aid = get_registered_agent(agent_id) or agent_id
    if not aid:
        return None
    aid_lower = aid.lower()
    if "transformation_recommender" in aid_lower:
        from api.services.transformation_recommender import TransformationRecommender
        return TransformationRecommender(db, tenant_id)
    if "transformation_advisor" in aid_lower:
        from api.services.transformation_advisor import TransformationAdvisor
        return TransformationAdvisor(db, tenant_id)
    if "workflow_builder" in aid_lower:
        # Thin adapter for builder (run_agent is the entry; map to AgentTurnResult using P2b fields + heuristic)
        class _BuilderAdapter:
            agent_id = "workflow_builder"
            task_kind = "bounded"
            def __init__(self, db, tenant_id):
                self.db = db
                self.tenant_id = tenant_id
            def handle_turn(self, db, tenant_id, *, query, history=None, context=None, thread_id=None):
                from agent.workflow_builder.agent import run_agent as run_wb
                msgs = [{"role": r, "content": c} for r, c in (history or [])[-20:]]
                msgs.append({"role": "user", "content": query})
                res = run_wb(
                    messages=msgs,
                    db=db,
                    tenant_id=tenant_id,
                    project_id=(context or {}).get("project_id"),
                    session_id=thread_id,
                    account_id=None,
                )
                # Map using P2b transition fields if present in res (from builder returns), else heuristic
                transition = TaskTransition.CONTINUE
                phase = res.get("phase") or "building"
                awaiting = res.get("awaiting")
                pending_ref = res.get("pending_ref") or f"pending_workflow:{thread_id or 'no-id'}"
                if res.get("workflow_created"):
                    transition = TaskTransition.COMPLETE
                    phase = "committed"
                elif res.get("transition") in ("complete", "abandon"):
                    transition = TaskTransition.COMPLETE if res.get("transition") == "complete" else TaskTransition.ABANDON
                # Domain-only: strip any control keys the builder result still
                # carries so they cannot leak into the ledger (epic §9.2).
                cu = strip_control_keys(res.get("context_updates"))
                answer = {"answer": res.get("reply", ""), "sources": [], "blocks": []}
                return AgentTurnResult(
                    answer=answer,
                    transition=transition,
                    phase=phase,
                    awaiting=awaiting,
                    pending_ref=pending_ref,
                    context_updates=cu,
                )
            def classify_phase(self, db, tenant_id, *, conversation_id):
                """Project a COARSE phase from the builder's durable pending
                markers so the cross-agent control plane can consult builder
                progress through the shared contract. Light read of
                workflow_builder_pending — no LLM, no transcript, no import of the
                300KB agent. Returns gathering|building|reviewing|editing|committed,
                or None when there is no active build for this conversation."""
                if not db or not conversation_id:
                    return None
                try:
                    import json as _json
                    from sqlalchemy import text as _text
                    from agent.workflow_builder.state import project_coarse_phase
                    pk = f"{tenant_id}:bld_{conversation_id}"
                    row = db.execute(
                        _text("SELECT state FROM workflow_builder_pending WHERE pk = :pk"),
                        {"pk": pk},
                    ).fetchone()
                    if not row or not row[0]:
                        return None
                    st = row[0] if isinstance(row[0], dict) else _json.loads(row[0])
                except Exception:  # noqa: BLE001 — best-effort projection, never raises
                    return None
                if not isinstance(st, dict) or not st:
                    return None
                return project_coarse_phase(st)

            def resolve_pending(self, db, tenant_id, pending_ref):
                """Real exists/stale/missing for builder pending (review #3 — was a
                placeholder that always said 'exists'). Light read of
                workflow_builder_pending keyed by the thread, with staleness judged
                against the admin-tunable purge horizon."""
                if not db or not pending_ref:
                    return PendingResolution(status="missing", summary="no pending ref")
                thread_id = pending_ref.split(":", 1)[1] if ":" in pending_ref else ""
                try:
                    import json as _json
                    from datetime import datetime as _dt
                    from sqlalchemy import text as _text
                    from api.services import conversation_staleness as _staleness
                    pk = f"{tenant_id}:{thread_id}"
                    row = db.execute(
                        _text("SELECT state, updated_at FROM workflow_builder_pending "
                              "WHERE pk = :pk"),
                        {"pk": pk},
                    ).fetchone()
                except Exception:  # noqa: BLE001
                    return PendingResolution(status="missing", summary="pending lookup failed")
                if not row or not row[0]:
                    return PendingResolution(status="missing", summary="no pending workflow")
                try:
                    st = row[0] if isinstance(row[0], dict) else _json.loads(row[0])
                    updated_at = row[1]
                    purge_h = _staleness.resolve_global(db, "conversation_pending_purge_hours")
                    if updated_at is not None:
                        now = _dt.now(updated_at.tzinfo) if updated_at.tzinfo else _dt.utcnow()
                        age_h = (now - updated_at).total_seconds() / 3600.0
                        if age_h > purge_h:
                            return PendingResolution(
                                status="stale",
                                summary=f"pending {age_h:.1f}h old (purge {purge_h:.0f}h)",
                            )
                    n = len((st or {}).get("nodes") or [])
                    return PendingResolution(status="exists", summary=f"workflow build, {n} nodes")
                except Exception:  # noqa: BLE001
                    return PendingResolution(status="exists", summary="builder pending workflow")
        return _BuilderAdapter(db, tenant_id)
    if "workflow_editor" in aid_lower:
        class _EditorAdapter:
            agent_id = "workflow_editor"
            task_kind = "bounded"

            def __init__(self, db, tenant_id):
                self.db = db
                self.tenant_id = tenant_id

            def handle_turn(self, db, tenant_id, *, query, history=None, context=None, thread_id=None):
                from agent.workflow_editor.agent import run_agent as run_we
                wf_id = (context or {}).get("workflow_id")
                msgs = [{"role": r, "content": c} for r, c in (history or [])[-20:]]
                msgs.append({"role": "user", "content": query})
                res = run_we(
                    messages=msgs,
                    db=db,
                    tenant_id=tenant_id,
                    workflow_id=wf_id,
                    thread_id=thread_id,
                )
                transition = TaskTransition.CONTINUE
                if res.get("workflow_edited") or res.get("graph_changed"):
                    transition = TaskTransition.COMPLETE
                cu = strip_control_keys(res.get("context_updates"))
                answer = {"answer": res.get("reply", ""), "sources": [], "blocks": []}
                return AgentTurnResult(
                    answer=answer,
                    transition=transition,
                    phase=res.get("phase") or "editing",
                    awaiting=res.get("awaiting"),
                    pending_ref=f"workflow_editor:{thread_id or wf_id or 'no-id'}",
                    context_updates=cu,
                )

            def classify_phase(self, db, tenant_id, *, conversation_id):
                return "editing" if conversation_id else None

            def resolve_pending(self, db, tenant_id, pending_ref):
                return PendingResolution(status="exists", summary="workflow editor session")

        return _EditorAdapter(db, tenant_id)
    if "personal_score" in aid_lower:
        class _ScorerAdapter:
            agent_id = "personal_score"
            task_kind = "bounded"

            def handle_turn(self, db, tenant_id, *, query, history=None, context=None, thread_id=None):
                from agent.personal_score.agent import run_agent as run_ps
                msgs = [{"role": r, "content": c} for r, c in (history or [])[-30:]]
                msgs.append({"role": "user", "content": query})
                res = run_ps(db, tenant_id, msgs, session_id=thread_id)
                transition = TaskTransition.CONTINUE
                if res.get("phase") == "complete" or res.get("done"):
                    transition = TaskTransition.COMPLETE
                cu = strip_control_keys(res.get("context_updates"))
                answer = {
                    "answer": res.get("reply") or res.get("answer") or "",
                    "sources": res.get("sources") or [],
                    "blocks": res.get("blocks") or [],
                }
                return AgentTurnResult(
                    answer=answer,
                    transition=transition,
                    phase=res.get("phase"),
                    awaiting=res.get("awaiting"),
                    pending_ref=f"personal_score:{thread_id or 'no-id'}",
                    context_updates=cu,
                )

            def classify_phase(self, db, tenant_id, *, conversation_id):
                return None

            def resolve_pending(self, db, tenant_id, pending_ref):
                return PendingResolution(status="exists", summary="personal score session")

        return _ScorerAdapter()
    if "catalog_role_create" in aid_lower:
        class _CatalogRoleAdapter:
            agent_id = "catalog_role_create"
            task_kind = "bounded"

            def handle_turn(self, db, tenant_id, *, query, history=None, context=None, thread_id=None):
                from api.services.catalog_role_flow import handle_catalog_role_turn
                res = handle_catalog_role_turn(
                    db,
                    tenant_id=tenant_id,
                    query=query,
                    context=context,
                    history=history,
                    catalog_entry=True,
                )
                if not res:
                    return AgentTurnResult(
                        answer={"answer": "", "sources": [], "blocks": []},
                        transition=TaskTransition.NONE,
                        context_updates={},
                    )
                transition = TaskTransition.CONTINUE
                phase = (res.get("context_updates") or {}).get("catalog_role_create_phase")
                if phase in ("committed", "done", "idle"):
                    transition = TaskTransition.COMPLETE
                cu = strip_control_keys(res.get("context_updates"))
                answer = res.get("answer") or {"answer": res.get("reply", ""), "sources": [], "blocks": []}
                if isinstance(answer, str):
                    answer = {"answer": answer, "sources": [], "blocks": []}
                return AgentTurnResult(
                    answer=answer,
                    transition=transition,
                    phase=phase,
                    awaiting=phase,
                    pending_ref=f"catalog_role_create:{thread_id or 'no-id'}",
                    context_updates=cu,
                )

            def classify_phase(self, db, tenant_id, *, conversation_id):
                if not db or not conversation_id:
                    return None
                try:
                    from sqlalchemy import text as _text
                    row = db.execute(
                        _text(
                            "SELECT context FROM conversations "
                            "WHERE conversation_id = :cid AND tenant_id = :tid"
                        ),
                        {"cid": conversation_id, "tid": tenant_id},
                    ).fetchone()
                    ctx = row[0] if row and isinstance(row[0], dict) else {}
                except Exception:  # noqa: BLE001
                    return None
                from api.services.catalog_role_ledger import reconcile_catalog_flow

                snap = reconcile_catalog_flow(ctx)
                if snap.active:
                    return snap.phase or "active"
                return None

            def resolve_pending(self, db, tenant_id, pending_ref):
                return PendingResolution(status="exists", summary="catalog role intake")

        return _CatalogRoleAdapter()
    # Fallback
    return None
