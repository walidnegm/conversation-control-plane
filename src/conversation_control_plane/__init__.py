"""Conversation Control Plane SDK — public import surface.

Self-contained package (no top-level ``api`` namespace). Modules are portable
reference implementations; many monorepo host integrations remain optional
try/except so a bare ``pip install -e .`` imports cleanly.

Authority hot path (ledger writes, turn claim, revision fence, COMPLETE vs
ABANDON journal types, ``decide_turn`` when host state is supplied) is
**deterministic code**. Optional host classifiers are not part of this package.
"""
from __future__ import annotations

from conversation_control_plane.chat_dispatch_contract import (
    POST_DECIDE_DISPATCHES,
    POST_DECIDE_ONLY_DISPATCHES,
    PRE_DECIDE_DISPATCHES,
    ChatDispatchContractError,
    plan_summary_for_dispatch,
    validate_dispatch,
)
from conversation_control_plane.contract import (
    AGENT_REGISTRY,
    WORKFLOW_BUILD_KIND,
    TaskTransition,
    TurnPlan,
    delegatable_agent_ids,
    ledger_kind_for_agent,
    registry_route_intent_labels,
    resolve_conversational_agent,
    strip_control_keys,
    workflow_agent_ids,
)
from conversation_control_plane.kind_spec import KindSpec, get_kind_spec, require_kind_spec
from conversation_control_plane.ledger_keys import CONTROL_KEYS, LEDGER_MUTABLE_PROJECTION_KEYS
from conversation_control_plane.sdk_identity import (
    SDK_CITATION,
    SDK_FULL_NAME,
    SDK_PUBLIC_REPO,
    SDK_PUBLISHER,
    SDK_PYPI_PACKAGE,
)

# decide_turn is the portable dispatcher — may soft-depend on optional monorepo
# host modules at runtime; import of the function itself must succeed.
from conversation_control_plane.decide import decide_turn  # noqa: E402

__all__ = [
    "AGENT_REGISTRY",
    "CONTROL_KEYS",
    "ChatDispatchContractError",
    "KindSpec",
    "LEDGER_MUTABLE_PROJECTION_KEYS",
    "POST_DECIDE_DISPATCHES",
    "POST_DECIDE_ONLY_DISPATCHES",
    "PRE_DECIDE_DISPATCHES",
    "SDK_CITATION",
    "SDK_FULL_NAME",
    "SDK_PUBLIC_REPO",
    "SDK_PUBLISHER",
    "SDK_PYPI_PACKAGE",
    "TaskTransition",
    "TurnPlan",
    "WORKFLOW_BUILD_KIND",
    "decide_turn",
    "delegatable_agent_ids",
    "get_kind_spec",
    "ledger_kind_for_agent",
    "plan_summary_for_dispatch",
    "registry_route_intent_labels",
    "require_kind_spec",
    "resolve_conversational_agent",
    "strip_control_keys",
    "validate_dispatch",
    "workflow_agent_ids",
]

__version__ = "0.1.0"
