"""Recognising a meaning is not authority to act on it.

Portable control-plane contract. Ships in the Conversation Control Plane SDK.

A conversational system that lets specialists assert their own authority has no
authority model at all. This module names the boundary between *interpreting*
a turn and *being entitled to act on that interpretation*, and gives hosts the
shapes to carry a grounded answer across it.

## The failure it prevents

A specialist receives a request and decides how to satisfy it. Somewhere in
that work it makes a semantic choice the user never made — a branch kind, a
merge target, a default. If the specialist may also *label* that choice as
user-declared, then any rule that treats user declarations as stronger evidence
is decorative: the component the rule constrains can satisfy the rule by
claiming it already did.

Concretely, the shape to refuse::

    specialist_entry({"operations": [...], "provenance": "declared_by_user"})

That is an authority escalation wearing the costume of a parameter.

## The three-step law

1. **Cognition proposes.** An interpreter may claim the user declared
   something. That is a reading of language, which is what interpreters are
   for, and it is *never* by itself authority.
2. **The host grounds it.** Code checks the proposal against state: do the
   referenced objects exist, do they resolve to the objects the user meant, and
   is the declaration attributable to the **current** turn rather than
   inherited from history or invented?
3. **The control plane emits a grounded declaration.** Only that output carries
   ``DECLARED_BY_USER``. Specialists consume it. No specialist can construct
   one for itself, because the constructor requires facts (a turn id, resolved
   targets) that only grounding produces.

## Provenance is per concept, not per request

One request routinely mixes authored and derived decisions::

    "make those three exclusive and clean up the downstream merge"

    branch_kind  = exclusive     DECLARED_BY_USER   (the user said it)
    join_policy  = xor_merge     INFERRED_BY_AGENT  (the specialist chose it)
    merge_target = t_42          INFERRED_BY_AGENT  (the specialist chose it)

Stamping the *request* as user-declared would launder every derived decision
into user authorship. And the control plane cannot classify the second and
third: they did not exist when the turn was interpreted — the specialist
introduced them while satisfying it. So the plane owns the provenance of the
**root declaration**, and whichever component introduces an effect owns that
effect's provenance.

## What this module deliberately does not do

It does not interpret language, name product concepts, or resolve references.
Those are host concerns and differ per product. This is the envelope a host
fills and a specialist reads — the portable part is *the rule about who may
fill it*.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class Provenance(str, Enum):
    """How a semantic fact came to be asserted."""

    #: A human stated it, grounded against the current turn.
    DECLARED_BY_USER = "declared_by_user"
    #: A model or specialist decided it.
    INFERRED_BY_AGENT = "inferred_by_agent"
    #: Read off authoritative state, not decided by anyone.
    DERIVED_STRUCTURALLY = "derived_structurally"
    #: Not a choice — a rule that holds regardless.
    REQUIRED_BY_INVARIANT = "required_by_invariant"


#: Provenances that count as **authorship**: a human supplying meaning rather
#: than a component guessing at it. Only these may satisfy an evidence
#: requirement that exists to guard *inference*.
AUTHORING_PROVENANCES: frozenset[Provenance] = frozenset({
    Provenance.DECLARED_BY_USER,
})


def is_authored(provenance: Provenance | str | None) -> bool:
    try:
        return Provenance(str(provenance)) in AUTHORING_PROVENANCES
    except ValueError:
        return False


@dataclass(frozen=True)
class SemanticProposal:
    """What an interpreter *claims* the user declared. Not yet authority.

    Emitted by whatever reads the turn — an LLM router, a grammar, a form.
    The host grounds it before it becomes anything a specialist may rely on.
    """

    concept: str
    value: str
    #: References as the interpreter saw them, in whatever vocabulary it uses.
    #: Grounding resolves these; they are NOT yet object identifiers.
    target_refs: tuple[str, ...] = ()
    confidence: float | None = None


@dataclass(frozen=True)
class GroundedDeclaration:
    """A declaration the host has checked against state and the current turn.

    Construction requires ``source_turn_id`` and ``resolved_targets`` — facts
    only grounding can supply. A specialist cannot conjure one, which is the
    mechanism, not merely the convention.
    """

    concept: str
    value: str
    source_turn_id: str
    resolved_targets: tuple[str, ...]
    provenance: Provenance = Provenance.DECLARED_BY_USER

    def __post_init__(self) -> None:
        if not str(self.concept).strip():
            raise ValueError("GroundedDeclaration requires a concept")
        if not str(self.source_turn_id).strip():
            raise ValueError(
                "GroundedDeclaration requires source_turn_id — a declaration "
                "not bound to a turn cannot be attributed to the user",
            )
        if not self.resolved_targets:
            raise ValueError(
                "GroundedDeclaration requires resolved_targets — a declaration "
                "about unresolved references authorises nothing",
            )

    def declares(self, concept: str, value: Any = None) -> bool:
        if str(concept).strip() != self.concept:
            return False
        if value is None:
            return True
        return str(value).strip().lower() == self.value.strip().lower()

    def covers(self, targets: Iterable[str]) -> bool:
        """Whether this declaration was grounded against these objects.

        A declaration about other objects must not authorise work on these —
        otherwise a stale or mis-resolved reference carries authorship onto
        something the user never named.
        """
        want = {str(t) for t in (targets or ()) if str(t)}
        return bool(want) and want.issubset(set(self.resolved_targets))


@dataclass(frozen=True)
class DeclarationSet:
    """The grounded declarations attached to one turn.

    This is what the control plane hands a specialist. It is the *whole* of
    what the user is recorded as having declared; anything absent was not
    declared, which is a different statement from "was declared false".
    """

    source_turn_id: str
    declarations: tuple[GroundedDeclaration, ...] = ()

    def find(self, concept: str) -> GroundedDeclaration | None:
        for d in self.declarations:
            if d.declares(concept):
                return d
        return None

    def provenance_for(
        self, concept: str, *, targets: Iterable[str] = (),
    ) -> Provenance:
        """Provenance of ONE semantic concept for ONE set of targets.

        Returns ``DECLARED_BY_USER`` only when a grounded declaration covers
        this exact concept **and** these targets. Everything else — including
        every consequence a specialist derived while carrying out the request
        — is ``INFERRED_BY_AGENT``.

        Asking per concept is what stops laundering: a declared ``branch_kind``
        cannot confer authorship on a ``join_policy`` the specialist chose.
        """
        found = self.find(concept)
        if found is None:
            return Provenance.INFERRED_BY_AGENT
        if targets and not found.covers(targets):
            return Provenance.INFERRED_BY_AGENT
        return found.provenance


def ground_proposal(
    proposal: SemanticProposal,
    *,
    source_turn_id: str,
    resolve: Any,
    supported_concepts: Iterable[str] = (),
) -> GroundedDeclaration | None:
    """Turn an interpreter's claim into a grounded declaration, or reject it.

    ``resolve`` is the host's reference resolver: it maps the interpreter's
    ``target_refs`` to authoritative object identifiers and returns ``()`` for
    anything it cannot resolve. The control plane does not resolve references
    itself — object identity is a product concern — but it *requires* that
    resolution happened before authorship is granted.

    Returns ``None`` when the claim cannot be grounded. ``None`` is the safe
    outcome: the specialist then treats the concept as inferred and applies
    whatever evidence rule guards inference, rather than being handed an
    authorship it did not earn.
    """
    concept = str(proposal.concept or "").strip()
    if not concept:
        return None
    allowed = {str(c).strip() for c in (supported_concepts or ()) if str(c).strip()}
    if allowed and concept not in allowed:
        # An interpreter may propose anything; a host declares which concepts
        # a user is *able* to author. Concepts a specialist derives must never
        # appear here, or grounding becomes a laundering step.
        return None
    if not str(source_turn_id).strip():
        return None
    try:
        resolved = tuple(str(t) for t in (resolve(proposal.target_refs) or ()) if str(t))
    except Exception:  # noqa: BLE001 — an unresolvable reference is not authority
        return None
    if not resolved:
        return None
    return GroundedDeclaration(
        concept=concept,
        value=str(proposal.value or "").strip(),
        source_turn_id=str(source_turn_id).strip(),
        resolved_targets=resolved,
    )


__all__ = [
    "Provenance",
    "AUTHORING_PROVENANCES",
    "is_authored",
    "SemanticProposal",
    "GroundedDeclaration",
    "DeclarationSet",
    "ground_proposal",
]
