---
title: Wiring a turn capability — a checklist against the target pipeline
status: touchstone
purpose: >
 Coding aid. NOT a new model. It walks the target turn architecture stage by
 stage, and at each stage names the failure we have actually shipped, the
 existing mechanism that owns it, and the instrument that guards it.
---

# Wiring a turn capability — a checklist against the target pipeline

**This invents nothing.** The stages below are the architecture. The checklist
only says, at each stage: what breaks there, what already owns it, how to check.

> **The golden turn is below, before the stages.** This checklist is the
> per-stage FAILURE catalogue; the reference is the shape you are aiming at.
> Read it first — most defects here are a stage doing another stage's job, and
> that is easiest to see against a correct turn than against a list of wrong
> ones. It is reproduced in full rather than linked, because a checklist that
> sends you elsewhere for the target gets used without it.

---

## ⭐ THE GOLDEN TURN — the shape this checklist protects

**What this is.** One correct turn, traced end to end, with the owner of each
stage, what it produces, and the invariant that holds at the seam. Everything
below is implemented and ratcheted; nothing here is aspirational. Use it to
DIFF an implementation against — most defects in this file are a stage doing
another stage's job, and they are easiest to see side by side.

**The worked example** is the request that took eight conversations to answer:

> "can you rename Selectoin / INtent to Intention Recorded"

### The stages

| # | stage | owner | produces | the seam invariant |
|---|---|---|---|---|
| 0 | free text arrives | — | the utterance, untouched | it is DATA, never instructions |
| 1 | cognition | LLM (one bounded call) | the ACT (`read_kind` / `discovery_kind` / `product_concept_kind` / act flags), typed SLOTS (`graph_edit`, `target_constraints`), `semantic_resolution` | it never picks an id — it cannot verify one. It stops at the label |
| 2 | grounding | code | SLOTS → REFS against a CLOSED inventory; the act's `ActRequirement` checked | sufficiency gates precedence: a pin wins by SATISFYING, not by being earlier |
| 3 | stream / task | ledger | which task this turn belongs to | the ledger is SoR for ownership; context is a projection |
| 4 | authority | `free_text_claimant_may_run` at the claimant's ENTRY | who may decide this turn | gate the ENTRY, never the call site — doors multiply |
| 5 | delivery leaf | code | the answer, or the question | `may_run` — only an act with everything it needs changes anything |
| 5b | agent boundary | `handoff_act_contract` | a typed act addressed to its owner | no handoff carries unresolved prose as work |
| 6 | execution | the owning agent | the proposal / the result | claimed exactly once (`take_`) |

### The same turn, traced

```
utterance "can you rename Selectoin / INtent to Intention Recorded"

1 cognition read_kind = workflow_graph_edit
 graph_edit = {update_node, "Selectoin / INtent",
 "Intention Recorded"} <- the TYPO, verbatim
 semantic_resolution= understood

2 grounding requirement = workflow_graph_edit needs {workflow_id,
 version_id} in state {saved, graph_valid}
 entity = wf_9f5f6e14 via context pin
 node = wgn_c945464c via near match 0.94,
 runner-up 0.44, margin 0.50 <- audited
 label returned = "Selection / Intent Recorded" (the GRAPH's
 spelling, not the user's)

4 authority concept_gate, inventory_entity_resolve, workflow_simulation_entry
 all YIELD: named act is workflow_graph_edit, none owns it

5 delivery may_run = True -> the editor may open. On ASK or UNSUPPORTED it
 opens NOTHING and asks instead

5b handoff {owner_agent: workflow_editor, act_kind: update_node,
 slots: {target_label, new_label},
 resolved_refs: {workflow_id, node_id},
 provenance: {utterance, source_turn_id, resolver evidence},
 claim_policy: take_once}

6 execution workflow_editor take_s it, proposes the rename, context cleared
```

### The invariants, in one place

1. **Cognition leads, code enforces.** Meaning is the model's; identity,
 arithmetic and state are code's.
2. **One decider per decision.** Before adding a field, grep the enums. Three
 names for one fact survived here behind a sync test.
3. **Instructions are not enforcement.** Ship the ratchet, or it is a wish.
4. **An act is executable only when its typed requirements are satisfied.**
5. **No agent handoff carries unresolved prose as work.** Prose travels as
 provenance; executable fields are typed slots or resolved refs.
6. **A surface that invites a finite reply arms its owner in the same turn.**
 Rendering the choice and arming the owner are ONE act.
7. **Refusal is first-class.** Ask for the gap and keep everything already
 understood. A tenant-wide list is the failure wearing a question mark.
8. **Every declaration needs a reader.** A field, a mode, a contract or an
 enum value with no consumer is a station the architecture believes is
 enforced and is not.
9. **Fuzzy matching only over closed inventories**, after cognition produced
 the slot, with a unique winner AND a margin, and the evidence recorded.
 Never for act selection, never for what free text means.
10. **The publish source may not regress the live release.** DB-backed prompts
 are authoritative; diff before publishing from a spec.
11. **A semantic act is not automatically an operational act.** `CONTINUES`
 without a named reader, typed slots, grounded refs, and take-once claim
 is a hollow act.
12. **Graphs own navigation; Control owns admissibility; Execution owns
 mutation.** `next_act` is not a central switch in the control plane.

### The telemetry a healthy turn emits

`named_act` · `authority_conflict` · `delivery_mode` / `continues_act` ·
`act_target_status` + `act_target_source` + `act_target_rejected` ·
`resolver_method` + `resolver_score` + `resolver_runner_up_score` ·
`handoff_owner_agent` + `handoff_claimed` + `handoff_outcome` ·
`finite_surface_subcases`.

**If a turn goes wrong and none of these say so, the instrument is the bug.**
That has been true three times in this file: `authority_conflict` under-reported
by half, `ACT_DELIVERY_MODE` had zero readers, and the act-flag family was half
invisible to the gate.

### How to tell you have deviated

| symptom | the stage that slipped | seen in |
|---|---|---|
| a list where an answer was asked for | 2 — requirements never checked | "recommendations for my keynote workflow" |
| a glossary answer to a stated act | 4 — a claimant that never yielded | conv_6b245f0e, conv_c832462f |
| the right room opened and nothing done | 5b — CONTINUES with no reader | conv_6b245f0e turn 2 |
| "reply with 1" understood by nobody | 6 — a surface with no owner | TC-U |
| an act named at 0.95 and executed by no one | 4/5 — owner refused its own act | conv_d8d6b40f |
| a capability nobody can reach in words | 1 — no label exists for it | `list_domains`, `simulate_workflow` |
| a fix that works locally and not on staging | prompt published to one env only | TC-Q |

---

```
free text
 ↓
cognition proposes composed product meaning → operation + typed SLOTS + task_intent
 ↓
semantic validation + grounding → slots resolved to REFS
 ↓
stream / task resolution
 ↓
declared authority + ownership
 ↓
delivery leaf ──── another agent ────▶ handoff act ── take-once ──┐
 ↓ (ActRequirement + delivery_mode; CONTINUES has a named reader)
tool / skill / domain execution ◀────────────────────────────────┘
```

A semantic act is not automatically an operational act. Graphs own
navigation (`next_act`); Control owns admissibility; Execution owns mutation.

> **Read the architecture before adding to it.** `value_metrics_request` was
> added as a new boolean act when `read_kind=outcome_value_setup` already
> existed and the router prompt already defined it as *"collect or configure
> workflow business scorecard"*. A door existed; a second one was built beside
> it. That is the competition §0.2 forbids, and it was avoidable by reading the
> enum. **Before adding a field, grep the enums.**

---

## 0. THE LAW — above every stage

Three rules. The stages are where you satisfy them; these are what you are
satisfying.

### 0.1 Cognition leads, code enforces

The model decides **what the user means**. Code decides **what happens** and
**what is said about state**. Neither may do the other's job.

| Cognition owns | Code owns |
|---|---|
| Is this a process description? | Is 198 characters enough? *(it must not ask)* |
| Is this user stuck, or asking for work? | What is true about their ledger state |
| Which capability is being requested | Whether that capability may run now |

Violations, all found in one day:
* `has_structure` decided by a 250-char wordlist while the model held the
 answer under another name (finding B).
* A `"help me"` substring overruling a stated act (C4).
* The facilitator authoring *"You've successfully entered the value metric"* —
 cognition writing a claim about state (C6).

**Test:** if a rule decides what the user *meant*, the model owns it. If it
decides what *happens next*, code owns it. A `len` on user text is almost
always the first kind wearing the second's clothes.

### 0.2 One decider per decision — no competition

Two mechanisms that can both answer the same question will eventually disagree,
and the winner is whichever runs first. That is not a design; it is a race.

* 8 independent `*_request` booleans can all be true at once, so code must
 adjudicate — and adjudication order becomes the real router. An **enum** is
 mutually exclusive by construction and deletes the contention.
* An opener that fires while its own kind is already active competes with the
 continue path. It must **stand down**, not arbitrate (C1 round 4).
* `decide_turn` is authoritative — until a pre-decide short-circuit runs first.
 Adding a door is adding a competitor unless you place it deliberately.

**Test:** for any decision, name the single owner. If you cannot, you have a
race, not a router.

### 0.3 Instructions are not enforcement

A prompt rule is a request. A ratchet is a guarantee. Ship the guarantee and let
the prompt rule reduce how often it fires.

* C6's prompt rule forbidding state assertions was added **as belt-and-braces**;
 the fix was dropping model free text at the schema boundary.
* A schema field with no prompt example is silently always-empty — and a prompt
 published nowhere is a field that is always `false` (station 1).

**Test:** if the only thing stopping a regression is wording, it will regress.

---

### 0.4 Meaning arrives as ONE closed enum — SDK §2.1.x, not a new law

**This was already contracted. I wrote two laws before reading it; both are
withdrawn.** Kept as a worked example of the failure mode this checklist exists
to prevent: inventing where the architecture already speaks.

The Control Plane SDK, §2.1.x *Extension points — enums, kinds, surfaces,
continuum*:

> **Closed enums / ops** — Meaning → **schema-validated enum or union**;
> unknown → **clarify/refuse**; never free-text as operation authority.

```text
SemanticProposal {
 operation: <closed enum> // never free-form string authority
 target?: <id | pin key>
 read_kind?: ... // optional product LABELS, also closed
 task_intent?: continue | new_task | ...
}
```

Three properties follow, and they are the ones we kept rediscovering:

1. **One field carries the act.** Mutually exclusive by construction — so there
 is nothing to adjudicate, which is §0.2 for free.
2. **Unknown is a value.** The model can say *"I don't know"*, and code answers
 with clarify/refuse. Eight independent booleans have no unknown: all-false is
 indistinguishable from not-asked, so a suppressed value fails **silently**.
3. **`read_kind` is a label, not the act.** The SDK lists it as an optional
 product label beside `operation`. Filing an act there was never sanctioned.

**Measured drift.** The router carries **8 independent `*_request` booleans**
where the contract calls for one closed `operation` enum. Every symptom we
chased follows from that single deviation:

| Symptom | Why the contract prevents it |
|---|---|
| `outcome_value_setup` unreachable (C1/C7) | a closed enum has one place to put the act; it cannot be suppressed by eight scattered "NOT" rules |
| Adjudication order becoming the real router | mutually exclusive values cannot compete |
| A capability shipped with no way to ask for it (S7) | adding an operation means adding an enum value — visible, reviewable, countable |
| Silent all-false | `unknown` is a value the contract requires |

**Rule.** Do not add a 9th boolean, and do not file acts under `read_kind`.
The work is to converge the act family on the contract shape already published
in §2.1.x. Until then, treat every `*_request` boolean as known drift.

**Withdrawn:** "acts must not live in a read enum" (refuted — `step_kpi_edit`
and `workflow_editor_session` are acts in `read_kind` and work fine) and
"negative rules accrete past a third" (an artefact of measuring one deviation's
symptoms rather than reading the contract). The negative-rule ratchet is kept as
a **symptom monitor** while the drift exists, labelled as such.

**Corollary for §0.2.** Two signals for one decision are not always competitors.
Where one is how the model expresses the intent and the other is what delivery
switches on, normalise the first into the second — one decider downstream, every
existing wire intact. That is the interim shape until `operation` lands.

---

## Stage 1 — cognition proposes composed product meaning

**Owns:** `unified_turn_router` — 40 fields: 21 enums, 8 booleans, 11 refs.

- [ ] **Does a value already exist for this?** `read_kind` (21), `discovery_kind`
 (9), `cost_turn_kind` (5), `task_intent` (7). Extending an enum is one
 decider; adding a boolean is a new one.
- [ ] **Read SDK §2.1.x before adding a field.** Meaning is one closed
 `operation` enum with an `unknown` value; `read_kind` is a label beside
 it, not the act. A 9th `*_request` boolean is drift, not an extension.
- [ ] If the model must express something new, prefer an **enum value** over a
 9th independent boolean. Booleans are not mutually exclusive, so code has
 to adjudicate — and adjudication order silently becomes the router.
- [ ] The prompt **teaches** it, and is **published** to every env the runtime
 reads (`platform_editable` ⇒ DB is authority, inline is bookkeeping).
 Validator ceiling is 50,000 chars: declare `length_ceiling`, do not force.

*Shipped failures:* B (`has_structure` decided by a 250-char wordlist while the
model held the answer under another name) · C1 (no act existed, so the only
thing matching the words won).

## Stage 2 — semantic validation + grounding

- [ ] The proposal is checked against real state, not accepted on its face —
 does the named workflow/project exist, is it this tenant's, is it pinned?
- [ ] Ambiguity produces a **pick card**, not a guess. `resolve_workflow_ref`
 already does this; do not re-implement it.
- [ ] Sufficiency is the model's call. A `len` on user text at this stage is
 cognition wearing code's clothes.

*Shipped failures:* B2 (198 chars lost to a 250 floor) · E1 (50 floors remain).

## Stage 3 — stream / task resolution

**Owns:** `ledger.begin_task` / `complete_task`, `SOLE_CONTINUE_KINDS`, `KindSpec`.

- [ ] `begin_task` through the **ledger API** — never `context_updates["active_task"]`.
 Projection without journal is invisible to resume, orientation and audit.
- [ ] **Every** exit opens a task, including "nothing to do here".
- [ ] Re-begin keeps its `task_id` (agent + kind + `pending_ref`), or begins and
 completes stop pairing and the orphan corrupts the next resumption.
- [ ] Verify with data: `conversation_control_events` rows exist for your kind.

*Shipped failures:* A2 (0 events in 1,122) · C3 (four ids, three orphans) ·
the value-metrics loop (already-complete branch called nothing).

## Stage 4 — declared authority + ownership

**Owns:** `decide.py`, `delivery_order_contract`, `task_pin_contract`.

- [ ] Name the **single owner** of this decision. If you cannot, it is a race.
- [ ] Your entry point's **position** matters: a pre-decide short-circuit runs
 before every sticky handler.
- [ ] An opener **stands down** when its own kind is already active. It must not
 arbitrate against the continue path — it must yield to it.
- [ ] Phrase heuristics yield to a stated act. Exact chip tokens may outrank;
 substrings may not.

*Shipped failures:* C4 (`"help me"` substring beat a stated act) · C1 round 4
(opener re-fired ahead of the continue path).

## Stage 5 — delivery leaf

- [ ] The card offers the **next act**, never a status. "Already has X" is a
 reason to show X.
- [ ] It never asserts what the user has done. Model free text does not author
 claims about state — code owns the voice (`code_owned_orientation`).
- [ ] No button that does not exist; no future UI state they cannot see.
- [ ] A turn that legitimately moves nothing calls `declare_read_only_turn`.

*Shipped failures:* C6 (*"You've successfully entered the value metric"* —
nothing had been) · the terse "already has value metrics" dead end.

## Stage 5b — the agent boundary (only when the owner is another agent)

Skip this stage when your leaf runs the work itself. Enter it the moment the
act belongs to a **different agent** — that is where a correct component chain
can still lose the request, because losing it is nobody's error.

- [ ] The act has an **`ACT_REGISTRY` row**: `owner_agent`, `required_slots`,
 `required_refs`, `resolver`, `delivery_mode`. An act nobody declared is
 an act nobody owns, and ownership then falls to whoever ran first.
- [ ] **Cognition filled the slots** — user-facing values, typed. It must stop
 at the label: a signal carrying a node id means the model resolved an
 identity it cannot verify.
- [ ] **Code resolved the refs** against a closed inventory. Which member of a
 known set was named is a lookup; what the user meant is not.
- [ ] Resolution failed or was ambiguous → **ask BEFORE opening anything**.
 Open-and-stall is the defect. The question keeps the act it understood
 and asks only the part genuinely open.
- [ ] Nothing executable is prose. `build_handoff_act` refuses a slot with a
 newline or over the cap — prose belongs in `provenance`.
- [ ] The receiver claims with **`take_once`**, and an act addressed elsewhere
 is neither claimed nor destroyed: a wiring bug must be visible.
- [ ] Telemetry carries `declared_delivery_mode`, `owner_agent`, `claimed`,
 `resolved`, `outcome`. Without `outcome`, *handed over* and *done* are
 the same row.

*Shipped failure:* **conv_6b245f0e** — a stated rename on a selected workflow.
The host opened the editor and said "you can rename it directly in the editor".
The act was declared `continues` and the declaration **had no reader**; the
tools that could perform it belong to another agent; the request did not cross
with the switch. The user was asked to redo work the conversation already
contained.

## Stage 6 — tool / skill / domain execution

- [ ] A terminal phase completes the task, or it stays armed and corrupts the
 next resumption. Completion is keyed by **agent**; confirm `decide.py`
 can reach yours.

*Shipped failure:* `engagement_pack_plan` armed 11h → wrong resumption.

---

---

## The one-line test

> **Ask for it in your own words, on turn one. Then say "do all of them" on
> turn two.**

Round 1 failed at Stage 1. Round 4 failed at Stage 4. Both would have been
caught by typing two sentences at the product.

## Instruments that watch these stages

| Stage | Instrument |
|---|---|
| Stage 1 | `KindReachabilityTests` — every kind declares its act or admits it is click-only |
| Stage 3 | `plane_movement.py` — reports a turn that answered without moving the plane |
| Stage 3 | `ActWithNoDoorTests` — a sole-continue kind with no `begin_task` |
| Stage 4 | `BeginTaskIdentitySurvivesRebeginTest` — re-begin keeps its id |
| Stage 2 | `ActBeatsHelpChipTests` — a stated act is not a cry for help |
| Stage 5 / 5b | `delivery_mode_contract` — a CONTINUES act names a reader; hollow open is a miss |
| Stage 5b | handoff envelope (`owner_agent`, slots, refs, `take_once`) — prose is provenance only |

The worked example and invariants are the golden turn in this file and in
[SDK — the golden turn](conversation-control-plane-sdk.md#the-golden-turn--one-correct-turn-end-to-end).
