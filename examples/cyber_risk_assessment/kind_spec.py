"""B6 KindSpec for this specialist — register once in the host KIND_REGISTRY.

Production-grade claim P16: every sole-continue kind has a closed KindSpec
(phases, resolve vs continue sets, pending_ref type, terminal phases).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


KIND = "cyber_risk_assessment"

# Phase sets align with multi_turn_stream_contract (portable extract).
ENTITY_RESOLVE_PHASES = frozenset({"anchor", ""})
CONTINUE_PHASES = frozenset({
    "discover", "project", "verify", "score", "complete", "cancelled",
})
ALL_PHASES = frozenset({
    "anchor", "discover", "project", "verify", "score", "complete", "cancelled",
})
TERMINAL_PHASES = frozenset({"complete", "cancelled"})


@dataclass(frozen=True)
class KindSpec:
    kind: str
    version: int
    owner_agent: str
    phases: frozenset[str]
    entity_resolve_phases: frozenset[str] = field(default_factory=frozenset)
    continue_phases: frozenset[str] = field(default_factory=frozenset)
    pending_ref_type: str = "none"
    terminal_phases: frozenset[str] = field(default_factory=frozenset)
    exclusive_owner: Optional[str] = None
    # Thin projection keys allowed on active_task.payload (P15) — not domain IR.
    allowed_payload_keys: frozenset[str] = field(default_factory=frozenset)


CYBER_RISK_KIND_SPEC = KindSpec(
    kind=KIND,
    version=1,
    owner_agent="cyber_risk_assessment",
    phases=ALL_PHASES,
    entity_resolve_phases=ENTITY_RESOLVE_PHASES,
    continue_phases=CONTINUE_PHASES,
    pending_ref_type="cyber_panel_session",
    terminal_phases=TERMINAL_PHASES,
    exclusive_owner=KIND,
    allowed_payload_keys=frozenset({
        "workflow_id",
        "subject_id",
        "subject_kind",
        # phase / awaiting live on active_task columns, not only payload
    }),
)


def register_in(host_registry: dict) -> KindSpec:
    """Host: KIND_REGISTRY[spec.kind] = spec (or merge into portable kind_spec module)."""
    host_registry[CYBER_RISK_KIND_SPEC.kind] = CYBER_RISK_KIND_SPEC
    return CYBER_RISK_KIND_SPEC
