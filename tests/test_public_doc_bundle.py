"""Public doc bundle — links resolve; §15 is adopters-facing only."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SDK = DOCS / "conversation-control-plane-sdk.md"

PUBLIC_BUNDLE = (
    "conversation-control-plane-applicability.md",
    "conversation-turn-lifecycle-diagram.md",
    "conversation-control-plane-loop-playbook.md",
    "conversation-control-plane-trace-export.md",
    "conversation-control-plane-scale-smoke.md",
)


class PublicDocBundleTests(unittest.TestCase):
    def test_bundle_files_exist(self):
        for name in PUBLIC_BUNDLE:
            with self.subTest(name=name):
                self.assertTrue((DOCS / name).is_file(), msg=name)

    def test_sdk_doc_map_links_resolve(self):
        text = SDK.read_text(encoding="utf-8")
        for target in PUBLIC_BUNDLE:
            with self.subTest(target=target):
                self.assertIn(target, text)
                self.assertTrue((DOCS / target).is_file())

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
