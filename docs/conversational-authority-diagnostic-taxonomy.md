# Conversational authority — diagnostic taxonomy

**Public / portable.** Governing sheet for diagnosing multi-turn **authority** bugs
before patching.

**Not** a second failure-mode registry. **Not** an anti-pattern library fork. 
**Not** an LLM-IQ benchmark program — see **where this fits** below.

| Role | Document |
|------|----------|
| **This doc** | Purpose · fit in quality/eval scheme · ladder · roots · seal recipe · A# ↔ mode matrix |
| Anti-patterns A1–A19 | [SDK §1.6](conversation-control-plane-sdk.md#16-adoption-anti-patterns-engineering-doctrine--do-not-generate-these) |
| Failure modes (slug + law + ratchet) | Failure-mode registry (YAML SoT in the host / CAQ package) |
| Process + quality process | Conversational Authority Quality (CAQ) companion docs in the host / Conjecture package |
| Turn lifecycle | [conversation-turn-lifecycle-diagram.md](conversation-turn-lifecycle-diagram.md) |
| Portable SDK | [conversation-control-plane-sdk.md](conversation-control-plane-sdk.md) |

**Central distinction (keep prominent):**

> **Anti-pattern** = the **construction error** (what we must not build). 
> **Failure mode** = the **resulting authority burn** (what users / ledger hit). 
> **They map; they are not synonyms.**

**Vocabulary rule:** when a specialized term first appears in a table, that table
includes a **Description** (or equivalent) column so readers are not left with
opaque jargon.

---

## Purpose of a diagnostic taxonomy

Multi-agent chat systems fail in ways that look like “the model is dumb” but are often
**architecture and ownership** mistakes: wrong exclusive owner, dual state, unsealed
commit, laundry delivery, hollow open. A diagnostic taxonomy exists so that when a
turn goes wrong we:

1. **Name the failure class** in shared vocabulary (not a one-off ticket title). 
2. **Locate the earliest wrong layer** (cognition hop, control plane, specialist, delivery). 
3. **Choose the right seal** (contract + ratchet), not the next phrase exception. 
4. **Connect quality and test programs** so purity, CAQ, behaviour runners, and
 regression suites measure the same laws under different lenses.

Without a taxonomy, every incident becomes a local patch; with one, incidents **graduate**
into anti-patterns, modes, and automated proof.

### Why it serves conversational quality

Conversational quality here is not “pleasant tone alone.” It is **credible multi-turn
product behaviour**: continue stays on the right work, pins do not lie, saves and
existence claims match the registry, finite acts are typed, refuse is honest.

The taxonomy makes that quality **debuggable**: root (M/E/S/D) + mode + plane turn a
user complaint into a structural finding that quality programs can grade.

### Why it is about multi-agent architecture

A typical host is **orchestrator + specialists + tools** under a **conversation control
plane** (ledger, decide, exclusive owner, sole-continue). Failures often sit at:

| Layer | Description | Typical burn |
|-------|-------------|--------------|
| Front-door router / classifiers | Intent and leaf selection before the control plane | Wrong leaf (cost vs project, glossary vs action) |
| Control plane / ledger | Authoritative multi-turn ownership state | Steal, illegal restart, dual state machine |
| Specialist tools / commit | Durable domain effects | Soft existence, false save, ineligible transition |
| Delivery / UI blocks | What the user sees and can act on | Hollow open, option laundry, twin surfaces |

The taxonomy is **control-plane-native**: it assumes multi-turn ownership, not single-shot
chat completion. Architecture maps say *who* runs; this sheet says *how to diagnose when
ownership or delivery broke*.

### Why it is not “patch first”

Engineers and coding agents default to the nearest heuristic. The taxonomy **forces a
pause**: classify → map A#/mode → seal at earliest wrong layer → ratchet. Seal the
**class**, not the symptom.

---

## Where this fits: Diagnostics · Quality · LLM evaluation & validation

Three **related but distinct** programs. Do not collapse them into one doc or one harness.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Multi-agent product (host · ledger · specialists · tools · FE) │
└─────────────────────────────────────────────────────────────────────────┘
 │ │ │
 ▼ ▼ ▼
 DIAGNOSTICS QUALITY LLM EVAL & VALIDATION
 (this taxonomy) (grades · seals) (efficacy · proof · soaks)
 │ │ │
 When it breaks, Is the class sealed? Does the system still
 what class is it? Living scoreboard. obey law under cognition?
```

| Pillar | Description | Question it answers | Anti-goal |
|--------|-------------|---------------------|-----------|
| **1. Diagnostics** | Classification of authority burns into shared classes (this taxonomy) | *What kind of failure is this, and where did architecture go wrong?* | Not freestyle “model IQ”; not phrase laundry |
| **2. Quality** | **Scoreboards + seals:** CAQ mode grades, purity boards (voice/surface/ownership), sealed vs known_gap | *Are the laws sealed and graded on a living board?* | Not inventing parallel purity audits per incident |
| **3. Proof (validation + eval)** | **Regression/CI ratchets** (deterministic) + **multi-turn eval/soaks** (under cognition) — often incomplete as one program | *Will CI catch a re-burn? Does law hold when the model varies?* | Not LMSYS/MMLU as ship gate; not LLM-as-judge as primary SoR |

**Note:** Pillar 3 is deliberately **work in progress** as a single map — hosts usually have a regression suite and some multi-turn proofs; wiring them as one “eval + CI” narrative is still maturing. See *Association with quality programs* below.

### How the pillars connect (one flow)

```text
 Incident / soak / user hit
 │
 ▼
 ① DIAGNOSE (this taxonomy)
 doctrine · root · A# · failure mode · plane
 │
 ▼
 ② SEAL (architecture + code)
 earliest wrong layer · thin state · sole writer · typed refuse
 │
 ▼
 ③ PROVE (eval & validation)
 ratchet / behaviour freeze / path-faithful suite · optional soak
 │
 ▼
 ④ GRADE (quality programs)
 scoreboard · known residual if not yet sealed
```

| If you only… | You get… |
|--------------|----------|
| Diagnose without seal | Vocabulary, no product fix |
| Seal without ratchet | Fake-fixed (looks fixed once) |
| Eval without taxonomy | Test soup; wrong law tested |
| Quality grade without modes | Scores with no named failure class |

### Validation vs evaluation (house language)

| Term | Description |
|------|-------------|
| **Validation** | Deterministic checks: schema, enums, contracts, unit ratchets, refuse codes — **code-owned truth** |
| **Evaluation** | Behaviour under multi-turn / live cognition: freezes, soaks, path-faithful proofs — **law under non-deterministic models** |
| **Diagnostics** | How humans and coding agents **classify** a burn so validation and evaluation target the right law |

### Operational tension: ratchet design (avoid creep & flaky tests)

A **ratchet** at the **validation** layer must not assert on free-form model prose.
Non-deterministic hops make golden full-string chat tests flaky and encourage false
“fixes” that chase wording.

| Prefer (validation ratchets) | Avoid as primary proof |
|------------------------------|-------------------------|
| Ledger / control transition schemas (kind, phase, pin ids present/absent) | Exact assistant markdown paragraphs |
| Enum / label outcomes after authority apply | Synonym lists of user utterances as sole arbiter |
| Block type + structured fields (`type`, chip `send_text`, metrics ids) | Full-string snapshot of entire answer |
| Tool refuse codes / early-return shape | “Model said the right coaching sentence” |
| Contract modules + allow-lists | Hop-count-only or latency-only as authority seal |

**Evaluation** may still check **behavioural envelopes** (allowed outcomes, state law under
freeze) — that is not the same as unit-test golden prose.

**Guideline:** If a test fails when the model rephrases but the ledger and blocks are
correct, the test is wrong — tighten to **control-plane structure**, not phrasing.

---

## Scope of claim

**In scope:** multi-turn **conversational-authority** failures — ownership, pin, open
surface, durable claim, delivery leaf — when chat can look fine and the machine is wrong.
Prefer this process when the class **re-burns** or affects continue/stickiness/commit honesty.

**Strictly limit full 5-rung classification** to those multi-turn, authority-affecting
failures. **Do not** run the full ladder for:

| Skip full taxonomy | Description | Handle instead as |
|--------------------|-------------|-------------------|
| Tool syntax / schema validation errors | Deterministic input/output shape failures | Validator fix + unit test |
| Static copy typos, one-off wording | Presentation polish without ownership drift | Copy / product-voice inventory |
| One-shot tool outage, 5xx, timeout | Infrastructure failure without authority lie | Ops / infra playbook |
| Single-turn trivial miss with no ownership drift | Isolated miss that does not re-burn as a class | Local fix; escalate if it becomes a class |

**Out of scope as “ownership bugs”:** retrieval failures, pure model capability limits,
tool outages, latency, policy infra, malformed source data — unless they *also* produce
an authority burn (then classify both).

**Preferred claim:**

> Most **persistent multi-turn conversational-authority** failures are **ownership**
> failures, not “the model is dumb.”

---

## Official ladder (canonical rungs only)

```text
DOCTRINE
 What invariant must hold?

ROOT — M / E / S / D
 Why did the authority boundary fail?

ANTI-PATTERN — A#
 What implementation shape caused it?

FAILURE MODE — slug/id
 What observable product or ledger failure resulted?
 (slug is the machine name of the mode — not a separate conceptual rung)

RATCHET
 What automated proof prevents recurrence?
```

### What each rung means

| Rung | Description | Example |
|------|-------------|---------|
| **Doctrine / invariant** | A **must-always-hold** product or architecture rule. Not a tip — a boundary. If it fails, trust in multi-turn chat fails. | “Existence = registry id”; “ledger is sole writer of active task” |
| **Root (M/E/S/D)** | The **class of authority mistake** that let the invariant slip — why the system became unreliable | **E**: model text treated as “saved”; **S**: two writers of ownership |
| **Anti-pattern (A#)** | A **known bad construction** in code or prompts that tends to cause that root | A19 soft existence; A3 regex NL routing |
| **Failure mode (slug)** | The **named, observable burn** when that construction ships — user/ledger symptom with a stable machine `id` | `soft_existence_claim`, `wrong_delivery_leaf` |
| **Ratchet** | An **automated check** that fails if the bad shape returns: regression test, contract module, allow-list, CI gate, behaviour freeze. Without a ratchet, a “fix” is temporary memory | Contract module + path-faithful test that fails without the seal |

**Invariant vs ratchet:** an invariant is the **rule**; a ratchet is the **machine that
complains when the rule is broken again**. Doctrine without ratchets drifts; ratchets
without doctrine become brittle tests with no product story.

### Metadata (not ladder rungs)

| Metadata | Description | Role in diagnosis |
|----------|-------------|-------------------|
| **Review smell** | A short human-facing label for a recurring code smell (e.g. “meaning laundry”) | Fast recognition in review; **not** a registered failure mode; may map to several A# |
| **Plane** | The **surface area of the product stack** where the burn shows up | Orthogonal to root *why*: same root can appear on different planes |
| **Error code** | A runtime or API signal string returned by code | May or may not equal a failure-mode slug; useful for logs and refuse paths |
| **Source of truth** | The owning document, registry file, or contract module for a law | Where to edit doctrine or ratchets without forking copies |
| **Examples** | Path-faithful incidents or soaks | Proof anchors; not definitions |

**Plane vs root:** root explains **why** the authority boundary failed; plane identifies
**where** it showed up.

Example: Root **S** · Plane **delivery** · Mode `wrong_delivery_leaf`.

### Planes (closed vocabulary)

| Plane | Description |
|-------|-------------|
| **ownership** | Who holds multi-turn continue: ledger kind/phase, exclusive owner, sole-continue vs greenfield |
| **delivery** | Which leaf/surface answers the user: cards, chips, path pickers, wrong specialist vs right one |
| **packaging** | Concept / glossary / marketplace “about the product” that can steal from active work |
| **cognition** | Classifier / router / freestyle hops that invent meaning or fall through to unconstrained chat |
| **substrate** | Durable effects and system-of-record honesty: saves, ids, tables, tool commit/refuse |
| **authoring** | Multi-gate authoring pipeline (structure, domain, commit, staffing) |

---

## Doctrine (invariants)

An **invariant** is a standing rule of the product architecture: something that must remain
true across turns, agents, and refactors. Violating it may still “look like chat,” but the
machine’s story of ownership, identity, or durable effect is wrong.

| Invariant | Description |
|-----------|-------------|
| **LLM proposes · code owns** | The model may classify intent, extract fields, and narrate. It must **not** be the final authority on state transitions, durable ids, money/math, or “what just committed.” Code validates, writes the ledger, runs tools, and renders system-of-record surfaces. |
| **Ledger sole writer** | Only the control plane may write **ownership** keys — especially active task, kind, phase, and exclusive-owner fields. Specialists return **proposals** or domain results; they do not invent a second “who owns the thread” store. |
| **Thin state** | Routing/identity truth kept by the control plane is **small and stable**: phase, kind, thin pins (ids, name pin, pending ref) — not full IR, transcript dumps, or fat draft blobs. Fat artifacts live behind pointers. |
| **Open leaf** | When the system pins, advances, or claims to open work, the user must get a **non-empty product surface** (prose and/or blocks) — not “Pinned…” with nothing to do. |
| **Finite acts → typed affordances** | When code owns a **closed set** of next steps, those acts must be **typed controls** the host already resolves — chips, cards, structured clarification — not markdown menus the user must retype. |
| **Existence = registry id** | Dialogue agreement (“we’ll call it Project X”) is not a **registry row** with a durable id. Soft existence claims without ids are unsealed authority. |
| **Hard eligibility is code-owned** | Product **compatibility** constraints are enforced in code refuse paths. The model may *propose* suitability; it must not *commit* an ineligible transition. |

### Related terms (same family)

| Term | Description |
|------|-------------|
| **Seal** | A closed failure class: named law + structural fix + **ratchet** — not a one-off phrase patch. |
| **SoR (system of record)** | The store or path allowed to say “this is true” for ids, commits, and tables — never ephemeral model prose alone. |
| **Sole-continue** | Stickiness grade: after a detour that does not abandon, the thread returns to the **same** multi-gate work (kind + phase), not a greenfield re-ask. |
| **Pin-resume** | Weaker stickiness: remember path/evidence via thin pins, but do not auto-reopen the full card every turn unless product requires sole-continue. |
| **Typed refuse** | Code returns a structured error / blocked surface with product voice, instead of letting the model invent success after a failed tool. |

### House terms ↔ broader systems analogues

| House term | Broader systems analogue | Description (multi-turn chat) |
|------------|--------------------------|-------------------------------|
| **Sole writer** | Single-writer invariant | Exactly one mechanism may mutate a given class of authoritative state (e.g. only the control plane writes ownership). Parallel writers → drift and wrong continue. |
| **Ratchet** | Regression invariant / executable specification | An automated check that **fails when the sealed law is broken again**. Doctrine is the rule; the ratchet is the executable proof. Prefer structure over golden prose. |
| **Sealed transition** | Committed transaction | A durable effect is real only after the responsible system **validates and commits**. Model narration alone is not a commit. |
| **Soft existence** | Unresolved identity / phantom entity | Dialogue or pin *suggests* a durable thing without a registry **id**. Phantom until code verifies or creates. |
| **Owner steal** | Invalid control transfer | Continue / delivery is taken by a **non-owning** leaf while sticky multi-turn work still holds the thread. |
| **Thin state** | Minimal authoritative state projection | Routing/identity truth is a **small projection** — not a full transcript or fat IR dump. |
| **Hollow open** | State transition without usable observation | The system claims to open or advance work, but the user gets **no usable surface**. |

**Reading rule:** when reviewing with platform engineers, you may use the analogue once
for clarity, then prefer the **house term** so search and registry ids stay stable.

---

## Roots M / E / S / D

| Root | Full name | Description | One-line test |
|------|-----------|-------------|---------------|
| **M** | Meaning authority leakage | Lexical rules, input shape, or scattered exceptions are treated as **sufficient proof of user intent** | Surface cue decides meaning without sealed semantic label + code policy |
| **E** | Unsealed model authority | Model output is treated as an authoritative number, identity, transition, or durable result **without validation and commitment** | “Saved!” / table / existence without code SoR |
| **S** | Competing state authority | Two mechanisms can independently determine the same authoritative state or continuation | Dual state machine, pin vs id, multi-writer |
| **D** | Delivery orchestration laundry | Available acts, presentation order, suppression, or next-step behavior are encoded in **accumulating prose or branches** rather than typed delivery policy | Growing CTA menus / suppress stacks |

Many incidents are **combinations** (especially **E+S**, **S+D**). When a combination is
real, record **both** roots after applying the boundary rule below.

### Operational boundary: **E** vs **S**

| Call | Description — when to use it |
|------|------------------------------|
| **Primary root = E** | A **single** authoritative store or path already existed but the system **bypassed** it for model text / narration / freestyle. |
| **Primary root = S** | **Two valid** state keys, machines, or writers were both allowed and **drifted**. |
| **Both E+S** | Allowed after the rule above; tag primary by the **fix target** (seal the missing code SoR first if one source should have been sole). |

**Guideline:** If the team argues E vs S for more than a short call, apply the table,
pick primary + optional secondary, and move to anti-pattern / mode / seal. Taxonomy is
for **routing the fix**, not taxonomy theater.

---

## Review smells (non-canonical)

Fast code-review recognition aids. **Not** a registry. Map to roots / A#; do not invent
parallel slugs.

| Review smell | Description | Typical root | Often maps to |
|--------------|-------------|--------------|---------------|
| Meaning laundry | Free-text / phrase lists used as **sole** arbiter of what the user meant | M | A3–A5, CAQ-8 |
| Unsealed model authority | Model prose treated as committed fact, id, or transition without code SoR | E | A9, A19 |
| Fail-soft option laundry | After unclear, growing **prose CTA menus** instead of reasoner + re-show card | D | A17 |
| Soft existence / unsealed transition | “We already have X” or create without thin-verify of registry id | E+S | A19 |
| Dual SM / parallel flags | Second ownership machine beside ledger kind/phase (see **A1**, **A10**) | S | A1, A10 |
| Twin delivery surfaces | Same gate rendered as **two** competing UIs | D | product-voice under-render |
| Overloaded vocabulary | One user word maps to **two** product leaves without semantic disambiguation | M | `wrong_delivery_leaf` cousins |

---

## Diagnostic approach (not patch-first)

**When something re-burns — stop coding the next phrase exception.**

1. **Name the user hit** in plain language. 
2. **Root** — M / E / S / D (or combination). 
3. **Review smell** (optional, non-registered). 
4. **Anti-pattern** — existing A# if any (SDK §1.6). Prefer map before proposing a new A#. 
5. **Failure mode** — existing registry slug or park candidate until law + ratchet. 
6. **Plane** — metadata on the mode. 
7. **Earliest wrong layer** — domain / control plane / delivery / prompt — fix there. 
8. **Ratchet** — path-faithful test or contract that **fails if the burn returns**. 
9. **Product voice** on refuse/open if user-facing copy was wrong. 
10. **Grade** on the quality scoreboard when sealed.

| Do | Don’t |
|----|--------|
| Classify with this ladder before a PR | Jump to keyword patches |
| Seal: structural fix + **ratchet** that would fail without it | “Fix” only in prompt laundry or unanchored script |
| Reuse A# / mode if cousin | Invent a new A# / slug on first burn |
| NL meaning → LLM label | Code `looks_like_*` as sole intent arbiter |
| Hard eligibility → code | Hope the model remembers product rules |
| Keep **thin** control state; sole-write ownership | Parallel ownership booleans or fat domain blobs in the ledger |
| Ratchets on **ledger / blocks / enums** | Golden full-string assistant prose as unit proof |
| Full ladder only for multi-turn **authority** re-burns | Taxonomy ceremony for tool schema typos / static copy |

**Two-attempt pause:** same user-visible class twice → symptom ledger + this taxonomy → then fix.

---

## Anti-pattern ↔ failure mode mapping matrix

**Purpose:** reveal duplicates, over-broad modes, ops vs CAQ. 
**Do not add a new A# or failure-mode slug** until this matrix shows a gap that re-burns.

### Are A1 / A11 “Bot0-only”?

**No.** **A1–A19** are **portable construction errors** for multi-agent *conversational
control* (any host that has sticky multi-turn work + specialists). They are **not**
Bot0 product features or UI names.

| What A# is | What A# is not |
|------------|----------------|
| Stable **id** + short **title** for a bad *build shape* | A Bot0 screen, tool, or brand term |
| Shared with [SDK §1.6](conversation-control-plane-sdk.md#16-adoption-anti-patterns-engineering-doctrine--do-not-generate-these) for deep essays | A failure mode slug (`pin_drop`) — modes are *burns*; A# are *how you built wrong* |
| Illustrated with **generic** code smells (flags, regex, dual FSMs) | A requirement that your repo use the same variable names |

**Reading tip:** Lead with the **title** (“parallel ownership flags”); keep **A1** for
cross-ref and PR language. Code columns below use portable smells — your codebase may
spell them differently (`is_drafting`, `cost_active`, `workflow_open`, …).

| Id | Title (portable) | Root | Construction error (plain language) | Smell you might see in *any* host | Typical modes | Plane |
|----|------------------|------|-------------------------------------|-----------------------------------|---------------|-------|
| **A1** | Parallel ownership flags | S | “Who owns the thread?” encoded as many booleans instead of one ownership record (kind + phase) | `drafting_active`, `cost_open`, `advisor_on` all true independently | `owner_steal`, `illegal_restart`, `lost_activity_recall` | ownership |
| **A2** | Skip the control loop | S | Specialist or side path mutates continue without the host decide/apply path | Agent writes “current task” in its own store and the host never runs decide | `owner_steal`, `wrong_delivery_leaf` | ownership / delivery |
| **A3** | Regex as NL meaning | M | Regular expressions / keyword lists as **sole** arbiter of free-text intent | `if re.search(r"recommend\|optimize", text)` opens a product leaf | `wrong_delivery_leaf`, `named_item_misresolve` | delivery / cognition |
| **A4** | Prompt exception piles | M | Growing “if user says X do Y” lists in classifier prompts | Per-incident EXCEPTION blocks in system prompts | `wrong_delivery_leaf`, `compound_act_loss` | cognition |
| **A5** | Per-incident shape helpers | M | One-off `looks_like_*` / shape helpers as sole intent arbiter | New helper per soak without enum + code gate | `wrong_delivery_leaf`, `domain_pick_misbound` | delivery |
| **A6** | Scattered authority apply | S | Many sites apply ownership without a single authority path | Three modules each set “active flow” | `owner_steal`, `wrong_delivery_leaf` | ownership |
| **A7** | Concept before authority | M+S | Help/glossary/marketplace packaging runs before ownership is decided | FAQ leaf steals mid-task without stamp | `packaging_steal`, `owner_steal` | packaging |
| **A8** | Agents write control keys | S | Specialists write ledger ownership fields directly | Agent imports host state and sets `active_task` | `owner_steal` | ownership |
| **A9** | Unvalidated model facts | E | Model numbers/tables accepted without code render / system-of-record | Chat shows a cost table the engine never produced | `false_save_claim`, `success_payload_rewrite` | substrate |
| **A10** | Second state machine per feature | S | Feature-local FSM competes with the turn-ownership ledger | Feature module keeps its own “stage” next to the ledger | `illegal_restart`, `lost_activity_recall`, `owner_steal` | ownership |
| **A11** | Shape as intent | M | Structural shape of paste treated as product intent | Dense numbered list auto-opens pack/builder without cognition label | `wrong_delivery_leaf`, `soft_name_misresolve` | delivery |
| **A12** | Shape overrides readiness | M | Geometry/density rubrics open or block paths against true readiness | “Looks complete” opens save while required ids missing | `wrong_delivery_leaf`, `cold_start_collapse` | authoring / delivery |
| **A13** | Context-pin / delivery-order hijack | S | Ambient memory or wrong delivery order steals the active leaf | Last listed workflow id hijacks a sticky draft | `ambient_pin_hijack`, `packaging_steal`, `wrong_delivery_leaf` | delivery |
| **A14** | Re-resolve after pin | S+E | Identity pin present but free text re-resolves as greenfield | User has workflow pin; system searches by name again | `pin_drop`, `named_item_misresolve`, `illegal_restart` | ownership / delivery |
| **A15** | Ambient last-read as sole authority | S | “Last thing we mentioned” drives delivery without owner/pin gates | Session cache of last id without phase check | `ambient_pin_hijack`, `owner_steal` | delivery |
| **A16** | Per-agent multi-turn glue | S | Agent-local multi-turn glue instead of host sole-continue kinds | Each specialist invents its own sticky flags | `owner_steal`, `lost_activity_recall` | ownership |
| **A17** | Fail-soft option laundry | D | After unclear, growing prose option menus instead of card + reasoner | “Reply accept/skip/use X/try again…” walls of text | under-render; cousin `fall_through_fabrication` | delivery |
| **A18** | Dispatch-order laundry | S+D | Growing suppress / call-order stacks instead of owner allow-table | `if open_X: skip_Y` piles | `wrong_delivery_leaf`, `owner_steal` | delivery |
| **A19** | Soft existence / unsealed transition | E+S | Existence or create claimed without thin-verify of registry id / open leaf | “We already have project X” with no id | `soft_existence_claim`, `false_save_claim` | substrate |

**Notes:**

- One A# → many modes is normal. 
- One mode → several A# cousins is normal. 
- **Ops** (turn stall, locks, classifier fail-open as pure infra) stay in SDK ops sections —
 promote to CAQ only if an **authority law** is needed.

---

## Failure modes (index)

Machine SoT remains the failure-mode registry (YAML). Human index — **Description** is
the user/ledger burn in one sentence.

| Slug (`id`) | Plain name | Plane | Description |
|-------------|------------|-------|-------------|
| `owner_steal` | Owner steal | ownership | Continue or delivery is taken by a **non-owning** leaf while sticky multi-turn work still holds the thread. |
| `pin_drop` | Pin drop | ownership | Thin identity (workflow/project/scenario id, name pin, pending ref) is **lost or ignored** so the next turn re-resolves as if identity were unknown. |
| `illegal_restart` | Illegal restart | ownership | A multi-gate stream is treated as **greenfield** without abandon or complete — midflight work is wiped or re-begun wrongly. |
| `lost_activity_recall` | Lost activity recall | ownership | After a detour, the system **cannot restore** the prior activity the user reasonably expects to resume. |
| `hollow_open` | Hollow open | delivery | The system claims to open or pin work but returns **no usable surface**. |
| `hollow_advance` | Hollow advance | delivery | A gate **advances** without opening the next non-empty product surface. |
| `wrong_delivery_leaf` | Wrong delivery leaf | delivery | The host answers with the **wrong specialist or product path** for the user’s act. |
| `draft_improve_to_ir` | Open mid-draft improve steals to IR | delivery | Mid-draft refine is hijacked into structure/IR as if the user asked to compile. |
| `finite_token_dual_gate` | Finite token dual-gate | delivery | A bare confirm/ordinal is legal for **two armed gates**; code resolves the wrong one. |
| `named_item_misresolve` | Named-item misresolution | delivery | A **named** inventory entity is resolved to the wrong row or wrong tool. |
| `soft_name_misresolve` | Soft-name misresolution | delivery | Free-text name matching under an armed list binds the wrong object. |
| `ambient_pin_hijack` | Context-pin hijack | delivery | Ambient last-read residue **names** a saved object and steals the turn from the real owner. |
| `domain_pick_misbound` | Armed pick misbound | delivery | While a pick is armed, free text is bound to the wrong stream instead of advancing the pick. |
| `packaging_steal` | Packaging steal | packaging | Concept / glossary / marketplace packaging **intercepts** active product work. |
| `intentional_glossary` | Intentional glossary detour | packaging | User **asks** for product knowledge; glossary is correct when resume policy holds. |
| `fall_through_fabrication` | Escaped into unconstrained chat | cognition | Code-owned path falls through so the model **invents** tables, ids, or next acts. |
| `compound_act_loss` | Compound-act loss | cognition | Primary + secondary request; secondary dropped or primary replaced by explanation-only. |
| `success_payload_rewrite` | Mutative success rewrite | substrate | After a mutative tool, payload/narrative no longer matches what code committed. |
| `false_save_claim` | False save claim | substrate | UI or prose claims **saved** when the registry/tool did not succeed. |
| `soft_existence_claim` | Soft existence claim | substrate | Dialogue claims a durable entity **exists** without registry **id** verification. |
| `cold_start_collapse` | Cold-start authoring collapse | authoring | Early authoring collapses into a dead end or wrong gate via shape-as-intent. |

Laws and ratchets: always read the registry entry for the slug.

---

## Adjacent but non-CAQ registries

| Registry | Description |
|----------|-------------|
| **Control-plane ops** | Classifier fail-open, locks, turn stall, hot-potato as runtime — not always authority law |
| **Infrastructure** | Outages, 5xx, queue, DB |
| **Dialogue thrash** | Ceremony loops without authority failure (reopen thrash, twin surfaces as hygiene) |
| **Raw tool / API error codes** | Runtime signals; graduate to CAQ only with law + ratchet |

---

## Worked example (diagnostic, not patch)

**User hit:** “5 sales + 4 engineers, help me size it” → system opens **agent TCO / cost**
instead of **project / team-sizing** workspace.

| Step | Description | Call |
|------|-------------|------|
| Doctrine | Project = staffing simulation workspace; cost = agent/workflow TCO | Keep product boundaries honest |
| Root | **M** — underspecified “size” bound to the wrong product leaf | Meaning authority leakage |
| Review smell | Overloaded vocabulary / shape-as-intent | “size” means two products |
| Anti-pattern | **A11 — shape as intent** (cousin); risk of **A4 — prompt exception piles** if “fixed” with phrase lists | Prefer semantic labels + code gates |
| Failure mode | `wrong_delivery_leaf` | Wrong delivery leaf |
| Plane | delivery | Host leaf selection |
| Seal | Strengthen **semantic** cost vs project labels in the turn router; **no** `looks_like_*` sole arbiter | Code policy + classifier enums |
| Ratchet | Prompt markers + path-faithful route test when sealed | Fails if cost steals project size again |

---

## Association with quality programs

Diagnostics (this sheet) **name the class**. Quality programs **grade and prove** it.
Do not collapse them into one doc or one harness — but the ladder must stay shared.

```text
 This taxonomy (diagnose)
 │
 ├─► CAQ + purity scoreboards grade: is the mode / A# sealed?
 ├─► Regression + contract suite prove: ratchet fails without the seal
 ├─► CI gates enforce: suite / baseline must not worsen
 └─► Eval (multi-turn / soaks) prove under live or frozen cognition
```

| Program | Description | Status (typical) | Uses this taxonomy how |
|---------|-------------|------------------|------------------------|
| **CAQ (Conversational Authority Quality)** | Named **failure modes** (slugs) with laws and intended ratchets — product/ledger burns, not “chat vibe.” Registry is the machine SoT for modes; CAQ docs explain process. | Living | Modes are the **failure-mode rung**; grade “is `pin_drop` sealed?” without reinventing M/E/S/D |
| **CAQ purity scorecard** | **Grades** each CAQ mode and related A# (sealed / known_gap / open) — a scoreboard, not a second law book | Living / host-specific boards | Pointer audit: grades map to taxonomy modes + A#; **does not redefine** the ladder |
| **Purity scoreboards** (living audits) | Broader product purity: ownership, product voice, LLM surface hydration, open authority — often board/lens grades (e.g. L19 voice, Board O delivery) | Living | When a burn reappears, **park a candidate** here only until law + ratchet exist; promote modes to CAQ registry when sealed |
| **Regression / contract suite** | Executable **ratchets**: unit/integration tests and contract modules that fail if a sealed class returns (prefer ledger/blocks/enums over golden prose) | Living | Name tests by **mode id / A#** where possible; taxonomy says *which* law the test proves |
| **CI** | Continuous integration gates: run the suite, optional **baseline/ratchet** (failures must not increase), lint/security gates | Living host CI; portable package ships tests adopters wire into *their* CI | Enforces regression ratchets; CI is not a new failure class — it is the **enforcement path** for seals |
| **Eval (multi-turn behaviour / soaks)** | **Evaluation** under non-deterministic cognition: multi-turn scripts, freezes, path-faithful soaks, optional staging rituals — “chat can look fine while ledger is wrong” | **Work in progress** for a single unified map (many hosts already have pieces: suite + freezes + soaks) | Taxonomy picks the **law**; eval proves it under multi-turn load. Not MMLU/LMSYS as ship gate; not LLM-as-judge as primary SoR |
| **Coding agent / implementer playbook** | Session checklist: diagnose before patch | Living in host | Forces ladder use **before** coding |

### How to read the table

| Question | Look at |
|----------|---------|
| What *kind* of authority failure is this? | **This taxonomy** (root → A# → mode) |
| Is that mode sealed in product? | **CAQ / purity scoreboards** |
| Will CI catch a re-burn? | **Regression suite + CI** (ratchet present and wired) |
| Does it still hold when the model is stochastic? | **Eval** (multi-turn / soak / freeze) — often partial; grow deliberately |

### Explicit gaps (honest WIP)

| Gap | Description |
|-----|-------------|
| **Unified eval map** | Many pieces exist (contracts, multi-turn runners, soaks) but a single **adopter-facing program** that ranks “when to add a unit ratchet vs freeze vs soak” is still maturing — treat **Eval** as first-class in the quality stack, not an afterthought. |
| **CI portability** | Public package ships **tests**; each host must attach them to CI. Monorepo hosts often have pre-push / baseline ratchets; not every adopter will. |
| **Scoreboard sprawl** | Prefer **one ladder** (this taxonomy) + **one mode registry** (CAQ YAML); purity boards **grade** and inventory surfaces — they must not invent parallel anti-pattern numbers. |

**A# reminder:** use **A11 — shape as intent** (id + short title). Full anti-pattern essays live in [SDK §1.6](conversation-control-plane-sdk.md#16-adoption-anti-patterns-engineering-doctrine--do-not-generate-these).

---

## License / packaging note

This document is intended for the **portable conversation-control-plane** package and
adopters of multi-turn conversational authority. Host-specific path names, internal
changelogs, and product-only scoreboards are omitted here; see the host monorepo for
implementation maps.
