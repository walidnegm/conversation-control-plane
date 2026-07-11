"""Exact reset command grammar — shared across bot0, classifier, and decide.

Only unambiguous full-message discard commands are code-owned. Context-dependent
phrasing such as start-over / start-fresh is LLM-owned (conv_9594c5).
"""
from __future__ import annotations

EXACT_RESET_COMMANDS = frozenset({
    "reset",
    "cancel this",
    "forget this",
    "scrap this",
})

# Substring *hints* only — never sole-fire reset. ``reset_request`` on the
# unified router / intent classifier is the arbiter for non-exact phrasing.
# Keep this set small; do not grow with synonyms (cognition ban).
RESET_HINT_SUBSTRINGS = (
    "reset",
    "start over",
    "start fresh",
    "start afresh",
    "restart",
    "cancel",
    "abort",
    "nevermind",
    "never mind",
)


def normalize_reset_control_text(query: str) -> str:
    return " ".join((query or "").strip().lower().split()).strip(".!?")


def is_exact_reset_command(query: str) -> bool:
    """True only for an exact discard command — not sentence-like NL."""
    return normalize_reset_control_text(query) in EXACT_RESET_COMMANDS


def has_reset_hint(query: str) -> bool:
    """Cheap reset hint; LLM reset_request is the arbiter."""
    text = normalize_reset_control_text(query)
    return len((query or "").strip()) < 200 and any(
        s in text for s in RESET_HINT_SUBSTRINGS
    )