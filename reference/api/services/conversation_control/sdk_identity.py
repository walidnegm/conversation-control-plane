"""Canonical naming and attribution for the Conversation Control Plane SDK.

Follows common open-source patterns: a published integration contract (spec) plus a
reference implementation maintained by the vendor. Package slugs are reserved for
Phase 1b extraction — not published until that gate clears.
"""
from __future__ import annotations

SDK_FULL_NAME = "Conversation Control Plane SDK"
SDK_SHORT_NAME = "Control Plane SDK"
SDK_PUBLISHER = "Bot0.ai"
SDK_REFERENCE_IMPLEMENTATION = f"{SDK_FULL_NAME} — reference implementation by {SDK_PUBLISHER}"

# Monorepo integration contract (authoritative during extraction sync).
SDK_SPEC_DOC = "docs/epics/conversation-control-plane-sdk.md"
SDK_SPEC_ROLE = "integration contract"
SDK_DELIVERY_ORDER_MODULE = (
    "api/services/conversation_control/delivery_order_contract.py"
)
SDK_EXTRACT_MANIFEST = "extract/conversation-control-plane/MANIFEST.yaml"
SDK_EXTRACT_SYNC_SCRIPT = "scripts/sync_control_plane_sdk_extract.sh"

# Public SDK home — adopters cite this repo; code/docs sync from monorepo Phase 1b.
SDK_PUBLIC_REPO = "https://github.com/walidnegm/conversation-control-plane"
SDK_PUBLIC_REPO_SLUG = "walidnegm/conversation-control-plane"

# Reserved for Phase 1b — not consumable as standalone packages yet.
SDK_PYPI_PACKAGE = "conversation-control-plane"
SDK_NPM_PACKAGE = "@bot0/conversation-control-plane"

SDK_CITATION = (
    f"{SDK_FULL_NAME} (reference implementation by {SDK_PUBLISHER}). "
    f"Public repository: {SDK_PUBLIC_REPO}. "
    f"Integration contract: {SDK_SPEC_DOC}"
)