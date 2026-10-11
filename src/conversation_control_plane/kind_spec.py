"""B6 — portable KindSpec registry for sole-continue / ledger-tracked kinds.

A kind is not a free string: it declares phases, gates, projection requirements,
pending_ref type, and terminal transitions. Used for documentation, validation
ratchets, and future scaffold generators.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from conversation_control_plane.multi_turn_stream_contract import (
    CONTINUE_PHASES_BY_KIND,
    COST_OUT_KIND,
    CYBER_RISK_KIND,
    DRAFTING_KIND,
    ENTITY_RESOLVE_PHASES_BY_KIND,
    OUTCOME_VALUE_KIND,
    PROJECT_WORKSPACE_KIND,
    REALIZATION_KIND,
    RISK_CATALOG_LEARNING_KIND,
    SCORECARD_INTERROGATE_KIND,
    SOLE_CONTINUE_KINDS,
)

# Portable constants (avoid monorepo-only task_pin_contract import for extract).
AGENT_COST_PRICING_KIND = "agent_cost_pricing"
WORKFLOW_BUILD_KIND = "workflow_build"


@dataclass(frozen=True)
class GateSpec:
    """Portable gate definition (armed / satisfied / finite accept family)."""

    gate_id: str
    armed_flags: tuple[str, ...] = ()
    satisfied_key: Optional[str] = None
    finite_accept: tuple[str, ...] = ("yes", "go ahead", "proceed", "continue", "do it", "looks good")
    next_phase: Optional[str] = None
    reopen_from: Optional[str] = None
    reopen_to: Optional[str] = None


@dataclass(frozen=True)
class KindSpec:
    """Full kind registration object (B6)."""

    kind: str
    version: int
    owner_agent: str
    phases: frozenset[str]
    entity_resolve_phases: frozenset[str] = field(default_factory=frozenset)
    continue_phases: frozenset[str] = field(default_factory=frozenset)
    gates: tuple[GateSpec, ...] = ()
    required_projection: Mapping[str, frozenset[str]] = field(default_factory=dict)
    pending_ref_type: str = "none"
    terminal_phases: frozenset[str] = field(default_factory=frozenset)
    exclusive_owner: Optional[str] = None
    #: SDK A21 — the ``continue`` meanings this kind's leaf reads (in addition
    #: to HOST_CONTINUE_MEANINGS, which the host handles for every open kind).
    continue_meanings: frozenset[str] = field(default_factory=frozenset)
    #: SDK A21 — ``module:function`` that reads the raw text itself. A kind
    #: with an interpreter receives every continue meaning.
    continue_interpreter: str = ""


def _base_required(phase: str) -> frozenset[str]:
    return frozenset({"task_id", "phase", "kind", "pending_ref"}) | (
        frozenset({"gate_id"}) if phase else frozenset()
    )


# ---------------------------------------------------------------------------
# SDK A21 — a continue meaning needs a reader.
# The decision hands the open kind a ``continue`` with a meaning. A kind
# declares which meanings its leaf reads (or names the interpreter that reads
# the raw text itself); the boundary passes those and ASKS about any other,
# so no leaf silently absorbs a meaning it never reads. Add a meaning to a row
# only in the change that adds its reader (ratchet: test_kind_continue_meanings).
# ---------------------------------------------------------------------------

#: Meanings the host handles for every open kind, whatever the leaf.
HOST_CONTINUE_MEANINGS: frozenset[str] = frozenset({
    # The schema default, and what every leaf does when nothing narrower
    # applies; a leaf that re-reads the text treats it as its own input.
    "advance",
    # Fail-soft: the leaf re-reads the text itself (no host reader exists).
    "unclear",
    # Answered by the host's pending-switch handler when a switch is armed.
    "accept_switch",
    "decline_switch",
})

#: Meanings each kind's own leaf reads, beyond HOST_CONTINUE_MEANINGS.
KIND_CONTINUE_MEANINGS: dict[str, frozenset[str]] = {
    # Verified 2026-10-10 (B-260/B-261 trace). Readers:
    # - confirm: agent_cost_profile_save.is_cost_profile_save_confirm →
    #   finite_confirm_grammar.confirm_at_open_gate (the save gate);
    # - decline: the save gate persists only on agreement, so a decline
    #   leaves the estimate unsaved — not persisting IS the answer;
    # - amend_estimate / reestimate_pin / reprice_catalog / show_profile:
    #   bot0 _COST_CONTINUE_MEANINGS + cost_out_turn (amend merge);
    # - question: cost_question_contract (B-260).
    COST_OUT_KIND: frozenset({
        "confirm", "decline",
        "amend_estimate", "reestimate_pin", "reprice_catalog", "show_profile",
        "question",
    }),
}

#: Kinds whose leaf reads the raw text itself (``module:function``). Both
#: entries compute a parallel continue meaning (their own labels and an
#: ends-with-"?" rule) — a second decider beside the router, recorded as
#: B-262 debt. They are declared here as what they ARE, not endorsed: the
#: retirement is to declare the meanings they need and read the decision.
KIND_CONTINUE_INTERPRETERS: dict[str, str] = {
    "recommendation_setup": (
        "conversation_control_plane.recommendation_setup_continue_meaning_contract"
        ":resolve_rec20_continue_meaning"
    ),
    "pattern_midflight": (
        "conversation_control_plane.pattern_midflight_contract"
        ":map_pattern_midflight_continue_meaning"
    ),
}

#: Kinds whose leaf has not been traced yet. The boundary does not limit them
#: (today's behaviour) until a verified row moves them out. SHRINK-ONLY:
#: B-261 owns the audit; a kind leaves this set with a row or an interpreter.
KIND_CONTINUE_UNAUDITED: frozenset[str] = frozenset({
    AGENT_COST_PRICING_KIND,
    "concept_thread",
    CYBER_RISK_KIND,
    DRAFTING_KIND,
    "engagement_pack_plan",
    "input_state_setup",
    OUTCOME_VALUE_KIND,
    PROJECT_WORKSPACE_KIND,
    REALIZATION_KIND,
    RISK_CATALOG_LEARNING_KIND,
    SCORECARD_INTERROGATE_KIND,
    WORKFLOW_BUILD_KIND,
})


#: SDK A21 + A17 (10-11 audit): a kind whose continue meanings the boundary
#: ENFORCES must also say how its open card is shown again — when the
#: boundary asks about a meaning the step does not read, the person stays on
#: that card instead of losing it to a bare line. Every key of
#: KIND_CONTINUE_MEANINGS needs a row here ("module:function", taking the
#: ledger context, returning ContentBlocks).
KIND_OPEN_CARD: dict[str, str] = {
    "cost_out": "conversation_control_plane.cost_question_contract:open_card_blocks",
}


def open_card_blocks(kind: str | None, context: Any) -> list[dict[str, Any]]:
    """The open step's card for ``kind``, or [] when none is declared or available."""
    ref = KIND_OPEN_CARD.get(str(kind or "").strip())
    if not ref:
        return []
    try:
        import importlib

        module, _, fn = ref.partition(":")
        blocks = getattr(importlib.import_module(module), fn)(context)
        return [b for b in (blocks or []) if isinstance(b, dict)]
    except Exception:  # noqa: BLE001 — never break the ask
        return []


def accepted_continue_meanings(kind: str | None) -> frozenset[str] | None:
    """The continue meanings an open ``kind`` may receive, or None for no limit.

    None when the kind is unknown (nothing to enforce) or names an
    interpreter (it reads every meaning itself). Otherwise the host meanings
    plus the kind's declared ones; the boundary asks about anything else.
    """
    key = str(kind or "").strip()
    if not key or key not in KIND_CONTINUE_MEANINGS and key not in KIND_CONTINUE_INTERPRETERS:
        return None
    if KIND_CONTINUE_INTERPRETERS.get(key):
        return None
    return HOST_CONTINUE_MEANINGS | KIND_CONTINUE_MEANINGS.get(key, frozenset())


def _spec(
    kind: str,
    *,
    owner: str,
    phases: frozenset[str],
    pending_ref_type: str,
    terminal: frozenset[str],
    gates: tuple[GateSpec, ...] = (),
    version: int = 1,
    exclusive: Optional[str] = None,
) -> KindSpec:
    er = ENTITY_RESOLVE_PHASES_BY_KIND.get(kind, frozenset())
    cont = CONTINUE_PHASES_BY_KIND.get(kind, frozenset())
    req = {p: frozenset({"task_id", "phase", "kind"}) for p in phases}
    for p in cont:
        req[p] = frozenset({"task_id", "phase", "kind", "pending_ref"})
    return KindSpec(
        kind=kind,
        version=version,
        owner_agent=owner,
        phases=phases,
        entity_resolve_phases=er,
        continue_phases=cont,
        gates=gates,
        required_projection=req,
        pending_ref_type=pending_ref_type,
        terminal_phases=terminal,
        exclusive_owner=exclusive or kind,
        continue_meanings=KIND_CONTINUE_MEANINGS.get(kind, frozenset()),
        continue_interpreter=KIND_CONTINUE_INTERPRETERS.get(kind, ""),
    )


# Authoring multi-gate (workflow_build) — portable gate ids align with authoring_gate_contract.
_WB_GATES = (
    GateSpec(
        gate_id="structure",
        armed_flags=("_awaiting_ir_confirmation",),
        satisfied_key="_ir_confirmed",
        next_phase="role_proposal",
    ),
    GateSpec(
        gate_id="staffed",
        armed_flags=("_awaiting_role_proposal_review",),
        satisfied_key="_staffed_ir_satisfied",
        next_phase="domain_picker",
        reopen_from="domain_picker",
        reopen_to="role_proposal",
    ),
    GateSpec(
        gate_id="agents",
        armed_flags=("_awaiting_agents_review",),
        satisfied_key="_agents_reviewed",
        next_phase="briefs",
    ),
    GateSpec(
        gate_id="domain",
        armed_flags=("_awaiting_domain_choice", "_awaiting_domain"),
        satisfied_key="_resolved_domain_id",
        next_phase="operational_data",
    ),
    GateSpec(
        gate_id="kpi",
        armed_flags=("_awaiting_operational_data",),
        satisfied_key="_operational_data_confirmed",
        next_phase="commit_plan",
    ),
    GateSpec(
        gate_id="commit",
        armed_flags=("_awaiting_commit_confirmation",),
        satisfied_key="_commit_confirmed",
        next_phase="complete",
    ),
)

KIND_REGISTRY: dict[str, KindSpec] = {
    COST_OUT_KIND: _spec(
        COST_OUT_KIND,
        owner="bot0",
        phases=frozenset({
            "open", "entity_pick", "anchored", "sizing", "estimated",
            "save_confirm", "terminal",
        }),
        pending_ref_type="cost_seed",
        terminal=frozenset({"terminal"}),
    ),
    AGENT_COST_PRICING_KIND: _spec(
        AGENT_COST_PRICING_KIND,
        owner="bot0",
        # Shares cost_out exclusive owner (same chat cost surface; sole-continue sticky).
        exclusive="cost_out",
        phases=frozenset({
            "open", "eliciting", "preview", "saved", "published", "complete", "terminal",
        }),
        pending_ref_type="agent_cost_ir",
        terminal=frozenset({"complete", "terminal", "published"}),
    ),
    CYBER_RISK_KIND: _spec(
        CYBER_RISK_KIND,
        owner="bot0",
        phases=frozenset({
            "anchor", "discover", "project", "verify", "score", "complete", "cancelled",
        }),
        pending_ref_type="cyber_panel_session",
        terminal=frozenset({"complete", "cancelled"}),
    ),
    REALIZATION_KIND: _spec(
        REALIZATION_KIND,
        owner="bot0",
        phases=frozenset({"readiness", "spec", "targets", "package", "complete", "active"}),
        pending_ref_type="realization_plan",
        terminal=frozenset({"complete", "package"}),
    ),
    OUTCOME_VALUE_KIND: _spec(
        OUTCOME_VALUE_KIND,
        owner="bot0",
        phases=frozenset({"collecting", "confirming", "complete", "active"}),
        pending_ref_type="outcome_value_workflow",
        terminal=frozenset({"complete"}),
    ),
    DRAFTING_KIND: _spec(
        DRAFTING_KIND,
        owner="bot0",
        phases=frozenset({
            "awaiting_domain", "awaiting_details", "drafting", "refining",
            "ready_to_build", "active",
        }),
        pending_ref_type="drafting_pending",
        terminal=frozenset({"ready_to_build"}),
    ),
    PROJECT_WORKSPACE_KIND: _spec(
        PROJECT_WORKSPACE_KIND,
        owner="transformation_advisor",
        phases=frozenset({
            "open", "ready", "roles", "staffing", "scenario", "sim",
            "active", "complete", "consulting",
        }),
        pending_ref_type="project_workspace",
        terminal=frozenset({"complete"}),
    ),
    SCORECARD_INTERROGATE_KIND: _spec(
        SCORECARD_INTERROGATE_KIND,
        owner="bot0",
        phases=frozenset({"active", "detail", "complete"}),
        pending_ref_type="scorecard_run",
        terminal=frozenset({"complete"}),
    ),
    RISK_CATALOG_LEARNING_KIND: _spec(
        RISK_CATALOG_LEARNING_KIND,
        owner="bot0",
        phases=frozenset({"browsing", "detail", "complete"}),
        pending_ref_type="risk_catalog",
        terminal=frozenset({"complete"}),
    ),
    WORKFLOW_BUILD_KIND: _spec(
        WORKFLOW_BUILD_KIND,
        owner="workflow_builder",
        phases=frozenset({
            "active", "ready", "in_progress", "extracting", "gathering", "reviewing",
            "building", "editing", "ir_review", "role_proposal", "briefs",
            "domain_picker", "operational_data", "commit_plan",
            # Failure terminal. Without one, the ONLY terminal was the success
            # phase (``commit_plan``), so a build that failed mid-``extracting``
            # stayed ACTIVE forever — and ``workflow_build`` is in
            # SOLE_CONTINUE_KINDS_SUPPRESS_SURFACE_READ, so the orphaned task
            # silently suppressed every later saved-workflow read in that
            # conversation. Observed: an extraction failed, and three hours
            # later "display the graph" was still being refused, for a build
            # the user had long abandoned.
            #
            # Conjecture failure mode: ``unterminated_task_on_failure``.
            "build_failed",
        }),
        pending_ref_type="pending_workflow",
        terminal=frozenset({"commit_plan", "build_failed"}),
        gates=_WB_GATES,
    ),
    "pattern_midflight": _spec(
        "pattern_midflight",
        owner="bot0",
        exclusive="pattern_midflight",
        phases=frozenset({
            "choose", "gap", "confirm_run", "running", "results", "abandoned",
        }),
        pending_ref_type="pattern_midflight_plan",
        terminal=frozenset({"results", "abandoned"}),
    ),
    "recommendation_setup": _spec(
        "recommendation_setup",
        owner="bot0",
        exclusive="recommendation_setup",
        phases=frozenset({
            "path", "project", "costs", "scorecard", "target",
            "placements", "graph", "participants", "boundary",
            "ready", "abandoned",
        }),
        pending_ref_type="recommendation_route",
        # `ready` is the costing + green Run card — not a terminal.
        # Kind ends via finish_active_task after Run, or phase abandoned.
        terminal=frozenset({"abandoned"}),
    ),
    "engagement_pack_plan": _spec(
        "engagement_pack_plan",
        owner="bot0",
        exclusive="engagement_pack",
        phases=frozenset({"plan", "advancing", "complete"}),
        pending_ref_type="engagement_pack_plan",
        terminal=frozenset({"complete"}),
    ),
    # Input State Manager — host leaf under bot0 (not AGENT_REGISTRY agent).
    "input_state_setup": _spec(
        "input_state_setup",
        owner="bot0",
        exclusive="input_state_setup",
        phases=frozenset({
            "pick_state",
            "show",
            "propose_act",
            "confirm_write",
            "written",
            "ready_to_run",
            "handoff",
            "abandoned",
        }),
        pending_ref_type="input_state_act_package",
        terminal=frozenset({"handoff", "abandoned"}),
    ),
    # Stacked glossary / product-knowledge Q&A (concept packaging home).
    "concept_thread": _spec(
        "concept_thread",
        owner="bot0",
        exclusive="default",
        phases=frozenset({"open", "followup", "complete"}),
        pending_ref_type="none",
        terminal=frozenset({"complete"}),
    ),
}


def get_kind_spec(kind: str | None) -> KindSpec | None:
    if not kind:
        return None
    return KIND_REGISTRY.get(str(kind).strip())


def require_kind_spec(kind: str) -> KindSpec:
    spec = get_kind_spec(kind)
    if spec is None:
        raise KeyError(f"unregistered kind: {kind!r}")
    return spec


def sole_continue_kinds_registered() -> frozenset[str]:
    """Every SOLE_CONTINUE_KINDS member must have a KindSpec (ratchet)."""
    return frozenset(SOLE_CONTINUE_KINDS)


def missing_kind_specs() -> frozenset[str]:
    return sole_continue_kinds_registered() - frozenset(KIND_REGISTRY.keys())


__all__ = [
    "GateSpec",
    "HOST_CONTINUE_MEANINGS",
    "KIND_CONTINUE_INTERPRETERS",
    "KIND_CONTINUE_MEANINGS",
    "KIND_CONTINUE_UNAUDITED",
    "KIND_REGISTRY",
    "accepted_continue_meanings",
    "KindSpec",
    "get_kind_spec",
    "missing_kind_specs",
    "require_kind_spec",
    "sole_continue_kinds_registered",
]
