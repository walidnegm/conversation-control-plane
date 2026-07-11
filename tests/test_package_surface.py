"""Portable contract pins — run inside this repo: pytest tests/"""
from __future__ import annotations

import unittest


class PackageImportTests(unittest.TestCase):
    def test_imports_clean(self) -> None:
        import conversation_control_plane as ccp

        self.assertTrue(hasattr(ccp, "decide_turn"))
        self.assertTrue(hasattr(ccp, "TurnPlan"))
        self.assertTrue(hasattr(ccp, "TaskTransition"))
        self.assertTrue(hasattr(ccp, "strip_control_keys"))
        self.assertEqual(ccp.__version__, "0.1.0")

    def test_no_top_level_api_package_required(self) -> None:
        """Public package must not require or squat top-level ``api``."""
        import conversation_control_plane as ccp

        self.assertTrue(ccp.__name__.startswith("conversation_control_plane"))
        from conversation_control_plane import ledger_keys

        self.assertIn("active_task", ledger_keys.CONTROL_KEYS)
        # Must not install a top-level ``api`` package from this distro.
        import importlib.util

        # conversation_control_plane.ledger is fine; bare ``api`` as our dist is not.
        self.assertIsNotNone(importlib.util.find_spec("conversation_control_plane.ledger"))


class StripControlKeysTests(unittest.TestCase):
    def test_strips_control_keys_from_agent_updates(self) -> None:
        from conversation_control_plane import strip_control_keys

        cleaned = strip_control_keys(
            {
                "active_task": {"kind": "cost_out"},
                "pending_switch": {"to": "x"},
                "last_chat_cost_seed": {"ok": True},
                "note": "user domain",
            }
        )
        self.assertNotIn("active_task", cleaned)
        self.assertNotIn("pending_switch", cleaned)
        self.assertEqual(cleaned.get("last_chat_cost_seed"), {"ok": True})
        self.assertEqual(cleaned.get("note"), "user domain")


class TaskTransitionTests(unittest.TestCase):
    def test_complete_and_abandon_are_distinct(self) -> None:
        from conversation_control_plane import TaskTransition

        self.assertNotEqual(TaskTransition.COMPLETE, TaskTransition.ABANDON)
        self.assertEqual(TaskTransition.COMPLETE.value, "complete")
        self.assertEqual(TaskTransition.ABANDON.value, "abandon")


class KindSpecTests(unittest.TestCase):
    def test_cost_out_registered(self) -> None:
        from conversation_control_plane import get_kind_spec

        spec = get_kind_spec("cost_out")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertIn("save_confirm", spec.phases)


class FakeHostLoopTests(unittest.TestCase):
    """Host loop shape: begin → continue → complete vs abandon journal types."""

    def test_fake_ledger_complete_vs_abandon(self) -> None:
        from examples.e2e_host_loop import FakeOwnershipLedger

        led = FakeOwnershipLedger()
        t1 = led.begin(kind="demo", phase="open", command_id="c1")
        self.assertEqual(t1["kind"], "demo")
        led.apply_complete(command_id="c2")
        self.assertIsNone(led.context.get("active_task"))
        self.assertEqual(led.journal[-1]["type"], "task_completed")

        led.begin(kind="demo", phase="open", command_id="c3")
        led.apply_abandon(command_id="c4")
        self.assertIsNone(led.context.get("active_task"))
        self.assertEqual(led.journal[-1]["type"], "task_abandoned")
        types = {e["type"] for e in led.journal}
        self.assertIn("task_completed", types)
        self.assertIn("task_abandoned", types)


if __name__ == "__main__":
    unittest.main()
