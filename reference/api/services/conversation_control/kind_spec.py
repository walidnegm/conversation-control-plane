"""B6 — portable KindSpec registry for sole-continue / ledger-tracked kinds.

A kind is not a free string: it declares phases, gates, projection requirements,
pending_ref type, and terminal transitions. Used for documentation, validation
ratchets, and future scaffold generators.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from api.services.conversation_control.multi_turn_stream_contract import (
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


def _base_required(phase: str) -> frozenset[str]:
    return frozenset({"task_id", "phase", "kind", "pending_ref"}) | (
        frozenset({"gate_id"}) if phase else frozenset()
    )


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
            "building", "editing", "ir_review", "role_proposal", "domain_picker",
            "operational_data", "commit_plan",
        }),
        pending_ref_type="pending_workflow",
        terminal=frozenset({"commit_plan"}),
        gates=_WB_GATES,
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
    "KIND_REGISTRY",
    "KindSpec",
    "get_kind_spec",
    "missing_kind_specs",
    "require_kind_spec",
    "sole_continue_kinds_registered",
]
