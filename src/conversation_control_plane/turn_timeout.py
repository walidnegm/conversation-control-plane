"""Turn-timeout envelope — control-plane SDK contract.

Inline Bot0 chat turns (POST ``/chat`` and SSE ``/chat-stream``, before
async-job handoff) must fail closed when preamble or sync ``chat()`` work
stalls — independent of per-service ``timeout_seconds`` in ``llm_factory``
and of async-job poll budgets.

Enforced in: ``api/routers/bot0.py`` ``bot0_chat`` + ``bot0_chat_stream``
(server), ``frontend/lib/api/bot0.ts`` ``sendBot0Message`` /
``sendBot0MessageStream`` (client backstop).

SDK: ``docs/epics/conversation-control-plane-sdk.md``. Behavior summary: agent-architecture §2.13.
"""
from __future__ import annotations

import os

CHAT_TURN_TIMEOUT_ERROR_CODE = "chat_turn_timed_out"

CHAT_TURN_ABORTED_ERROR_CODE = "chat_turn_aborted"

CHAT_TURN_TIMEOUT_DEFAULT_SECONDS = 45

CHAT_TURN_TIMEOUT_USER_MESSAGE = (
    "This is taking longer than expected and was stopped to protect your session. "
    "Please try again — if it keeps happening, refresh the page or start a fresh message."
)

CHAT_TURN_ABORTED_USER_MESSAGE = (
    "The connection closed before your message was processed. "
    "Your message may have been saved — refresh the thread, then try again if needed."
)

_MIN_SECONDS = 15
_MAX_SECONDS = 180


def inline_chat_turn_timeout_seconds() -> int:
    """Wall-clock cap for inline ``chat()`` inside one SSE stream."""
    raw = (os.getenv("BOT0_CHAT_TURN_TIMEOUT_SECONDS") or "").strip()
    try:
        val = int(raw) if raw else CHAT_TURN_TIMEOUT_DEFAULT_SECONDS
    except ValueError:
        val = CHAT_TURN_TIMEOUT_DEFAULT_SECONDS
    return max(_MIN_SECONDS, min(val, _MAX_SECONDS))


def chat_turn_timeout_user_message() -> str:
    return CHAT_TURN_TIMEOUT_USER_MESSAGE


def chat_turn_aborted_user_message() -> str:
    return CHAT_TURN_ABORTED_USER_MESSAGE


def inline_chat_turn_timeout_client_wait_ms() -> int:
    """FE should outlive the server cap by network + heartbeat slack."""
    return (inline_chat_turn_timeout_seconds() + 10) * 1000


__all__ = [
    "CHAT_TURN_ABORTED_ERROR_CODE",
    "CHAT_TURN_ABORTED_USER_MESSAGE",
    "CHAT_TURN_TIMEOUT_DEFAULT_SECONDS",
    "CHAT_TURN_TIMEOUT_ERROR_CODE",
    "CHAT_TURN_TIMEOUT_USER_MESSAGE",
    "chat_turn_aborted_user_message",
    "chat_turn_timeout_user_message",
    "inline_chat_turn_timeout_client_wait_ms",
    "inline_chat_turn_timeout_seconds",
]