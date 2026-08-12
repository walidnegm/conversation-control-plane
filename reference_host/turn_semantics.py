"""What cognition proposes — before anything is authoritative.

Reference host. Not part of the installable SDK.

Most conversational systems ask one question of a turn — *which handler gets
it?* — and answer it with a label. Every additional thing the turn means then
has to be smuggled into that label, and labels start competing: one says the
user is asking a question, another says they are performing an act, a third
says they are continuing existing work. There is no way to say *"all three,
about this object"*, so the system picks a winner and discards the rest.

``TurnSemantics`` is the alternative: a turn **composes**. It carries several
independent facts at once, and none of them is a routing decision.

    acts                what the user is asking to be done
    entities            product objects named or implied
    references          how the turn points at them ("this", "the second one")
    modifiers           qualifications — scope, time, degree
    relations           how the parts connect
    declared_semantics  decisions the user explicitly made

**Nothing here is authority.** This is an interpreter's reading of language:
a proposal about meaning, which grounding then checks against state. A field
being present says the interpreter believed it, not that it is true.

The separation matters most for ``declared_semantics``. An interpreter may
claim *"the user declared these branches exclusive"*. Whether that claim is
attributable to the current turn — and to the objects the user actually meant
— is a question about **state**, and only the host can answer it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityRef:
    """A pointer at a product object, as the interpreter saw it.

    Deliberately *unresolved*. ``"the second one"``, ``"this workflow"`` and
    ``"Acme onboarding"`` are all valid here; turning them into identifiers is
    grounding's job, because only the host knows what exists and what the
    conversation has pinned.
    """

    kind: str
    surface_text: str = ""
    #: Set only when the interpreter had an unambiguous identifier already.
    resolved_id: str = ""
    #: deictic | ordinal | name | pin | none
    reference_mode: str = "none"


@dataclass(frozen=True)
class ProductAct:
    """Something the user wants done.

    A turn may carry more than one. "Cost this out and then simulate it" is two
    acts with an ordering relation, not a routing contest to be resolved by
    whichever classifier ran first.
    """

    act: str
    targets: tuple[EntityRef, ...] = ()
    modifiers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DeclaredSemantic:
    """A decision the interpreter believes the **user** made.

    Kept separate from ``modifiers`` on purpose. A modifier qualifies an act;
    a declared semantic asserts a product fact the user chose — and downstream
    rules may legitimately treat a user's choice as stronger evidence than a
    specialist's guess. That is exactly why it must be grounded before anyone
    relies on it.
    """

    concept: str
    value: str
    targets: tuple[EntityRef, ...] = ()


@dataclass(frozen=True)
class TurnSemantics:
    """The composed reading of one turn. A proposal, not a decision."""

    acts: tuple[ProductAct, ...] = ()
    entities: tuple[EntityRef, ...] = ()
    modifiers: dict[str, str] = field(default_factory=dict)
    relations: tuple[str, ...] = ()
    declared_semantics: tuple[DeclaredSemantic, ...] = ()
    #: What durable product interaction this turn belongs to, if the
    #: interpreter can tell. Continuity, not authority: the plane decides
    #: whether the turn may actually advance that work.
    stream_hint: str = ""
    raw_text: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.acts or self.entities or self.declared_semantics)

    def acts_named(self) -> tuple[str, ...]:
        return tuple(a.act for a in self.acts)

    def declares(self, concept: str) -> DeclaredSemantic | None:
        for d in self.declared_semantics:
            if d.concept == concept:
                return d
        return None


def empty_semantics(raw_text: str = "") -> TurnSemantics:
    """The honest reading when interpretation fails.

    Returned rather than raising, and never a *guess*: a host that cannot
    interpret a turn still has to decide what to do with it, and "I understood
    nothing" is a usable input to that decision. Inventing an act to avoid an
    empty result is how a system starts acting on things nobody asked for.
    """
    return TurnSemantics(raw_text=raw_text)
