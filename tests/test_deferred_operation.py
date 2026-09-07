"""Host conformance: DEFERRED must not flatten into a completed answer."""
from __future__ import annotations

import unittest


class DeferredOperationContinuityTests(unittest.TestCase):
    def test_public_surface_exports_types(self) -> None:
        import conversation_control_plane as ccp

        self.assertTrue(hasattr(ccp, "OperationOutcome"))
        self.assertTrue(hasattr(ccp, "DeferredOperation"))
        self.assertTrue(hasattr(ccp, "violates_deferred_continuity"))
        self.assertIn("DEFERRED", ccp.DEFERRED_CONTINUITY_LAW)
        self.assertIn("MUST NOT", ccp.DEFERRED_CONTINUITY_LAW)

    def test_deferred_is_not_a_task_transition(self) -> None:
        from conversation_control_plane import OperationOutcome, TaskTransition

        self.assertNotIn(
            OperationOutcome.DEFERRED.value,
            {m.value for m in TaskTransition},
        )

    def test_flattening_deferred_to_answer_violates(self) -> None:
        from conversation_control_plane import (
            OperationOutcome,
            make_deferred_operation,
            violates_deferred_continuity,
        )

        deferred = make_deferred_operation(
            operation_id="op_claims_1",
            task_id="task_claims_1",
            originating_turn_id="turn_claims_1",
            execution_ref="runtime:run_opaque_1",
            owner="claims_review",
        )
        self.assertTrue(
            violates_deferred_continuity(
                outcome=OperationOutcome.DEFERRED,
                host_action="answer",
                lifecycle="continue",
                deferred=deferred,
            )
        )
        self.assertTrue(
            violates_deferred_continuity(
                outcome=OperationOutcome.DEFERRED,
                host_action="answer",
                lifecycle="complete",
                deferred=deferred,
            )
        )

    def test_preserved_opaque_ref_is_legal(self) -> None:
        from conversation_control_plane.deferred_operation import (
            OperationOutcome,
            deferred_continuity_errors,
            make_deferred_operation,
        )

        deferred = make_deferred_operation(
            operation_id="op_claims_1",
            task_id="task_claims_1",
            originating_turn_id="turn_claims_1",
            execution_ref="temporal:claims-review-42",
            owner="claims_review",
        )
        self.assertEqual(
            deferred_continuity_errors(
                outcome=OperationOutcome.DEFERRED,
                host_action="operation_deferred",
                lifecycle="continue",
                deferred=deferred,
            ),
            [],
        )

    def test_missing_execution_ref_fails_closed(self) -> None:
        from conversation_control_plane import make_deferred_operation

        with self.assertRaises(ValueError):
            make_deferred_operation(
                operation_id="op_1",
                task_id="task_1",
                originating_turn_id="turn_1",
                execution_ref="  ",
            )

    def test_completed_answer_is_not_a_deferred_violation(self) -> None:
        from conversation_control_plane import (
            OperationOutcome,
            violates_deferred_continuity,
        )

        self.assertFalse(
            violates_deferred_continuity(
                outcome=OperationOutcome.COMPLETED,
                host_action="answer",
                lifecycle="complete",
            )
        )
        self.assertFalse(
            violates_deferred_continuity(
                outcome=OperationOutcome.FAILED,
                host_action="answer",
                lifecycle="complete",
            )
        )

    def test_module_stays_provider_neutral(self) -> None:
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "conversation_control_plane"
            / "deferred_operation.py"
        )
        text = src.read_text(encoding="utf-8")
        for banned in (
            "async_job_queued",
            "save_exchange",
            "poll every",
            "/jobs/",
            "bot0-chat",
        ):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()
