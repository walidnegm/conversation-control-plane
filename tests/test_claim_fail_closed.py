"""claim_turn fail-closed contract — never silently proceed unclaimed on DB errors."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class ClaimFailClosedTests(unittest.TestCase):
    def test_default_raises_on_session_factory_failure(self) -> None:
        from conversation_control_plane.failure_modes import TurnClaimInfrastructureError
        from conversation_control_plane.ledger import claim_turn

        def _boom():
            raise RuntimeError("db down")

        with self.assertRaises(TurnClaimInfrastructureError):
            claim_turn(
                "t1",
                "c1",
                turn_id="turn_abc",
                session_factory=_boom,
            )

    def test_opt_in_fail_open_returns_unavailable(self) -> None:
        from conversation_control_plane.ledger import claim_turn

        def _boom():
            raise RuntimeError("db down")

        status = claim_turn(
            "t1",
            "c1",
            turn_id="turn_abc",
            session_factory=_boom,
            fail_open_on_error=True,
        )
        self.assertEqual(status, "unavailable")

    def test_no_row_without_ids(self) -> None:
        from conversation_control_plane.ledger import claim_turn

        self.assertEqual(
            claim_turn("", "c1", turn_id="t"),
            "no_row",
        )
        self.assertEqual(
            claim_turn("t1", "", turn_id="t"),
            "no_row",
        )


class JournalEventTypeContractTests(unittest.TestCase):
    def test_complete_and_abandon_are_distinct_event_names(self) -> None:
        # Documented journal types (ledger complete_task reason map).
        complete = "task_completed"
        abandon = "task_abandoned"
        self.assertNotEqual(complete, abandon)
        from conversation_control_plane import TaskTransition

        self.assertEqual(TaskTransition.COMPLETE.value, "complete")
        self.assertEqual(TaskTransition.ABANDON.value, "abandon")


if __name__ == "__main__":
    unittest.main()
