"""Exact reset command grammar — shared across bot0, classifier, and decide.

Only unambiguous full-message discard commands are code-owned. Context-dependent
phrasing such as start-over / start-fresh / start afresh is LLM-owned (conv_9594c5).
**LLM reset_request is the arbiter** for free-text paraphrase — not substring laundry.
"""
from __future__ import annotations

EXACT_RESET_COMMANDS = frozenset({
    "reset",
    "cancel this",
    "forget this",
    "scrap this",
})

# Retired substring synonym laundry (CAQ-8). Free-text "start over" etc. is NLP
# via unified ``reset_request``. Empty so growth ratchets fail if refilled.
RESET_HINT_SUBSTRINGS: tuple[str, ...] = ()


def normalize_reset_control_text(query: str) -> str:
    return " ".join((query or "").strip().lower().split()).strip(".!?")


def is_exact_reset_command(query: str) -> bool:
    """True only for an exact discard command — not sentence-like NL."""
    return normalize_reset_control_text(query) in EXACT_RESET_COMMANDS


def has_reset_hint(query: str) -> bool:
    """True only for exact reset tokens — paraphrase is unified ``reset_request``.

    Name kept for call-site compatibility; no substring synonym laundry.
    """
    return is_exact_reset_command(query)