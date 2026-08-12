"""The same edit, authored and inferred — and why they must differ.

Run: ``python examples/declared_vs_inferred.py``

Two turns ask for the same end state. One is a user telling the system what to
do; the other is the system deciding for itself. A specialist that treats them
identically has no authority model — and one that lets the *specialist* say
which is which has a worse one.

    "Make Blog, Engage and Referral exclusive"
        the user authored the semantics
        an evidence rule guarding INFERENCE has nothing to guard
        -> proceed, and report what the evidence shows as information

    "Fix the branching here"
        the specialist chose exclusivity
        the evidence rule applies in full
        -> refuse, and ask

This example uses only the portable contract in
``conversation_control_plane.semantic_declaration`` plus the reference host. It
does not depend on any product, and it is deliberately readable end to end.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_control_plane.semantic_declaration import Provenance  # noqa: E402
from reference_host.grounding import ground_turn  # noqa: E402
from reference_host.turn_semantics import (  # noqa: E402
    DeclaredSemantic,
    EntityRef,
    ProductAct,
    TurnSemantics,
)

#: Concepts a USER can author in this product. Anything a specialist derives
#: while carrying out a request — join policy, merge target — is deliberately
#: absent: if it could be grounded as user-declared, grounding would launder
#: the specialist's own choice into user authority.
DECLARABLE = ("branch_kind",)

_CATALOG = {"Blog": "n_blog", "Engage": "n_engage", "Referral": "n_referral"}


def resolve(refs):
    """The host's reference resolver. Returns () for anything unknown."""
    out = []
    for r in refs:
        key = getattr(r, "surface_text", None) or getattr(r, "resolved_id", None) or str(r)
        if key in _CATALOG:
            out.append(_CATALOG[key])
    return tuple(out)


def _arms():
    return tuple(EntityRef(kind="node", surface_text=n) for n in _CATALOG)


def turn_declared() -> TurnSemantics:
    """"Make Blog, Engage and Referral exclusive." """
    return TurnSemantics(
        raw_text="Make Blog, Engage and Referral exclusive",
        acts=(ProductAct(act="edit_graph", targets=_arms()),),
        entities=_arms(),
        declared_semantics=(
            DeclaredSemantic(
                concept="branch_kind", value="exclusive", targets=_arms(),
            ),
        ),
        stream_hint="workflow_editor_session",
    )


def turn_inferred() -> TurnSemantics:
    """"Fix the branching here." — same act, no declaration."""
    return TurnSemantics(
        raw_text="Fix the branching here",
        acts=(ProductAct(act="edit_graph", targets=_arms()),),
        entities=_arms(),
        declared_semantics=(),
        stream_hint="workflow_editor_session",
    )


def specialist_decides(grounded, *, concept: str, targets) -> Provenance:
    """What a specialist is entitled to claim.

    It **asks** the grounded turn; it does not assert. There is no argument by
    which it could tell the plane "this was user-declared" — that is the whole
    boundary.
    """
    return grounded.declarations.provenance_for(concept, targets=targets)


def evidence_guard_blocks(provenance: Provenance, *, evidence: str) -> bool:
    """An evidence rule that guards INFERENCE, not authorship.

    Real systems compute ``evidence`` from the graph. Here it is fixed at
    UNPROVEN — the interesting case, where the structure cannot show the arms
    were ever exclusive. Authorship is what differs between the two turns.
    """
    if evidence.startswith("PROVEN"):
        return False
    return provenance is not Provenance.DECLARED_BY_USER


def run(label: str, semantics: TurnSemantics, turn_id: str) -> None:
    grounded = ground_turn(
        semantics,
        source_turn_id=turn_id,
        resolve=resolve,
        declarable_concepts=DECLARABLE,
        current_task_relation="continue",
    )
    targets = grounded.resolved_entities
    prov = specialist_decides(grounded, concept="branch_kind", targets=targets)
    blocked = evidence_guard_blocks(prov, evidence="UNPROVEN")

    print(f"\n=== {label} ===")
    print(f'  turn            : "{semantics.raw_text}"')
    print(f"  acts            : {list(grounded.acts)}")
    print(f"  resolved        : {list(targets)}")
    print(f"  declarations    : {[d.concept for d in grounded.declarations.declarations]}")
    print(f"  branch_kind     : {prov.value}")
    print("  evidence        : UNPROVEN")
    print(f"  -> {'BLOCKED — ask the user' if blocked else 'PROCEEDS — evidence reported as info'}")


def run_laundering_attempt() -> None:
    """A specialist trying to claim authorship for a decision it made.

    The user declared ``branch_kind``. The specialist then picks a
    ``join_policy`` to realise it. Asking about that concept returns
    INFERRED_BY_AGENT — the declaration covers what the user said, not what the
    specialist inferred from it.
    """
    grounded = ground_turn(
        turn_declared(),
        source_turn_id="turn_1",
        resolve=resolve,
        declarable_concepts=DECLARABLE,
    )
    print("\n=== a declared branch_kind does not authorise a derived join_policy ===")
    for concept in ("branch_kind", "join_policy"):
        prov = grounded.declarations.provenance_for(
            concept, targets=grounded.resolved_entities,
        )
        print(f"  {concept:12s} -> {prov.value}")

    print("\n=== a declaration about other objects does not authorise these ===")
    other = grounded.declarations.provenance_for("branch_kind", targets=["n_unrelated"])
    print(f"  branch_kind on n_unrelated -> {other.value}")


if __name__ == "__main__":
    run("USER DECLARED", turn_declared(), "turn_1")
    run("AGENT INFERRED", turn_inferred(), "turn_2")
    run_laundering_attempt()
    print(
        "\nThe specialist never asserts authorship. It asks the grounded turn,\n"
        "and the answer is per concept and per object.\n",
    )
