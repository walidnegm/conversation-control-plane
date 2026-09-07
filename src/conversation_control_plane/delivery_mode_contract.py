"""Delivery mode — can this act finish in one leaf, or does it need a loop?

**Failure class:** ``act_delivered_by_a_mode_that_cannot_complete_it``.

The host turn cycle reads ``claim -> decide_turn -> handle (your leaf) ->
apply_transition -> release``. "Handle" is one phrase for two different shapes,
and nothing made a host declare which one an act needs:

``TERMINAL``
    One code-owned call answers the turn. Reads and openers where *opening is
    the answer*: list, inspect, show a graph, open an editor session.
``CONTINUES``
    The call is a PREREQUISITE, not the answer. The act needs a further step —
    an agent loop, a planner, a second tool — before the user has what they
    asked for.

**How it failed (conv_f4ae6ec0).** A stated graph edit was mapped to the same
opener as "open the editor". Opening is right for one and merely the setup for
the other. The delivery path ran one tool and ended the turn; the editor agent
would not run until an editor ledger task existed — which that very call had
just created. So the edit cost two turns and the first instruction was thrown
away: the user saw "Ready to work on X." and nothing else.

Nothing was broken in the ledger, the router, or the SDK. The act was simply
routed to a mode that could not finish it, and no contract could express the
difference. The same shape had already appeared as a capability with no act
(A2, C1) — a distinction real in behaviour and absent from the contract, so it
gets settled by which table someone happens to add a row to.

**What this module is.** The vocabulary and the assertion, not the delivery.
The plane does not own how a host runs agents, tools or jobs — the package
README is explicit that orchestration graphs and tool schemas live elsewhere.
It owns the requirement that the host *say which mode an act needs*, so a
mismatch is a failed check rather than a user staring at a greeting.

**Using it.** Declare a mode per act next to the act→delivery table, then call
``assert_delivery_modes_declared`` in a test. An act that CONTINUES must not be
delivered by a path that returns after one call.
"""
from __future__ import annotations

from typing import Any, Final, Iterable, Mapping

TERMINAL: Final = "terminal"
CONTINUES: Final = "continues"

DELIVERY_MODES: Final[frozenset[str]] = frozenset({TERMINAL, CONTINUES})


def safe_delivery_mode(value: Any) -> str | None:
    """Coerce to the closed set. Unknown is ``None`` — never a silent TERMINAL.

    Defaulting an undeclared act to TERMINAL is exactly how this failed: every
    row in an act→tool table was implicitly terminal because nothing asked.
    """
    v = str(value or "").strip().lower()
    return v if v in DELIVERY_MODES else None


def undeclared_acts(
    acts: Iterable[str],
    declared: Mapping[str, str],
) -> tuple[str, ...]:
    """Acts with no declared mode — each one a coin-flip at delivery time."""
    return tuple(
        sorted(
            a for a in acts
            if safe_delivery_mode(declared.get(a)) is None
        )
    )


def acts_needing_continuation(declared: Mapping[str, str]) -> tuple[str, ...]:
    """Acts a single-call delivery path must never be handed."""
    return tuple(
        sorted(a for a, m in declared.items() if safe_delivery_mode(m) == CONTINUES)
    )


def assert_delivery_modes_declared(
    acts: Iterable[str],
    declared: Mapping[str, str],
) -> None:
    """Raise when an act can reach delivery without declaring how it finishes."""
    missing = undeclared_acts(acts, declared)
    if missing:
        raise AssertionError(
            "acts with no declared delivery mode — a single-call path will "
            f"silently be assumed and may end the turn early: {list(missing)}",
        )


__all__ = [
    "CONTINUES",
    "DELIVERY_MODES",
    "TERMINAL",
    "acts_needing_continuation",
    "assert_delivery_modes_declared",
    "safe_delivery_mode",
    "undeclared_acts",
]
