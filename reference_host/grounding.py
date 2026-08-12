"""Checking a reading against state — where proposals become facts.

Reference host. Not part of the installable SDK.

Grounding is the step most conversational systems skip, and skipping it is why
they feel unpredictable. An interpreter says *"the user means the second
workflow"*; grounding asks **which second workflow, out of what, listed when?**
An interpreter says *"the user declared these exclusive"*; grounding asks
**declared in this turn, or is that inherited from three turns ago?**

Two rules do most of the work:

**References identify objects; they do not claim turns.** Resolving "this
workflow" to ``wf_123`` says nothing about whether this turn may act on it.
Object identity and turn authority are different questions, and conflating
them is how a passing mention of an object becomes a takeover of the
conversation.

**A declaration must be bound to the current turn.** Otherwise a user who said
"make them exclusive" once has, in effect, said it forever — and every later
turn inherits an authorship the user did not repeat.

The host owns resolution because only the host knows what exists. The control
plane owns the *requirement* that resolution happened.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from conversation_control_plane.semantic_declaration import (
    DeclarationSet,
    GroundedDeclaration,
    SemanticProposal,
    ground_proposal,
)

from .turn_semantics import EntityRef, TurnSemantics

#: Resolves interpreter references to authoritative object ids. Returns ``()``
#: for anything it cannot resolve — silence, never a guess.
ReferenceResolver = Callable[[Sequence[EntityRef]], tuple[str, ...]]


@dataclass(frozen=True)
class GroundedTurn:
    """What is now known to be true about a turn, after checking state."""

    source_turn_id: str
    acts: tuple[str, ...] = ()
    resolved_entities: tuple[str, ...] = ()
    #: Which durable interaction this turn belongs to, if the host resolved
    #: one. A *candidate*: the plane decides whether it may be advanced.
    stream_candidate: str = ""
    #: How this turn relates to work already open — continue | detour |
    #: new_task | abandon | unknown. The plane adjudicates; this is evidence.
    current_task_relation: str = "unknown"
    declarations: DeclarationSet = field(
        default_factory=lambda: DeclarationSet(source_turn_id=""),
    )
    #: References the interpreter produced that the host could NOT resolve.
    #: Surfaced rather than dropped: an unresolvable reference is usually a
    #: question worth asking the user, not a detail to discard.
    unresolved_refs: tuple[str, ...] = ()

    @property
    def has_unresolved(self) -> bool:
        return bool(self.unresolved_refs)


def ground_turn(
    semantics: TurnSemantics,
    *,
    source_turn_id: str,
    resolve: ReferenceResolver,
    declarable_concepts: Iterable[str] = (),
    stream_candidate: str = "",
    current_task_relation: str = "unknown",
) -> GroundedTurn:
    """Check an interpreter's reading against state.

    ``declarable_concepts`` is the host's list of concepts a **user** is able
    to author. It must exclude anything specialists derive: if a specialist's
    own concept can be grounded as user-declared, grounding becomes the
    laundering step it exists to prevent.

    A declaration that cannot be grounded is **dropped, not downgraded**. The
    result is a turn where that concept simply has no declaration, so the
    specialist treats it as inferred and applies whatever evidence rule guards
    inference. Nothing is silently weakened; something is honestly absent.
    """
    resolved: list[str] = []
    unresolved: list[str] = []
    for ent in semantics.entities:
        got = tuple(resolve([ent]) or ())
        if got:
            resolved.extend(got)
        else:
            unresolved.append(ent.surface_text or ent.kind)

    declarations: list[GroundedDeclaration] = []
    for decl in semantics.declared_semantics:
        grounded = ground_proposal(
            SemanticProposal(
                concept=decl.concept,
                value=decl.value,
                target_refs=tuple(
                    t.resolved_id or t.surface_text for t in decl.targets
                ),
            ),
            source_turn_id=source_turn_id,
            resolve=lambda _refs, _d=decl: tuple(resolve(_d.targets) or ()),
            supported_concepts=declarable_concepts,
        )
        if grounded is not None:
            declarations.append(grounded)

    return GroundedTurn(
        source_turn_id=source_turn_id,
        acts=semantics.acts_named(),
        resolved_entities=tuple(dict.fromkeys(resolved)),
        stream_candidate=stream_candidate or semantics.stream_hint,
        current_task_relation=current_task_relation,
        declarations=DeclarationSet(
            source_turn_id=source_turn_id, declarations=tuple(declarations),
        ),
        unresolved_refs=tuple(unresolved),
    )
