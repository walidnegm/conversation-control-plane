# Conversation Control Plane

**Defensive engineering for non-deterministic systems.**

Most agent architectures fail in the same direction: they give the model
operational authority. It picks the tool, invents the plan, decides when work is
finished, and passes prose to the next agent as if prose were a work order. That
works in a demo and degrades in production, because a language model is not an
executive. It is an excellent *semantic parser* and an unreliable *operator*.

This package takes the opposite bet. The model is treated as a **fuzzy-to-structured
parser with no operational authority**: it proposes meaning, in a closed
vocabulary, and nothing else. Identity, arithmetic, state transitions, and the
question of who may act next belong to code.

> **Meaning is the model's; identity, arithmetic and state are code's.**

That single line is the whole doctrine. Everything below is its consequences.

It is not a novel idea so much as the place serious teams arrive at after
roughly six months of fighting dynamic agent loops in production — the point
where you stop asking the model to be reliable and start building a system that
is reliable *while containing* something that isn't. If you have already been
burned by an agent that confidently took the wrong action, this will read as
familiar rather than clever.

### The three layers, and what each is *not*

| Layer | What it is | What it is **not** |
|---|---|---|
| **Cognition** | One bounded classifier proposes enums and typed slots from free text. | **Not act selection.** It cannot verify an ID. Fuzzy matching grounds a *label* to a closed inventory — never "which tool". |
| **Control** | Tables plus `decide_turn`: who may run, is the act TERMINAL or CONTINUES, are slots and refs sufficient, does a sticky owner yield. | **Not a ReAct loop.** The model does not read a tool menu and guess. |
| **Host delivery** | The turn: finite chips, named doors, `decide_turn`, then a leaf or a handoff envelope. | Not a place for new `if`s. Each door should consult a table; an `if` added instead of a row is debt. |

**Navigation is not a central switch.** Graphs own navigation, control owns
admissibility, execution owns mutation. `next_act` must not become one giant
`switch` in the control plane.

### Instructions are not enforcement

The rule that does the most work here, and the easiest one to skip:

> **If an invariant is not an executable test, it does not exist.**

A system prompt that says "always confirm before sending" is a suggestion to a
non-deterministic component. A schema field that says `"Requires confirmation"`
is documentation. Neither is a control. In this architecture an invariant is a
row in a registry plus a ratchet in CI that fails when the row is missing — so
declaring a `CONTINUES` act with no reader breaks the build rather than
producing a hollow open at runtime.

This is also the most common way an otherwise-good agent system rots: a
declared rule that nothing enforces, discovered months later when the behaviour
it described was never actually happening.

### What this costs you

This architecture buys predictability with flexibility, and the trade is real.
If these costs do not sound acceptable, do not adopt it — the honest failure
mode of this doctrine is a team that pays them without wanting them.

- **Developer velocity.** Elsewhere a new capability is a `@tool` decorator and
  the model figures it out. Here it is a closed-vocabulary change: enum →
  grounding → registry row → door → deploy, and a published prompt if cognition
  must be able to *name* it. That friction is the point, and it is still
  friction. Prototyping is slower.
- **No emergent orchestration.** Because navigation is the ledger's kind and
  phase plus each specialist's own machine, the system cannot invent a novel
  sequence of tool calls to solve a problem nobody anticipated. It will refuse
  or ask. A dynamic agent might have improvised something useful.
- **Take-once is contention.** "The owner takes once" is idempotency, and under
  concurrency idempotency is locks. A busy multi-writer deployment will meet
  row contention and must serialize deliberately rather than hope.
- **Refusal has a UX cost.** Refusal being first-class is mathematically right
  and can be conversationally miserable. A system that halts on every soft
  ambiguity trains users to give up. Refuse on missing *authority*, not on every
  under-specified slot.

### A new act is a code change

Stated plainly because it is a product decision, not an oversight: **the tables
are a closed inventory, not decoration around a dynamic router.** A request the
vocabulary cannot name cannot be routed — only guessed at, which is the failure
this package exists to prevent. New capability is a row, a door, and a deploy,
not a hot-loaded tool list the model browses.

The minimum stations for one new named act, and what breaks if you skip each:

| Station | What you add | If you skip it |
|---|---|---|
| Cognition enum | the valid kind / act flag | the model cannot say it; prompt text is inert |
| Prompt rubric | published body, same session | environments run an old act set |
| Delivery mode | TERMINAL vs CONTINUES | a CONTINUES act with no reader is a hollow open |
| Host door | a registered reader | control returns "fresh" and the host never delivers |
| Claimant yield | the claimant's owned surfaces | other leaves fail open and steal the turn |
| Handoff | an `ACT_REGISTRY` row if another agent executes | prose travels as work; the agent says "you can do that in the editor" |
| Multi-turn | sole-continue kind + spec + status card | pin-resume failure and turn stealing |
| Tools | a `tool_registry` row | the agent cannot call the tool even when correctly routed |

Only tool *permission* is DB-dynamic. Conversation routing does not appear
because a row showed up in Postgres.

### Target law vs. the system you are reading about

Everything above is the **target law**. The reference host that inspired this
package implements that law *plus* a long gauntlet of `if` statements that
frequently short-circuits it. That gap is stated here rather than hidden,
because it is the honest shape of the problem: the protocol is
`claim → decide → handle → apply`, and a host is permitted to short-circuit
around it. That becomes a defect the moment "a kind is present" is treated as
"this turn continues" — which is precisely how orientation flows, recommendation
surfaces, and setup wizards have historically stolen turns from one another.

Read the tables as law. Read the gauntlet as debt.

---


> **LangGraph can absolutely persist conversation and agent state, route between
> agents, and resume execution. A Conversation Control Plane extracts a different
> state contract: product-level task ownership and *admissible conversational
> transitions* — which stay authoritative even when execution moves between
> graphs, agents, deterministic handlers, jobs, or humans.**

It does not merely *remember* continuity. It **enforces authority law**: what
work is foreground, who owns the turn, what state constrains it, and which
lifecycle transitions (`BEGIN` · `CONTINUE` · `COMPLETE` · `ABANDON`) are legal
right now — with a single writer and `COMPLETE` never conflated with `ABANDON`.

**If your whole product is one LangGraph, LangGraph may be enough.** Its
checkpointer persists thread state, resumes conversations, and supports
interrupts; its handoff pattern already shows `active_agent` being persisted
across turns to decide who handles the next interaction. You can model
`active_task`, `phase`, `awaiting` and pins in that state and drive handoffs from
it. That is a perfectly good architecture, and this SDK is not claiming a
deficiency LangGraph does not have.

The value shows up when a conversation **spans more than one execution world** —
multiple graphs, a second agent runtime, deterministic product surfaces, async
jobs, tools, or human approval steps. Then one question needs a single shared
answer:

> *What work is active, and what may happen next?*

Putting that answer inside one particular graph gets awkward when some of the
work isn't in that graph.

```text
   OPTION A — one runtime owns everything
   ┌──────────────────────────────┐
   │ LangGraph                    │
   │   execution                  │
   │   conversation authority     │   ← often sufficient
   └──────────────────────────────┘

   OPTION B — authority outlives any single runtime
   ┌──────────────────────────────┐
   │ Conversation Control Plane   │
   │   product task authority     │
   └──────────────┬───────────────┘
        ┌─────────┼──────────┬────────────┐
        ▼         ▼          ▼            ▼
    LangGraph  Agents SDK  host code   human step
```

Both are valid. The bet behind Option B is that **product-level continuity
outlives any single agent runtime**: if the pricing specialist moves from
LangGraph to the OpenAI Agents SDK next quarter, the product's task state should
not have to migrate from one execution ontology to another.

### On ledgers, precisely

LangGraph's checkpointer *is* a durable state ledger — it saves state per step,
keys it to a thread, and supports history, replay, inspection and resume. The
difference is not "we have a ledger and they don't." It is **which question the
store is authoritative for**:

```text
LangGraph checkpoint          Conversation Control Plane
"Where is this                "Why does this product task
 graph execution?"             own this turn?"
```

| | authoritative state of |
|---|---|
| **LangGraph checkpoint** | graph execution · thread state · which node runs next |
| **This ledger** | product task lifecycle · kind/phase · awaiting · pins · suspend/resume · admissible transition |

The **same Postgres** can hold a LangGraph checkpointer *and* this ledger —
different questions, not competing stores. The thesis does not require another
database; it requires another **authority abstraction**.

### …and this package is not only the ledger

The ledger is the system of record underneath, not the whole of what ships. The
package owns six seats of the turn pipeline — including **adjudication, policy
and lifecycle**, not merely durable storage:

| Seat | **This package** | **Your app** |
|---|---|---|
| **0 Hydration** | ledger / KindSpec / pins as the SoR the view is built from | builds the brief |
| **1 Semantic** | law: meaning → closed enums; free text never becomes authority directly | classifiers, enum *values*, schemas |
| **2 Adjudication** | `decide_turn`, sole writer, exclusive owner | which leaves are offered |
| **3 Policy** | gates, stickiness, foreign-deny shape, lifecycle | continuum edges, inventories |
| **4 Execute** | `TaskTransition` envelope, control-key stripping | LangGraph / tools / workers / SoR |
| **5 Delivery** | finite grammar when armed, fail-soft ban | product voice, chips, payloads |

> **SDK** = who owns the turn + what transitions are admissible + durable
> ownership SoR.
> **App** = what ops / kinds / surfaces / edges *mean* + how the product speaks.

Full write-up in [the seat table below](#contract-at-a-glance) and
[SDK §0.0.2](docs/conversation-control-plane-sdk.md#authority-adjudication-pipeline-sdk-seat).

Nor is a *thread* the same as a *task*. A thread is what LangGraph persists
checkpoints against; one conversation may carry several product tasks with
independent lifecycles:

```text
  thread: conversation_42
    ├── task_913   kind=cost_out         SUSPENDED
    ├── task_927   kind=workflow_build   ACTIVE
    └── bounded glossary detour          (no task)
```

You can build that in LangGraph state. The claim here is narrower and, we think,
stronger: **the task model is worth being a first-class contract independent of
whichever graph happens to execute it.**

### Topology vs product authority

This is the sharpest form of the distinction. A graph handoff naturally encodes
**topology** — *which node runs next*:

```text
active_agent = sales
        ↓
route to sales_agent node
```

The control plane encodes **product authority** — *what work is open, and which
deliveries are legal for it*:

```text
task_913
  kind    = cost_out
  phase   = pricing
  awaiting = approval
        ↓
  legal delivery choices
    ├── LangGraph pricing agent
    ├── deterministic pricing service
    └── human approval
```

The product task exists **above** the implementation topology. Concretely: when
the pricing specialist moves from

```text
Pricing Agent: LangGraph      →      Pricing Agent: OpenAI Agents SDK
```

the product's task state does not migrate from one execution ontology to
another. `task_913` is still `cost_out`, still in `pricing`, still `awaiting`
approval — only the executor changed. That property is the whole point of
keeping authority outside any single runtime, and it is worth exactly as much as
your application's heterogeneity: near zero if everything is one graph, a great
deal once it isn't.

```text
                       USER
                         │
                         ▼
              PRODUCT CONTROL PLANE
              task_913 · cost_out · pricing · awaiting approval
                         │  authorized work
          ┌──────────────┼───────────────┐
          ▼              ▼               ▼
      LangGraph      OpenAI SDK       host leaf
       workflow      specialist      deterministic
          │              │               │
          ▼              ▼               ▼
       Temporal         MCP            human
         job           server         approval
```

The question that layer answers: **which of these systems is the authority for
the user's ongoing product task?** Putting that inside one particular graph gets
less attractive as more of the work happens outside it.

Your application still defines what kinds of work exist — `checkout`,
`claims_review`, `workflow_build` — and which agents and tools perform it.

**Compose with these runtimes; do not replace them.** LLM proposes; code owns
the turn.

<sub>*Naming:* “Conversation Control Plane” is the architectural layer. This
repository is its portable open-source implementation, built around the ledger
as the authoritative projection and journal. It is more than storage —
`decide_turn`, `KindSpec`, transition validation, gates, claims, suspension and
the provenance boundary are all control-plane behaviour.</sub>

Who is foreground, what is pinned, when ownership may yield — portable across how
each turn is **run** (LangGraph · agent SDKs · Temporal · plain code · human operator).

Package: `conversation-control-plane` · **MIT** · [Bot0.ai](https://bot0.ai)

This package owns *who holds the thread* across turns and specialists — not graph
DAGs, not RAG, not model vendors. **Persistence is assumed** (your SQL store);
**DB-backed is not the USP** — portable authority semantics are.

**Optional sibling (proof, not a dependency):**  
[**Conjecture Behaviour Runner**](https://github.com/walidnegm/conjecture-behaviour-runner)
(CBR) — multi-turn freezes + named failure modes + **Quality Console** (`conjecture ui`)
when chat still looks fine and ledger law is wrong.  
**Adopt the plane** (this SDK) · **prove the plane** (Conjecture). Details:
[Public product family](#public-product-family-why-adopt-both).

---

## Contract at a glance

**Spec (lookup):** [docs/conversation-control-plane-sdk.md](docs/conversation-control-plane-sdk.md)  
**Golden turn + checklist:** [SDK — the golden turn](docs/conversation-control-plane-sdk.md#the-golden-turn--one-correct-turn-end-to-end) · [docs/turn-capability-lifecycle-checklist.md](docs/turn-capability-lifecycle-checklist.md)  
**Lifecycle diagram:** [docs/conversation-turn-lifecycle-diagram.md](docs/conversation-turn-lifecycle-diagram.md)  
**Host laws:** [docs/host-transition-discipline.md](docs/host-transition-discipline.md)  
**Authority diagnostics:** [docs/conversational-authority-diagnostic-taxonomy.md](docs/conversational-authority-diagnostic-taxonomy.md)  
**Optional multi-turn proof:** [Conjecture Behaviour Runner](https://github.com/walidnegm/conjecture-behaviour-runner) (sibling)  
Operating sheet: **ladder** (causal) vs **triage** (investigation order). Roots **M/E/S/D**
parallel (D = delivery *authority* leakage). Quality stack = CAQ/purity · named **ratchet**
≠ suite · CI · eval (WIP). **Sealed** = checklist, not “looks fixed.”

**The golden turn** (full write-up + worked rename: [SDK — the golden turn](docs/conversation-control-plane-sdk.md#the-golden-turn--one-correct-turn-end-to-end) ·
[checklist](docs/turn-capability-lifecycle-checklist.md)):

```text
free text → cognition → grounding → stream/task → authority
        → delivery leaf ── another agent ──▶ handoff (take-once) ──┐
        → execution ◀─────────────────────────────────────────────┘
```

Stages **0–6 + 5b**. Crossing to another agent is a stage. A `CONTINUES` act
without a named reader, typed slots, grounded refs, and take-once claim is
hollow. Per-stage failures: the [checklist](docs/turn-capability-lifecycle-checklist.md).

The **essay seats** below are who owns each concern on that same turn (this
package vs your app) — not a second pipeline
([SDK mapping](docs/conversation-control-plane-sdk.md#golden-turn-vs-essay-seats)).

**Turn pipeline seat** (full write-up: [SDK §0.0.2](docs/conversation-control-plane-sdk.md#authority-adjudication-pipeline-sdk-seat) ·
[adjudication note](docs/conversational-routing-authority-adjudication.md) ·
[§2.1.x](docs/conversation-control-plane-sdk.md#21x-extension-points-enums-kinds-surfaces-continuum)):

| Essay layer | **This package** (SDK) | **Your app** |
|-------------|------------------------|--------------|
| **0 Hydration** | Ledger / KindSpec / pins = SoR the View is built from | Builds the brief (`allowed_operations`, surface map) |
| **1 Semantic** | Law: meaning → closed enums, never free-text authority | Classifiers, op enum *values*, schemas |
| **2 Adjudication** | **`decide_turn`**, sole writer, exclusive owner, A18 allow-list *shape* | Which leaves / EXTRA rows |
| **3 Policy** | Gates, stickiness, foreign deny as tables + lifecycle | Continuum edges, family inventories, suppressions |
| **4 Execute** | `TaskTransition` envelope; strip control keys | LangGraph / tools / SoR / workers |
| **5 Delivery** | Finite grammar when armed; open-leaf arming; A17 fail-soft ban | Product voice, chips, continuum pin payload |

> **SDK** = who owns the turn + what transitions are admissible + durable ownership SoR.  
> **App** = what ops / kinds / surfaces / edges mean + how the product speaks.

```text
App hydrates View ──reads──► SDK ledger
App proposes enums ─────────► SDK adjudicates (decide_turn / owner / A18)
App tables (policy) ────────► SDK enforces shape
App/LangGraph executes ─────► SDK applies TaskTransition only
App delivers continuum ─────► SDK open-leaf / armed-grammar law
```

| Extension | SDK requires | App fills |
|-----------|--------------|-----------|
| Ops / enums | Schema-validated closed set | `SET_FIELD`… or product-act ids |
| Kinds | Registered streams + phase enums | Your product streams |
| Surfaces | Literacy for adjudication | Leaves, cards, chips |
| Continuum | Invite + same-turn pin + armed-only affirm | Edge rows + `send_text` |

The package does **not** hardcode any product continuum table or classifier field list.

### Host turn cycle

```text
claim_turn → decide_turn → handle (your leaf) → apply_transition → release_turn
```

- **Claim** — at most one live turn per conversation (per-row, not a global lock).
- **`decide_turn`** — pure code: who owns this turn given projection + router labels.
- **`handle`** — your agent / graph / job / human; **must not** write control keys.
- **…and when there is no leaf** — a host obligation, not this package. A turn
  whose meaning resolves to no handler has at least five distinct causes:
  cognition could not read it, the capability does not exist, state forbids it,
  the actor is unauthorized, or your own routing lost the door. **They must not
  collapse into one user-facing outcome.** Reporting a missing route as "we
  don't support that" hides your wiring defect from the user *and* from your
  telemetry. Deciding this needs a prompt registry and a tool/capability
  registry — both explicitly *not owned here* (see below) — so the verdict is
  yours to build; this package only tells you who owned the turn.
- **…and which SHAPE of leaf** — `handle` is one word for two things, and an
  act routed to the wrong one cannot finish. **TERMINAL**: one call answers the
  turn (list, inspect, open an editor when *opening is the answer*).
  **CONTINUES**: the call is a prerequisite and something must run after it —
  an agent loop, a planner, a second tool. Declare which mode each act needs
  and assert it (`delivery_mode_contract`); an undeclared act silently becomes
  terminal, which is how a stated graph edit was answered with *"Ready to work
  on X."* and nothing else — the opener had just created the very ledger task
  the agent was waiting for, so the edit cost two turns and the first
  instruction was thrown away. Nothing was broken in the ledger, the router or
  this package: the act was routed to a mode that could not complete it, and
  no contract could express the difference.
- **`apply_transition`** — sole writer of ledger ownership from a typed transition.
- **Release** — free the claim (incl. orphan steal / timeout paths).

### What the ledger stores (thin projection · L1)

| Field | Role |
|-------|------|
| `active_task` | Foreground task: `agent`, `kind`, `phase`, `awaiting`, pins / `pending_ref` |
| `suspended_tasks` | Detoured work still resume-able |
| `pending_switch` | Switch/Stay (or silent handoff) offer |
| `_control_revision` | Optimistic concurrency fence |
| turn claim | Live worker holder + TTL |

Domain working state lives in a **specialist store** behind `pending_ref` — not fat IR in control JSON.

### Journal (L2)

Queryable history: begin / continue / **complete** vs **abandon** (distinct), with
`task_id`, `command_id`, seq. Success and cancel are never the same clear path.

### Specialist → host boundary

`TaskTransition` is **lifecycle only** — not the whole multi-turn story. Stickiness
open/stay/close/none lives here; **where you are in the stream** lives on the same
envelope as closed `kind` + `phase` + `awaiting` (+ thin pins / `pending_ref`).
Hydration, continuum next-step, and delivery chips are **host** concerns — do not
add them as sixth/seventh transition types.

| Type | Meaning |
|------|---------|
| `TaskTransition.BEGIN` | Start a multi-turn kind (`phase`, `pending_ref`; arm `awaiting` if the leaf asks for a next act) |
| `CONTINUE` | Same task; optional phase / awaiting / thin payload update |
| `COMPLETE` | Success — release stickiness |
| `ABANDON` | User/reset bail — release stickiness (**≠** complete) |
| `NONE` | No task semantics (pure Q&A) |

Agents return `TaskTransition` (+ domain-only `context_updates`).  
`strip_control_keys(...)` removes control keys from agent payloads.  
**Only** host / `decide_turn` write `active_task` and siblings.

#### Deferred execution (not a sixth transition)

`TaskTransition` is lifecycle. When authorized execution **leaves this turn**,
the host returns `OperationOutcome.DEFERRED` with a `DeferredOperation`
(`operation_id`, `task_id`, `originating_turn_id`, opaque `execution_ref`).
The originating task stays alive (`BEGIN` / `CONTINUE`). Flattening
`DEFERRED` into `action=answer` is a **Control Plane contract violation**.

The SDK does **not** own poll / SSE / WebSocket, worker runtimes, chat-row
persistence, or card UX. Hosts map `execution_ref` to a job id, Temporal
workflow id, LangGraph run id, or equivalent. Depth:
[SDK §2.2](docs/conversation-control-plane-sdk.md#22-deferred-operation-continuity-portable-contract).

#### Worked product enums (illustrative — register *your* closed tables)

| Do | Don’t |
|----|--------|
| Document **example** kinds / phases / awaitings that worked | Add them as more `TaskTransition` members |
| Frame as **host product examples** / portable **shape** | Ship one product’s taxonomy as SDK law |
| Point to **closed registry** + **reject invalid** phase | Free-text phase diaries as ownership |

Portable law is the **shape** (closed registry + reject invalid phase), not these
product strings. Hosts that shipped sole-continue multi-turn used tables like:

| Axis | Examples that held up |
|------|------------------------|
| **kind** | `drafting` · `workflow_build` · `cost_out` · `cyber_risk_assessment` · `recommendation_setup` · `pattern_midflight` · `engagement_pack_plan` · `input_state_setup` |
| **phase** (per kind) | **cost_out:** `open` → `entity_pick` → `anchored` → `sizing` → `estimated` → `save_confirm` → `terminal` · **drafting:** `awaiting_domain` → `awaiting_details` → `drafting` → `refining` → `ready_to_build` · **cyber:** `anchor` → `discover` → `project` → `verify` → `score` → `complete` |
| **awaiting** (shared arm grammar) | `in_progress` · `user_confirm` · `finite_pick` · product twins e.g. `cost_profile_save_confirm` · `project_name` |

```text
BEGIN     kind=cost_out  phase=entity_pick  awaiting=finite_pick  pending_ref=…
CONTINUE  phase=sizing   awaiting=in_progress
CONTINUE  phase=save_confirm  awaiting=cost_profile_save_confirm
COMPLETE  → host clears stickiness
```

Post-complete **continuum** (invite next surface) is a host pin / product act — often
`NONE` or a **new** `BEGIN` of another kind — never `TaskTransition.CONTINUUM`.
Depth: [SDK §0.1.3](docs/conversation-control-plane-sdk.md#013-ledger-projection-vs-specialist-state-machine-what-is-internal-vs-shared).

### Multi-turn invariants (portable)

1. **Phase owns dispatch** — open vs continue vs pick phases are code gates.  
2. **Pin owns identity** — after pin, payload ids are authority (not ambient `last_read_*`).  
3. **LLM owns continue meaning** — labels / enums into the plane; not free-text ownership.  
4. **Finite grammar only when armed** — ordinals / approve only if a gate or menu was set.

### What this package does *not* own

Orchestration graphs · durable job infra · prompt registries · tool/MCP schemas ·
model memory · model vendors · poll / SSE / WebSocket · chat-row persistence ·
card UX. Compose with them; do not re-implement them here. **Deferred
continuity** (task still alive + opaque `execution_ref`) *is* this package;
the host experience of observing / persisting / rendering the result is not.

Full anti-pattern library (**A1 — parallel ownership flags** … **A19 — soft existence**):  
[SDK §1.6](docs/conversation-control-plane-sdk.md#16-adoption-anti-patterns-engineering-doctrine--do-not-generate-these).  
Diagnostic ladder + quality programs: [diagnostic taxonomy](docs/conversational-authority-diagnostic-taxonomy.md).

### Public product family (why adopt both)

Real multi-turn products fail when **chat looks fine** and **authority is wrong**. One package
cannot own every proof surface without becoming a product host. Split deliberately:

| Public package | Value you get |
|----------------|---------------|
| **This package** (control plane) | Turn ownership SoR · `decide_turn` · sole writer · multi-turn stream · A1–A19 · **cognitive seat** (hydrate…adjudicate…deliver) |
| **[Conjecture Behaviour Runner](https://github.com/walidnegm/conjecture-behaviour-runner)** | **Named failure modes** · planted FAIL · multi-turn freezes · **Quality Console** (`conjecture ui`) — cockpit for laws · seals · proof debt |

| Need | Use |
|------|-----|
| Wire ownership into my host | This repo |
| Named mode + CI proof for owner_steal / hollow_open / continuum unarmed affirm | Conjecture (`incidents/registry.yaml` · `CATALOG.md`) |
| Navigate programs / surface×law / laundry multi-lens after a soak | Conjecture **Quality Console** — [CBR README](https://github.com/walidnegm/conjecture-behaviour-runner#quality-console--conversational-agentic-quality) |
| Architecture without product laundry | [Authority adjudication note](docs/conversational-routing-authority-adjudication.md) |

**Together:** adopt the plane (this SDK) + prove the plane (Conjecture + console).  
**Do not bloat this package** with product continuum edge tables, catalog families, or
full host CAQ YAML. Ship **shape + law + anti-patterns** here; ship **mode slugs + proofs +
console** in Conjecture. Host monorepos keep the full private D1 registry.

---

## Quickstart (5 minutes)

```bash
git clone https://github.com/walidnegm/conversation-control-plane.git
cd conversation-control-plane
pip install -e ".[dev]"
pytest tests/ -q
python examples/e2e_host_loop.py
```

```python
from conversation_control_plane import (
    TurnPlan,
    TaskTransition,
    strip_control_keys,
    get_kind_spec,
    decide_turn,
)

# Host: claim → decide_turn → agent.handle → apply_transition → release
# Specialists return TaskTransition; strip_control_keys on agent context_updates.
```

Optional specialist shape: [examples/cyber_risk_assessment/](examples/cyber_risk_assessment/).  
Wrap sketches: [examples/integrations/](examples/integrations/).

---

## Where it sits (compose once)

This package is the **authority kernel** of a larger architecture — not the whole
of it. The layers above it interpret language; the layers below it execute work.
It owns the part in between: *who may act, on what, right now.*

```text
   PRODUCT SEMANTIC MODEL          your app
   what acts, objects and concepts exist
              │
              ▼
   TURN COMPOSITION                your app  ·  reference_host/
   free text → acts, entities, references,
   modifiers, declared semantics
              │
              ▼
   SEMANTIC GROUNDING              your app  ·  reference_host/
   resolve references against state;
   bind declarations to THIS turn
              │
              ▼
   STATE ADJUDICATION              shared boundary
              │
   ╔══════════▼═══════════════════════════════╗
   ║  OPEN-SOURCE SDK — authority kernel      ║
   ║                                          ║
   ║  decide_turn · KindSpec · task lifecycle ║
   ║  ownership · gates / pins · transitions  ║
   ║  ledger (L1 projection · L2 journal)     ║
   ║  suspend / resume · single-writer        ║
   ╚══════════╤═══════════════════════════════╝
              │ handle dispatches into
              ▼
   AGENT / HOST LEAF               your app
   LangGraph · Agents SDK · CrewAI · Rasa ·
   ChatKit · Temporal · plain Python
              │
              ▼
   SKILL / TOOL / MCP              your app / runtime
              │
              ▼
   DOMAIN SYSTEM OF RECORD         your enterprise
```

**Bring your own product semantics and execution runtime.** The hard portable
part is the deterministic authority substrate in the middle — that is what this
package is, and the only thing it claims to be.

`reference_host/` shows the seam above the kernel (`TurnSemantics` → grounding →
`GroundedTurn` → `decide_turn`). It is a reference architecture, **not** a
dependency: nothing in `conversation_control_plane` imports it, and you are
expected to replace it. See [`examples/declared_vs_inferred.py`](examples/declared_vs_inferred.py).

| Layer | Owns |
|-------|------|
| **This package** | Foreground task, pins, phases, COMPLETE≠ABANDON, turn claim |
| **Run leaf** | Nodes, tools, crew steps, job activities *inside one execution* |
| **Hosted chat / dialogue** | Vendor session (ChatKit, Rasa tracker, …) if you stay single-stack |
| **Checkpointer / workflow state** | Mid-run execution state — not chat-thread multi-task law |

Same Postgres can hold a LangGraph checkpointer **and** this ledger: different questions
(graph step N vs why this **turn** routed here).

Deep ecosystem comparison: [SDK §0](docs/conversation-control-plane-sdk.md#0-value-proposition--conversational-control-in-a-layered-stack) · [§14](docs/conversation-control-plane-sdk.md#14-ecosystem-layering--langgraph-crewai-temporal-and-the-control-plane).

---

## On-ramp

### Design principles

| Principle | Contract |
|-----------|----------|
| **Not the agent** | Execution leaves stay yours; ledger owns thread authority. |
| **Authority is deterministic** | No model call on claim / fence / pure `decide_turn` / COMPLETE≠ABANDON. |
| **Cognition ≠ execution** | LLM proposes enums; code owns transitions and structure. |
| **Single writer** | `TaskTransition` only; agents never import `ledger.py`. |
| **Thin projection** | Pins + phase + `pending_ref` — no fat domain artifacts in control JSON. |
| **Pin owns identity** | After pin, ids win; ambient reads are not sole authority. |
| **Per-conversation locks** | Short TX; LLM work off the row lock. |
| **Finite grammar when armed** | Menus/gates only when code set them this turn. |

### Specialist checklist

You own the product phase machine; the ledger only records honest transitions.

| Step | Shape |
|------|--------|
| Register a **kind** | Closed enum + `KindSpec` phases |
| **begin_task** | Host assigns `task_id` |
| **Pin** identity | Typed ids on thin payload |
| **Phase owns dispatch** | No re-resolve by name every continue |
| **Honest surface** | CTA matches current phase (no “next step” while blocked) |
| Return **BEGIN / CONTINUE / COMPLETE / ABANDON / NONE** | Never raw control keys |

Helpers: `multi_turn_stream_contract.py`. Scaffold: [cyber_risk_assessment](examples/cyber_risk_assessment/).

### Minimal host setup

1. Map chat store → control slice (`active_task`, suspended, switch, revision, optional journal).  
2. Install package; host loop as above.  
3. Register each multi-turn `KindSpec`; first sticky turn **begin**.  
4. Five tests: resume · complete · abandon≠complete · no auto-switch · no re-resolve after pin.  
5. [Host transition discipline](docs/host-transition-discipline.md) — reorient ≠ COMPLETE.

### Coding-agent kickoff (paste)

```text
Integrate Conversation Control Plane (turn-ownership ledger). NOT a LangGraph/
Temporal/ChatKit replacement. Compose: claim → decide_turn → handle → apply → release.

Repo: https://github.com/walidnegm/conversation-control-plane
Spec: docs/conversation-control-plane-sdk.md (§2.1 multi-turn, §3.1 concurrency, §5 invariants)
Laws: docs/host-transition-discipline.md

Rules: classifiers propose enums; decide_turn enforces. Specialists return TaskTransition
only. Thin projection (pins + phase + pending_ref). COMPLETE ≠ ABANDON. No phrase laundry
for NL meaning. No **A1 — parallel ownership flags**. No ambient last-read as sole identity after pin.
Diagnose authority burns with docs/conversational-authority-diagnostic-taxonomy.md before patching.

Deliver: (1) port ledger + decide_turn to our store (2) one sole-continue KindSpec
(3) five tests: resume, complete, abandon≠complete, no auto-switch, no re-resolve after pin.
```

Longer bootstrap: SDK [§1.1](docs/conversation-control-plane-sdk.md#11-adopter-brief-copy-to-your-coding-agent).

---

## Compared with durable execution (Temporal, Step Functions, Inngest)

The control and host layers describe a domain-specific implementation of
durable execution, and the overlap is not accidental.

**Shared philosophy.** Temporal's core thesis is that workflow logic must be
strictly deterministic; this doctrine says the same thing about the
conversational layer. Temporal passes strongly typed payloads between
activities; this package requires slots to become grounded refs before an act
crosses an agent boundary. Temporal's execution history makes retries safe;
"the owner takes once" is the same guarantee against duplicate mutation.

**Where it diverges.** Temporal is a generic primitive; this is a conversational
OS. Temporal has no opinion about a user turn, a chip, or the difference between
a TERMINAL and a CONTINUES act — and it deliberately shouldn't. It also has no
cognition layer: it will execute a graph faithfully, but something still has to
decide *which* graph the user meant, from prose, and that is the part this
package governs.

**Where Temporal is straightforwardly better.** Versioning. Temporal runs V1 and
V2 of a workflow concurrently with first-class version gates. The host pattern
here has a long gauntlet of `if` statements where those distinctions would, in a
Temporal deployment, be cleanly separated workflow definitions. If your problem
is mostly orchestration versioning and only incidentally conversational, use
Temporal and put this doctrine's ideas *inside* it.

The reason this exists as its own thing is narrow: agent frameworks index on
model autonomy, which fails in production; durable execution engines index on
backend orchestration, which ignores fuzzy intent, turn ownership, and
human-in-the-loop yields. The gap between those two is where conversational
products actually break.

---

## When to adopt

**Adopt when** the conversation spans more than one execution world — several
graphs, a second agent runtime, deterministic product surfaces, async jobs, or
human approval — and they all need one shared answer to *what work is active and
what may happen next*. Also when you need SQL-auditable ownership, hit stuck
sessions / double-writers, or want to swap a specialist's runtime without
migrating product state.

**Skip when one runtime already owns everything.** If your whole product is a
single LangGraph — all agents are nodes, all handoffs are edges, all state is
graph state — then LangGraph is very likely already a good control plane for it,
and this SDK is an abstraction you do not yet need. Same if Temporal already owns
the orchestration you care about, or you are prototyping single-agent flows.

That is a real "don't adopt this" answer, and it is meant sincerely: the
abstraction earns its keep when authority must **outlive** any single runtime,
not before.

Adoption cost: moderate thin host loop; **0 inherent LLM calls** on the authority path.

---

## What the code actually pins

| Shipped | Not claimed / open |
|---------|-------------------|
| Projection + journal shapes; COMPLETE vs ABANDON | Formal load benchmark numbers |
| `decide_turn`, `strip_control_keys`, `TaskTransition` | One-line full SQL host `pip` productization |
| Revision fence + `command_id` (with SQL host) | Every host path fail-closed out of the box |
| KindSpec + multi-turn stream helpers | `ccp inspect` CLI / session viewer UI |
| `pytest` + `e2e_host_loop` | PyPI production SLA |

---

## Repository layout

| Path | Role |
|------|------|
| [`src/conversation_control_plane/`](src/conversation_control_plane/) | **Installable package — the authority kernel** |
| [`reference_host/`](reference_host/) | **Reference architecture, NOT installed.** Turn composition + grounding above the kernel. Replace it. |
| [`docs/`](docs/) | SDK contract + lifecycle + host discipline |
| [`examples/declared_vs_inferred.py`](examples/declared_vs_inferred.py) | User declaration vs agent inference, end to end |
| [`examples/e2e_host_loop.py`](examples/e2e_host_loop.py) | Runnable host + COMPLETE≠ABANDON demo |
| [`examples/cyber_risk_assessment/`](examples/cyber_risk_assessment/) | Optional specialist scaffold |
| [`examples/integrations/`](examples/integrations/) | Wrap sketches (not full E2E products) |
| [`tests/`](tests/) | Portable contract tests |

**The line between the two top rows is the point.** `src/` is portable law:
install it, depend on it, expect it to be stable. `reference_host/` is one
worked answer to *"what must become true before the kernel is asked to decide"* —
useful to read, not meant to be adopted. Nothing in `src/` imports it.

---

## Maintainers

Publish from the Bot0 monorepo:

```bash
./scripts/publish_control_plane_public_repo.sh --repo /path/to/clone --push
```

---

## License

MIT — see [LICENSE](LICENSE).
