"""Reference host — NOT part of the installable SDK.

``conversation_control_plane`` is the portable authority kernel: the ledger,
task lifecycle, ownership adjudication, gates, transitions, suspend/resume.
It deliberately does not interpret language, name product concepts, or resolve
references — those differ per product and belong to the application.

That leaves a real question unanswered for anyone adopting it: **what has to
become true before the kernel is asked to decide?**

This package answers it by example. It is a reference architecture, not a
dependency: nothing in ``conversation_control_plane`` imports it, and adopters
are expected to replace it wholesale. Its value is the *shape* of the seam —

    free text
      → TurnSemantics        (cognition proposes)
      → grounding            (host checks against state)
      → GroundedTurn         (what is now known to be true)
      → authority input      (what the kernel needs)
      → decide_turn          (the kernel decides)
      → TurnPlan

— and one law it demonstrates end to end: **a specialist may consume grounded
provenance but may not manufacture it.**
"""
