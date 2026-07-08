"""Portable delivery-order contract tests (public repo — no Bot0 monorepo deps)."""
from __future__ import annotations

import types
import unittest
from pathlib import Path

from api.services.conversation_control.delivery_order_contract import (
    FRONT_DOOR_DETOUR_KINDS,
    STAGE_FRONT_DOOR_DELIVERY,
    active_flow_handler_must_yield,
    discovery_detour_supersedes_active_flow,
    front_door_detour_supersedes_active_flow,
    is_front_door_detour_kind,
    plan_owns_front_door_delivery,
)
from api.services.conversation_control.dispatch_phase import (
    discovery_detour_supersedes_active_flow as dispatch_facade,
)

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "docs" / "conversation-control-plane-sdk.md"


class DeliveryOrderContractTests(unittest.TestCase):
    def test_front_door_kinds(self):
        self.assertIn("scorecards", FRONT_DOOR_DETOUR_KINDS)
        self.assertIn("orientation", FRONT_DOOR_DETOUR_KINDS)
        self.assertEqual(STAGE_FRONT_DOOR_DELIVERY, "front_door_delivery")

    def test_sdk_doc_mentions_precedence(self):
        text = SDK.read_text(encoding="utf-8")
        self.assertIn("Discovery detour precedence", text)
        self.assertIn("delivery_order_contract", text)
        self.assertNotIn("active-backlog", text)

    def test_yield_helpers(self):
        plan = types.SimpleNamespace(mode="detour", discovery_kind="scorecards")
        self.assertTrue(is_front_door_detour_kind("scorecards"))
        self.assertTrue(front_door_detour_supersedes_active_flow(plan=plan))
        self.assertTrue(discovery_detour_supersedes_active_flow(plan=plan))
        self.assertTrue(dispatch_facade(plan=plan))
        self.assertTrue(plan_owns_front_door_delivery(plan))
        self.assertTrue(active_flow_handler_must_yield(plan=plan))
