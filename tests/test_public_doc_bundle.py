"""Public doc bundle — links resolve; §15 is adopters-facing only."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SDK = DOCS / "conversation-control-plane-sdk.md"

PUBLIC_DOCS = (
    "conversation-control-plane-sdk.md",
    "conversation-turn-lifecycle-diagram.md",
)

MONOREPO_ONLY_DOCS = (
    "conversation-control-plane-applicability.md",
    "conversation-control-plane-loop-playbook.md",
    "conversation-control-plane-trace-export.md",
    "conversation-control-plane-scale-smoke.md",
)


class PublicDocBundleTests(unittest.TestCase):
    def test_small_public_surface(self):
        for name in PUBLIC_DOCS:
            with self.subTest(name=name):
                self.assertTrue((DOCS / name).is_file(), msg=name)
        self.assertTrue((ROOT / "README.md").is_file())
        for name in MONOREPO_ONLY_DOCS:
            with self.subTest(omitted=name):
                self.assertFalse((DOCS / name).exists(), msg=name)

    def test_sdk_points_in_bundle_not_companion_files(self):
        text = SDK.read_text(encoding="utf-8")
        self.assertIn("../README.md", text)
        self.assertIn("conversation-turn-lifecycle-diagram.md", text)
        for name in MONOREPO_ONLY_DOCS:
            with self.subTest(omitted=name):
                self.assertNotIn(name, text)
        self.assertIn("#31-three-hard-questions", text)
        self.assertIn("#111-intent-router", text)

    def test_lifecycle_has_no_bot0_entrypoint_anchors(self):
        life = DOCS / "conversation-turn-lifecycle-diagram.md"
        text = life.read_text(encoding="utf-8")
        self.assertIn("Stage → portable anchor", text)
        self.assertNotIn("bot0.py", text)
        self.assertNotIn("future-state-langgraph-migration", text)
        self.assertIn("STAGE_FRONT_DOOR_DELIVERY", text)
        self.assertIn("active_flow_handler_must_yield", text)
        self.assertIn("## 10. Is this a LangGraph?", text)
        self.assertIn("Bounded classifiers → enums", text)

    def test_section_15_is_adopter_facing(self):
        tail = SDK.read_text(encoding="utf-8").split("## 15.", 1)[-1]
        self.assertIn("Adopter-facing", tail)
        for forbidden in (
            "active-backlog",
            "AGENT_REGISTRY",
            "realization_intake_handler",
            "test_control_plane_property_harness",
            "Acceptance gate (Bot0 internal)",
            "Contract shipped (reference implementation)",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, tail)

    def test_no_internal_only_strings_in_sdk(self):
        text = SDK.read_text(encoding="utf-8")
        self.assertNotIn("active-backlog", text)
        self.assertNotRegex(text, r"conversation-control-plane-implementation\.md")
