"""Conversation Control Plane SDK — Phase 1b public import surface.

Monorepo authoritative modules live under ``api.services.conversation_control``.
This package re-exports the portable contract entrypoints for adopters and harness
runs against the extracted slice.
"""
from __future__ import annotations

from api.services.conversation_control.chat_dispatch_contract import (
    POST_DECIDE_DISPATCHES,
    POST_DECIDE_ONLY_DISPATCHES,
    PRE_DECIDE_DISPATCHES,
    ChatDispatchContractError,
    plan_summary_for_dispatch,
    validate_dispatch,
)
from api.services.conversation_control.contract import (
    AGENT_REGISTRY,
    WORKFLOW_BUILD_KIND,
    TurnPlan,
    delegatable_agent_ids,
    ledger_kind_for_agent,
    registry_route_intent_labels,
    resolve_conversational_agent,
    workflow_agent_ids,
)
from api.services.conversation_control.decide import decide_turn
from api.services.conversation_control.sdk_identity import (
    SDK_CITATION,
    SDK_CHAT_DISPATCH_CONTRACT_MODULE,
    SDK_DELIVERY_ORDER_MODULE,
    SDK_EXTRACT_MANIFEST,
    SDK_EXTRACT_SYNC_SCRIPT,
    SDK_FULL_NAME,
    SDK_PUBLIC_REPO,
    SDK_PUBLISHER,
    SDK_PYPI_PACKAGE,
    SDK_REFERENCE_IMPLEMENTATION,
    SDK_SPEC_DOC,
)

__all__ = [
    "AGENT_REGISTRY",
    "ChatDispatchContractError",
    "POST_DECIDE_DISPATCHES",
    "POST_DECIDE_ONLY_DISPATCHES",
    "PRE_DECIDE_DISPATCHES",
    "SDK_CITATION",
    "SDK_CHAT_DISPATCH_CONTRACT_MODULE",
    "SDK_DELIVERY_ORDER_MODULE",
    "SDK_EXTRACT_MANIFEST",
    "SDK_EXTRACT_SYNC_SCRIPT",
    "SDK_FULL_NAME",
    "SDK_PUBLIC_REPO",
    "SDK_PUBLISHER",
    "SDK_PYPI_PACKAGE",
    "SDK_REFERENCE_IMPLEMENTATION",
    "SDK_SPEC_DOC",
    "TurnPlan",
    "WORKFLOW_BUILD_KIND",
    "decide_turn",
    "delegatable_agent_ids",
    "ledger_kind_for_agent",
    "plan_summary_for_dispatch",
    "registry_route_intent_labels",
    "resolve_conversational_agent",
    "validate_dispatch",
    "workflow_agent_ids",
]