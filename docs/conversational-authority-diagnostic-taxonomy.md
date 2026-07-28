# Conversational authority — diagnostic taxonomy

**Public / portable.** Governing operating sheet for diagnosing multi-turn
**authority** bugs before patching — plus registry governance so the class stays stable.

Written for **any multi-agent host** with sticky turns. This is a **portable
conversation-control-plane framework** with optional **host extensions** — not a claim
that every mode slug is industry-generic.

**Not** a second failure-mode registry. **Not** an anti-pattern library fork. 
**Not** an LLM-IQ benchmark program.

### How to read this document

| Part | Use when | Contents |
|------|----------|----------|
| **I — Operating sheet** | Live incident | Purpose · scope · ladder vs triage · roots · planes · procedure · definition of sealed · one example |
| **II — Registry governance** | Adding modes / A# | Cardinality · matrix · failure index · quality / validation / eval · recovery |
| **Appendix** | Onboarding | Invariants · analogues · review smells · WIP |

**Vocabulary rules:**

1. Specialized terms get a **Description** column on first table mention. 
2. **A# ids** always **id + short title** (e.g. **A1 — parallel ownership flags**). 
 Not product brand names; smells in examples are generic. 
3. Failure-mode **slugs** name burns (or **counterexamples**, marked as such). 
4. **Ratchet ≠ suite ≠ CI ≠ eval**. 
5. **Stable machine ids** — do not rename slugs/A# for prose; use doc aliases if needed.

| Role | Document |
|------|----------|
| **This doc** | Operating sheet + registry governance |
| Anti-patterns A1–A19 | [SDK §1.6](conversation-control-plane-sdk.md#16-adoption-anti-patterns-engineering-doctrine--do-not-generate-these) |
| Failure modes | YAML SoT in the host / CAQ package |
| Turn lifecycle | [conversation-turn-lifecycle-diagram.md](conversation-turn-lifecycle-diagram.md) |
| Portable SDK | [conversation-control-plane-sdk.md](conversation-control-plane-sdk.md) |

**Central distinction:**

> **Anti-pattern** = the **construction error** (what we must not build). 
> **Failure mode** = the **resulting authority burn** (what users / ledger hit). 
> **They map; they are not synonyms.**

### Quality stack at a glance

| Layer | Owns | Not the same as |
|-------|------|-----------------|
| **Diagnostics** (this sheet) | Classify burns: root → A# → mode | A test harness |
| **CAQ + purity scoreboards** | Grade: sealed / residual / gap | Redefining laws |
| **Ratchet** | One focused automated proof of a **named** class | “The whole suite is green” |
| **Regression suite** | Collection of ratchets | A single ratchet |
| **CI** | Enforcement path that runs the suite | A failure class |
| **Eval** (WIP as one map) | Multi-turn behaviour under cognition | Unit golden prose |

---

# Part I — Operating sheet

## 1. Purpose and scope

Multi-agent chat systems fail in ways that look like “the model is dumb” but are often
**architecture and ownership** mistakes. This taxonomy exists so that when a turn goes
wrong we:

1. **Name the failure class** in shared vocabulary. 
2. **Locate the earliest wrong layer**. 
3. **Choose the right seal** (structural fix + named ratchet). 
4. **Connect** quality and proof programs to the same laws.

**Conversational quality** = credible multi-turn product behaviour (continue, pins, saves,
typed acts, honest refuse) — not tone alone.

A typical host is **orchestrator + specialists + tools** under a **conversation control
plane** (ledger, decide, exclusive owner, sole-continue). Failures often sit at:

| Layer | Description | Typical burn |
|-------|-------------|--------------|
| Front-door router / classifiers | Intent and leaf selection | Wrong leaf |
| Control plane / ledger | Multi-turn ownership state | Steal, illegal restart, dual SM |
| Specialist tools / commit | Durable domain effects | Soft existence, false save |
| Delivery / UI blocks | What the user sees and can act on | Hollow open, option laundry |

**Preferred claim:** most **persistent multi-turn conversational-authority** failures are
**authority-boundary** failures, not weak model reasoning alone.

**In scope:** ownership, pin, open surface, durable claim, delivery leaf. 
**Skip full taxonomy for:** schema typos, static copy, pure infra outages, one-shot misses
without ownership drift.

---

## 2. Causal ladder vs incident triage

> The **ladder** describes **causal structure**. 
> The **triage sequence** describes **investigation order**.

### 2.1 Classification model (causal dependency)

```text
DOCTRINE (invariant)
 → ROOT — M / E / S / D
 → ANTI-PATTERN — A#
 → FAILURE MODE — slug
 → RATCHET
```

| Rung | Description | Example |
|------|-------------|---------|
| **Doctrine / invariant** | Must-always-hold boundary | Existence = registry id |
| **Root (M/E/S/D)** | Class of authority mistake | **E**: prose treated as “saved” |
| **Anti-pattern (A#)** | Known bad construction — **id + title** | **A19 — soft existence** |
| **Failure mode (slug)** | Named observable burn | `soft_existence_claim` |
| **Ratchet** | Focused proof of **one** sealed class — not “suite green” | Contract + path-faithful test |

### 2.2 Incident triage sequence (investigation order)

```text
User hit
 → Failure mode (or park candidate)
 → Plane
 → Violated invariant
 → Root (primary + optional secondary)
 → Anti-pattern A#
 → Earliest wrong layer → structural seal
 → Named ratchet + refuse/open voice
 → Scoreboard grade
```

| Do | Don’t |
|----|--------|
| Classify before a PR | Jump to keyword patches |
| Structural fix + **named ratchet** | Phrase laundry only |
| Reuse A# / mode if cousin | Invent A20 on first burn |
| Ratchets on ledger / blocks / enums | Golden full-string assistant prose |

### 2.3 Metadata (not ladder rungs)

| Metadata | Description |
|----------|-------------|
| **Review smell** | Fast human label — not a registered mode |
| **Plane** | Where the burn showed (orthogonal to root *why*) |
| **Error code** | Runtime signal — may ≠ mode slug |
| **Source of truth** | Owning doc / contract / registry |
| **Examples** | Incidents and tests — anchors, not definitions |

**Plane vs root:** root = **why**; plane = **where**. 
Wrong leaf because meaning leaked → primary **M**, plane may be delivery — do **not** add
**D** only because the user saw the result in delivery.

---

## 3. Roots M / E / S / D (parallel authority failures)

All four roots are **types of misplaced authority**. Laundry constructions sit **below**
as anti-patterns (A17, A18, …).

| Root | Full name | Parallel formulation | Description | One-line test |
|------|-----------|----------------------|-------------|---------------|
| **M** | Meaning authority leakage | (same) | Weak evidence decides **semantic intent** | Surface cue without sealed label + code policy |
| **E** | Unsealed model authority | *Effect authority leakage* | Uncommitted proposal treated as authoritative **truth** | “Saved!” without code SoR |
| **S** | Competing state authority | *State authority fragmentation* | Multiple mechanisms determine **continuation** | Dual SM / multi-writer |
| **D** | Delivery authority leakage | (construction smell was “orchestration laundry”) | User-visible **acts/surfaces** selected **outside** typed delivery policy | Freestyle CTA menus / suppress stacks invent next acts |

**D ≠ delivery plane.** Plane = location; **D** = authority over *which acts surface* leaked.

### 3.1 Primary-root rule

> **Primary root** = earliest authority boundary whose correction would **prevent the burn**. 
> **Secondary** only if an independently defective boundary remains after the primary fix.

| Example | Primary | Notes |
|---------|---------|-------|
| Wrong leaf from meaning leak; host renders that leaf | **M** | Do not add **D** for “user saw it” |
| Unclear label correct; host invents freestyle option menu | **D** | Typed policy lost |
| Model says saved though tool failed | **E** | SoR bypass |
| Parallel ownership flags fight ledger | **S** | Multi-writer |

**E vs S (subset):** single SoR bypassed → **E**; two writers drifted → **S**; both → tag
by fix target.

---

## 4. Planes

**Framework planes** (common house vocabulary):

| Plane | Description |
|-------|-------------|
| **ownership** | Multi-turn continue: kind/phase, exclusive owner |
| **delivery** | Which leaf/surface answers |
| **packaging** | Help/glossary/marketplace that can steal active work |
| **cognition** | Classifier / router / freestyle |
| **substrate** | Durable effects / SoR honesty |
| **authoring** | Multi-gate build/authoring pipeline |

**Portable absorption map** (for external readers — not a second registry):

| Portable plane | Absorbs |
|----------------|---------|
| **routing** | classifiers, much of cognition |
| **control** | ownership, ledger, continuation |
| **domain** | authoring, specialist workflows |
| **commit** | substrate, tools, durable effects |
| **presentation** | delivery, packaging, blocks/affordances |

---

## 5. Definition of sealed

A failure class is **sealed** only when:

1. Registered mode slug (or explicit counterexample id). 
2. Violated invariant named. 
3. Primary root (+ optional secondary) assigned. 
4. Causative A# or construction class identified. 
5. Earliest wrong layer fixed **structurally**. 
6. Authoritative source and sole writer explicit. 
7. Deterministic **named ratchet fails without the fix**. 
8. Multi-turn **evaluation** when cognition materially affects the path. 
9. User-facing refuse / recovery / open defined when user-visible. 
10. Scoreboard **sealed** with evidence pointers.

### Lifecycle statuses

| Status | Meaning |
|--------|---------|
| **candidate** | Observed, not classified |
| **classified** | Named; fix not done |
| **fix_in_progress** | Structural work underway |
| **ratcheted** | Named proof exists; product path may lag |
| **sealed** | Checklist complete |
| **known_residual** | Honest remaining gap |

---

## 6. Worked example (triage order)

**User hit:** “help me size it” → **cost** leaf instead of **team-sizing** workspace.

| Step | Call |
|------|------|
| Failure mode | `wrong_delivery_leaf` |
| Plane | delivery |
| Invariant | Product leaf boundaries honest |
| Root | **M** (primary) — not **D** merely because delivery showed it |
| Anti-pattern | **A11 — shape as intent**; risk of **A4** if phrase-fixed |
| Seal | Semantic leaf labels; no keyword sole arbiter (**A3** / **A5**) |
| Ratchet | Path-faithful route test for this class |

---

# Part II — Registry governance

## 7. Incident identity and cardinality

| Rule | Description |
|------|-------------|
| One incident → many modes | When burns are independently true |
| One mode = primary burn | Secondary effects ≠ automatic new incidents |
| Stable slugs | Survive product refactors |
| New mode | Distinct **law** or **ratchet** — not wording/surface alone |
| New A# | Matrix gap that **re-burns** |
| Counterexamples | Valid outcomes that disambiguate burns — **not** failure burns |

---

## 8. Anti-pattern ↔ failure mode matrix

Do **not** invent A20 or new slugs until the matrix shows a re-burning gap.

| Id | Title (portable) | Root | Typical modes | Plane | Smell you might see in *any* host |
|----|------------------|------|---------------|-------|-----------------------------------|
| **A1** | Parallel ownership flags | S | `owner_steal`, `illegal_restart`, `lost_activity_recall` | ownership | Many `flow_*_active` flags instead of one owner record |
| **A2** | Skip the control loop | S | `owner_steal`, `wrong_delivery_leaf` | ownership / delivery | Agent writes “current task” outside host decide/apply |
| **A3** | Regex as NL meaning | M | `wrong_delivery_leaf`, `named_item_misresolve` | delivery / cognition | `if "book" in text` opens a leaf |
| **A4** | Prompt exception piles | M | `wrong_delivery_leaf`, `compound_act_loss` | cognition | Growing EXCEPTION blocks in prompts |
| **A5** | Per-incident shape helpers | M | `wrong_delivery_leaf`, `domain_pick_misbound` | delivery | New helper per incident without enum+gate |
| **A6** | Scattered authority apply | S | `owner_steal`, `wrong_delivery_leaf` | ownership | Three modules each set “active flow” |
| **A7** | Concept before authority | M+S | `packaging_steal`, `owner_steal` | packaging | FAQ steals mid-task |
| **A8** | Agents write control keys | S | `owner_steal` | ownership | Specialist mutates host ownership |
| **A9** | Unvalidated model facts | E | `false_save_claim`, `success_payload_rewrite` | substrate | Metrics table engine never produced |
| **A10** | Second state machine per feature | S | `illegal_restart`, `lost_activity_recall`, `owner_steal` | ownership | Feature-local “stage” next to ledger |
| **A11** | Shape as intent | M | `wrong_delivery_leaf`, `soft_name_misresolve` | delivery | Dense list auto-opens a path |
| **A12** | Shape overrides readiness | M | `wrong_delivery_leaf`, `cold_start_collapse` | authoring / delivery | “Looks complete” opens save without ids |
| **A13** | Context-pin / delivery-order hijack | S | `ambient_pin_hijack`, `packaging_steal`, `wrong_delivery_leaf` | delivery | Last-mentioned id hijacks sticky work |
| **A14** | Re-resolve after pin | S+E | `pin_drop`, `named_item_misresolve`, `illegal_restart` | ownership / delivery | Pin present; free-text re-searches by name |
| **A15** | Ambient last-read as sole authority | S | `ambient_pin_hijack`, `owner_steal` | delivery | Session last-id without phase check |
| **A16** | Per-agent multi-turn glue | S | `owner_steal`, `lost_activity_recall` | ownership | Each specialist invents sticky flags |
| **A17** | Fail-soft option laundry | D | cousin `fall_through_fabrication`; **under-render** = unregistered candidate | delivery | “Reply accept/skip/use X…” walls of text |
| **A18** | Dispatch-order laundry | S+D | `wrong_delivery_leaf`, `owner_steal` | delivery | Cascading “if leaf X open, skip Y” piles |
| **A19** | Soft existence / unsealed transition | E+S | `soft_existence_claim`, `false_save_claim` | substrate | “We already have Project X” with no id |

**Unregistered candidates** (not indexed until law + ratchet): e.g. **under-render** —
code owns finite acts but only unmarked markdown shows them.

---

## 9. Failure-mode human index

Host YAML remains machine SoT. Slugs below are the common portable set; hosts may add
extensions without renaming these.

### 9.1 Authority burns

| Slug | Plain name | Plane | Description |
|------|------------|-------|-------------|
| `owner_steal` | Owner steal | ownership | Non-owning leaf takes continue while sticky work holds |
| `pin_drop` | Pin drop | ownership | Thin identity lost → greenfield re-resolve |
| `illegal_restart` | Illegal restart | ownership | Multi-gate stream treated as greenfield wrongly |
| `lost_activity_recall` | Lost activity recall | ownership | Prior activity cannot be restored after detour |
| `hollow_open` | Hollow open | delivery | Open/pin with no usable surface |
| `hollow_advance` | Hollow advance | delivery | Advance without next non-empty surface |
| `wrong_delivery_leaf` | Wrong delivery leaf | delivery | Wrong specialist or product path |
| `finite_token_dual_gate` | Finite token dual-gate | delivery | Confirm/ordinal legal for two gates |
| `named_item_misresolve` | Named-item misresolution | delivery | Named entity → wrong row/tool |
| `soft_name_misresolve` | Soft-name misresolution | delivery | Free-text name binds wrong object |
| `ambient_pin_hijack` | Context-pin hijack | delivery | Ambient last-read steals turn |
| `packaging_steal` | Packaging steal | packaging | Help/glossary intercepts active work |
| `fall_through_fabrication` | Escaped into unconstrained chat | cognition | Fall-through → model invents facts/acts |
| `compound_act_loss` | Compound-act loss | cognition | Secondary request dropped |
| `success_payload_rewrite` | Mutative success rewrite | substrate | Narrative ≠ committed tool result |
| `false_save_claim` | False save claim | substrate | Claims saved without success |
| `soft_existence_claim` | Soft existence claim | substrate | Claims entity exists without registry id |

### 9.2 Common host-extension burns (stable ids; semantic aliases only)

| Slug | Semantic alias (docs) | Description |
|------|----------------------|-------------|
| `draft_improve_to_ir` | midstream_refinement_hijack | Mid-stream refine hijacked into compile/structure |
| `domain_pick_misbound` | armed_selection_misbound | Armed pick; free text bound wrong |
| `cold_start_collapse` | (same) | Early multi-gate collapse via shape-as-intent |

Hosts **keep these ids** if already wired; do not rename for portability theater.

### 9.3 Counterexamples (not failure burns)

| Slug | Role | Description |
|------|------|-------------|
| `intentional_glossary` | Valid detour / control vs `packaging_steal` | User asked for product knowledge; packaging is correct **and** resume policy holds |

---

## 10. Recovery as part of the authority contract

When sealing continuity burns, define at least:

| Concern | Questions |
|---------|-----------|
| Safe terminal state | What is true after refuse/fail? |
| Prior owner | Still sticky? |
| Pending state | Consumed / retained / cleared? |
| Compensation | Partial mutative success? |
| User surface | Prose + structured acts |
| Resume | How to continue the same work |
| Retry | Idempotent? |

Especially: `owner_steal`, `hollow_advance`, `false_save_claim`,
`success_payload_rewrite`, `illegal_restart`, `pin_drop`.

---

## 11. Quality, validation, and evaluation (one map)

```text
 User hit → DIAGNOSE (triage) → SEAL → PROVE (ratchet + optional eval) → GRADE
```

| Program | Description | Status |
|---------|-------------|--------|
| **CAQ** | Named modes + laws + intended ratchets | Living (host) |
| **Purity / scorecards** | Grades sealed vs residual | Living (host) |
| **Regression suite** | Collection of **named** ratchets | Living |
| **CI** | Enforcement path | Host-wired; package ships tests |
| **Eval** | Multi-turn under cognition | **WIP** as a single unified map |

### Validation vs evaluation

| Term | Description |
|------|-------------|
| **Validation** | Deterministic contracts, schemas, enums, refuse codes |
| **Evaluation** | Behaviour under multi-turn / live cognition |
| **Diagnostics** | Classification so proof targets the right law |

### Ratchet design

| Prefer | Avoid as primary proof |
|--------|-------------------------|
| Ledger / control schemas | Exact assistant markdown |
| Enum outcomes after authority apply | Synonym lists as sole intent |
| Block type + structured fields | Full-string answer snapshots |
| Refuse codes / early-return shape | “Right coaching sentence” |

### Explicit gaps (WIP)

| Gap | Description |
|-----|-------------|
| Unified eval map | When to use unit ratchet vs freeze vs soak |
| CI portability | Package ships tests; host must wire CI |
| Scoreboard sprawl | One ladder + one mode registry |

---

## 12. Adjacent non-CAQ registries

| Registry | Description |
|----------|-------------|
| Control-plane ops | Stall, locks, pure infra |
| Infrastructure | Outages, 5xx |
| Dialogue thrash | Ceremony without authority failure |
| Raw tool / API codes | Graduate only with law + ratchet |

---

# Appendix

## A. Doctrine (invariants)

| Invariant | Description |
|-----------|-------------|
| **LLM proposes · code owns** | Model proposes; code owns transitions, ids, commits, SoR |
| **Ledger sole writer** | Only control plane writes ownership |
| **Thin state** | Small routing projection — not fat dumps |
| **Open leaf** | Open/advance ⇒ non-empty surface |
| **Finite acts → typed affordances** | Closed acts ⇒ structured controls |
| **Existence = registry id** | Name agreement ≠ durable row |
| **Hard eligibility is code-owned** | Compatibility refuse in code |

### Related terms

| Term | Description |
|------|-------------|
| **Seal** | Meets §5 checklist |
| **SoR** | Authority for “this is true” |
| **Sole-continue** / **Pin-resume** | Stickiness grades |
| **Typed refuse** | Structured block vs invented success |
| **CAQ-8** (host process id) | No phrase piles as sole NL meaning arbiter in classifiers — maps to **M** · **A3–A5**; not a mode slug |

### Control-plane terms ↔ systems analogues

| Control-plane term | Broader analogue | Description |
|--------------------|------------------|-------------|
| Sole writer | Single-writer invariant | One mutator for authoritative state |
| Ratchet | Focused regression proof | Fails when **that** law breaks again |
| Sealed transition | Committed transaction | Validate + commit |
| Soft existence | Phantom entity | No registry id |
| Owner steal | Invalid control transfer | Non-owner takes continue |
| Thin state | Minimal projection | Small routing truth |
| Hollow open | Transition without observation | Open claimed, no surface |

---

## B. Review smells (non-canonical)

| Review smell | Typical root | Often maps to |
|--------------|--------------|---------------|
| Meaning laundry | M | **A3–A5** · CAQ-8 (process) |
| Unsealed model authority | E | **A9**, **A19** |
| Fail-soft option laundry | D | **A17** |
| Soft existence | E+S | **A19** |
| Dual SM / parallel flags | S | **A1**, **A10** |
| Twin delivery surfaces | D | Often **A17**; under-render candidate |
| Overloaded vocabulary | M | `wrong_delivery_leaf` · **A11** |

---

## License / packaging note

Intended for the **portable conversation-control-plane** package and adopters of
multi-turn conversational authority. Host path names, internal changelogs, and product-only
scoreboards live in the host monorepo.
