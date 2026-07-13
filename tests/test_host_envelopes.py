"""Portable host envelopes: timeout, claim session discipline, session staleness."""
from __future__ import annotations

import os
import unittest
from unittest import mock


class TurnTimeoutEnvelopeTests(unittest.TestCase):
    def test_default_and_clamp(self) -> None:
        from conversation_control_plane.turn_timeout import (
            CHAT_TURN_TIMEOUT_DEFAULT_SECONDS,
            inline_chat_turn_timeout_seconds,
        )

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BOT0_CHAT_TURN_TIMEOUT_SECONDS", None)
            self.assertEqual(
                inline_chat_turn_timeout_seconds(),
                CHAT_TURN_TIMEOUT_DEFAULT_SECONDS,
            )
        with mock.patch.dict(os.environ, {"BOT0_CHAT_TURN_TIMEOUT_SECONDS": "5"}):
            self.assertEqual(inline_chat_turn_timeout_seconds(), 15)  # min
        with mock.patch.dict(os.environ, {"BOT0_CHAT_TURN_TIMEOUT_SECONDS": "999"}):
            self.assertEqual(inline_chat_turn_timeout_seconds(), 180)  # max


class TurnSessionDisciplineTests(unittest.TestCase):
    def test_claim_prepares_then_claims(self) -> None:
        from conversation_control_plane import turn_session_discipline as tsd

        commits: list[str] = []

        def _prepare(db) -> None:
            commits.append("prepare")

        with mock.patch.object(
            tsd, "prepare_session_for_second_connection", side_effect=_prepare,
        ), mock.patch.object(
            tsd, "claim_turn", return_value="claimed",
        ) as claim:
            status, tid = tsd.claim_turn_for_conversation(
                mock.Mock(), "t1", "c1", turn_id="turn_abc",
            )
        self.assertEqual(status, "claimed")
        self.assertEqual(tid, "turn_abc")
        self.assertEqual(commits, ["prepare"])
        claim.assert_called_once()
        self.assertEqual(claim.call_args.kwargs.get("turn_id"), "turn_abc")

    def test_claim_no_conversation_is_no_row(self) -> None:
        from conversation_control_plane.turn_session_discipline import (
            claim_turn_for_conversation,
        )

        status, tid = claim_turn_for_conversation(None, "t1", None)
        self.assertEqual(status, "no_row")
        self.assertTrue(tid)


class SessionStalenessTests(unittest.TestCase):
    def test_build_reorientation_has_resume_and_fresh(self) -> None:
        from conversation_control_plane.session_staleness import (
            SESSION_REORIENTATION_RESUME_ACTION,
            SESSION_REORIENTATION_START_FRESH_ACTION,
            build_session_staleness_reorientation,
        )

        ctx = {
            "active_task": {
                "agent": "workflow_builder",
                "kind": "workflow_build",
                "phase": "active",
                "awaiting": "structure_confirm",
            },
            "_last_completed_turn": {
                "completed_at": "2020-01-01T00:00:00+00:00",
            },
        }
        out = build_session_staleness_reorientation(context=ctx, db=None)
        self.assertIsInstance(out, dict)
        self.assertEqual(out.get("action"), "answer")
        blocks = (out.get("answer") or {}).get("blocks") or []
        self.assertTrue(blocks)
        actions = (blocks[0].get("data") or {}).get("actions") or []
        ids = {a.get("action_id") for a in actions}
        self.assertIn(SESSION_REORIENTATION_RESUME_ACTION, ids)
        self.assertIn(SESSION_REORIENTATION_START_FRESH_ACTION, ids)
        self.assertTrue((out.get("context_updates") or {}).get("session_reorientation_pending"))


if __name__ == "__main__":
    unittest.main()
