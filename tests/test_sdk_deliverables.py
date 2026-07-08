"""SDK §15 deliverables — portable subset."""
from __future__ import annotations

import types
import unittest

from api.services.conversation_control import delivery_order_contract as doc
from api.services.conversation_control.dispatch_phase import discovery_detour_supersedes_active_flow
from api.services.conversation_control.delivery_order_contract import (
    front_door_detour_supersedes_active_flow,
)


class DeliveryOrderContractDeliverableTests(unittest.TestCase):
    def test_exports(self):
        for name in (
            "FRONT_DOOR_DETOUR_KINDS",
            "front_door_detour_supersedes_active_flow",
            "active_flow_handler_must_yield",
            "STAGE_FRONT_DOOR_DELIVERY",
        ):
            self.assertTrue(hasattr(doc, name), msg=name)

    def test_facade(self):
        plan = types.SimpleNamespace(mode="detour", discovery_kind="scorecards")
        self.assertTrue(discovery_detour_supersedes_active_flow(plan=plan))
        self.assertTrue(front_door_detour_supersedes_active_flow(plan=plan))
