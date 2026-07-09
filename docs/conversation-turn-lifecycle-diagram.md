---
name: Conversation Turn Lifecycle — the ledger-pinned flow (diagram)
description: One diagrammed map of a single Bot0 chat turn — claim → perception → pre-decide gauntlet → decide_turn → post-decide prose intake → specialist dispatch → ledger write → release. Fourth of the four canonical architecture documents (2026-07-07).
type: reference
date: 2026-07-07
related:
  - conversation-control-plane-sdk.md
  - 
  - 
---

# Conversation Turn Lifecycle — the ledger-pinned flow

**What this is.** A single map of one chat turn through **your host entrypoint** (HTTP handler, SSE `chat`, worker) and the portable `conversation_control/` package. Bot0's reference host is `api/services/host chat module (monorepo)::chat` — **monorepo only**, not shipped here. The diagram shows where perception, `decide_turn`, detours, and ledger writes belong.


**Honest framing.** This documents the flow **as it is**, not the idealized "one router → `decide_turn`" version
in the [SDK contract](conversation-control-plane-sdk.md). The pre-decide **gauntlet** is real: several fast-paths
and detours can short-circuit before `decide_turn` runs. Retiring that competition (detours → ledger tasks, one
authoritative decision) is the  work;
this diagram is the honest baseline it works against.

**Ownership (2026-07-09).** Who manages memory vs front door vs multi-agent ownership is **not** siloed in this
diagram alone — see [SDK §0.1.2](conversation-control-plane-sdk.md#012-who-owns-what--front-door-multi-agent-ownership-memory-expectations)
and .

**One-liner:** *The ledger is the control plane’s state of record; the control plane is the rules and code
that read/write that state and pick the delivery leaf — one meta-layer, not two products.*

**Rule:** host short-circuits that ignore sealed `task_intent` / exclusive owner (e.g. early cost sole-continue)
are **control-plane delivery bugs**, not agent tool-choice bugs.

**Multi-turn sole-continue (does not change this diagram’s stage order):** once
`active_task.kind` is a sole-continue stream and an entity is **pinned**, later turns stay on the same
path — **phase-gated** entity resolve, **ledger pins** for identity, **LLM** for continue meaning
([SDK §2.1 multi-turn stream](conversation-control-plane-sdk.md#21-multi-turn-stream-contract-every-sole-continue-kind)).
This is dispatch discipline inside active-flow continue, not a second state machine.


**Cognition / execution on this map (2026-07-07).** ▨ blocks emit labels (intent, `user_wants`,
`authoring_maturity`, gaps). ▣ blocks validate enums and run transitions. **Semantic readiness** (how good is
this prose?) is ▨→▣ via `enrich_intake_assessment` — rubric in the published classifier prompt, execution in
code (,
[SDK §11.4](conversation-control-plane-sdk.md#114-classifier-rubric-ownership-prompt-library-pattern)). **Structural
readiness** (SQL counts, IR validators, finite step-list shape) stays ▣ throughout.

---

## 1. The turn lifecycle (top to bottom)

Legend: **▨ = LLM cognition** · **▣ = code / finite-grammar / ledger-state** · **⚡ = short-circuit exit (skips
`decide_turn`)** · **◆ = the single authoritative decision**.

```mermaid
flowchart TD
  MSG["User message — SSE /chat"] --> CLAIM

  CLAIM{"▣ claim_turn<br/>one _turn_claim per conversation"}
  CLAIM -->|busy| REJECT["⚡ 409 conversation_turn_in_flight<br/>reject, don't queue"]
  CLAIM -->|claimed| GRD

  GRD{"▨ Guardrail — check_message"}
  GRD -->|blocked| GBLK["⚡ safety refusal"]
  GRD -->|ok| GA

  subgraph GA["Pre-decide gauntlet — each may ⚡ short-circuit (finite-grammar / ledger-state / own bounded LLM)"]
    direction TB
    G1["▣ catalog_handoff — FE button payload"]
    G2["▣ domain_gate_pick — finite pick + ledger phase"]
    G3["▨ ir_gate_role_proposal — classify_propose_roles"]
    G4["▣ authoring_gate_proceed — finite yes/no/accept at gate"]
    G5["▨ ir_confirm — classify_ir_gate_turn"]
    G6["▣ prose_intake_early_enqueue — structural shape/length"]
    G1 --> G2 --> G3 --> G4 --> G5 --> G6
  end
  GA -->|a gate owns the turn| SHORT
  GA -->|none owns| PERC

  subgraph PERC["Perception — cognition (▨) then code authority (▣)"]
    R1["▨ unified router — classify_unified_turn<br/>→ UnifiedTurnSignal<br/>(user_wants, authoring_maturity, missing_segments)"]
    AUTH["▣ authority passes on signal<br/>prose_intake · drafting_signal · product_concept · gate_proceed · IR review"]
    R2["▣/▨ intent router L0–L4 — bot0_intent_router<br/>→ IntentRoute"]
    R1 --> AUTH --> R2
  end
  PERC --> PICK

  subgraph PICK["Finite-grammar picks + reset (▣, LLM-arbitrated on miss)"]
    K1["▣ reset gate — literal set OR hint + LLM reset_request"]
    K2["▣ pending picks — scorecard / discovery / workflow — #id or number"]
    K3["▣ gate-continue route synth — code-owned IntentRoute"]
    K1 --> K2 --> K3
  end
  PICK -->|resolved| SHORT
  PICK -->|else| DECIDE

  DECIDE{"◆ decide_turn — AUTHORITATIVE DISPATCHER<br/>precedence · continue-resumes · Switch/Stay · hot-potato guard<br/>SINGLE WRITER of control keys → TurnPlan"}
  DECIDE --> POST

  subgraph POST["Post-decide ladder — SDK §2.1 discovery detour precedence"]
    P0["◆ STAGE_FRONT_DOOR_DELIVERY<br/>scorecards · orientation · discovery detours<br/>delivery_order_contract · decide_turn supersede"]
    P0a["▣ active-flow continue<br/>realization_intake · outcome_value_setup<br/>only if active_flow_handler_must_yield is false"]
    P1["▣ authoring gates · product how-tos<br/>same yield guard"]
    P2["▨ orientation demotion · generic discovery demotion"]
    P3["▨ concept gate — grounded glossary/how-to"]
    P4["▣/▨ prose intake lane — §9 readiness gauntlet"]
    P0 --> P0a --> P1 --> P2 --> P3 --> P4
  end
  POST -->|prose intake owns turn| SHORT
  POST -->|else| DISP

  DISP["▨ Dispatch specialist<br/>ConversationalAgent.handle_turn → TaskTransition"]
  DISP --> LED

  LED["▣ Ledger write — decide_turn only<br/>active_task / suspended_tasks / pending_switch / pending_question<br/>+ _control_revision++ + platform event"]
  LED --> REL
  SHORT["⚡ short-circuit answer"] --> REL
  REL["▣ release_turn — finally<br/>+ persist 3-hop routing trace on the message"]
```

**Reading it:** perception (guardrail + unified router + intent router) only *proposes*. The gauntlet and the
finite picks can answer the turn themselves (⚡) — that's the competition. When none of them own the turn,
`decide_turn` (◆) is the one place that reads the ledger, applies precedence, and **writes** the control keys.
Every path — short-circuit or full — ends by releasing the claim and persisting the routing trace.

---

## 2. Perception — the intent router (L0–L4)

Cheapest signal first; the LLM (L3) is the arbiter for anything genuinely ambiguous. Layers are precedence
stages inside `bot0_intent_router.py`, surfaced in every routing trace as `layer`.

```mermaid
flowchart TD
  Q["User message + context"] --> L0
  L0{"L0 — sticky session<br/>▣ reads active_task / agent_type / idle clock"}
  L0 -->|active + not broken| STAY["stay on sticky agent"]
  L0 -->|no sticky| L1

  L1{"L1 — explicit trigger<br/>▣ regex CANDIDATE"}
  L1 -->|hit| ARB["▨ LLM arbitrates (candidate only)"]
  L1 -->|ordered step list| STRUCT{"▣ l2_structural candidate"}
  STRUCT -->|LLM confidence ≥ 0.85 disagrees| ARB
  STRUCT -->|no strong veto| WB["workflow_builder (structural accelerator)"]
  L1 -->|miss| L2

  L2{"L2 — pasted-content shape<br/>▣ roster / sequence signatures"}
  L2 -->|strong signal| ARB
  L2 -->|miss| L25

  L25{"L2.5 — pure-social<br/>▣ hi/thanks, ≤24 chars, not sticky"}
  L25 -->|match| SOCIAL["bot0 (skip L3)"]
  L25 -->|miss| L3

  L3["L3 — ▨ LLM classifier<br/>primary NL cognition"]
  L3 -->|unclear| L4
  ARB --> OUT["IntentRoute"]
  L3 --> OUT
  L4["L4 — ▣ safe default → bot0 (fail-closed)"] --> OUT
```

> `decide_turn` may still **override** the router's live route (precedence, continue, hot-potato). The trace then
> shows `layer: turn_plan:<mode>`.

---

## 3. `decide_turn` — the authoritative decision

The single writer. It takes the router signal + the DB-authoritative ledger and returns a `TurnPlan`; the ledger
write is its exclusive right (specialists only *declare* `TaskTransition`).

```mermaid
flowchart TD
  IN["router signal + get_control_state (DB)"] --> C0
  C0{"reset confirmed?"}
  C0 -->|yes| RST["complete/clear active_task → bot0"]
  C0 -->|no| C1

  C1{"pending_switch open + reply accepts/declines?"}
  C1 -->|accept| SW["resolve_switch → suspend_active + begin new"]
  C1 -->|decline / stale TTL| C2
  C1 -->|no pending| C2

  C2{"active_task mid-flight + turn is continue/ambiguous?"}
  C2 -->|yes| RESUME["◆ RESUME active_task<br/>(a flaky handoff cannot auto-steal)"]
  C2 -->|no| C3

  C3{"router proposes a DIFFERENT agent?"}
  C3 -->|would A→B→A bounce| HP["hot-potato guard →<br/>bot0 detour (hot_potato_guard)"]
  C3 -->|clean switch| PROP["propose_switch → pending_switch (Switch/Stay)"]
  C3 -->|same agent| DISPATCH

  RESUME --> DISPATCH
  PROP --> DISPATCH
  HP --> DISPATCH
  DISPATCH["TurnPlan.agent → dispatch + ledger write"]
```

Precedence in one line: **reset > switch-reply > continue-resumes > hot-potato-guard > propose-switch >
same-agent dispatch.** "Continue resumes" beating a flaky handoff classifier is the load-bearing invariant
(§5/§6 of the SDK contract).

---

## 4. The ledger state model (what "ledger-pinned" means)

The control slice lives on `conversations.context` (JSONB). `_CONTROL_KEYS`
([ledger.py:274](../../api/services/conversation_control/ledger.py#L274)) = `active_task`, `suspended_tasks`,
`pending_switch`, `pending_question` (+ transitional `advisor_active` / `pipeline_step` / `create_flow_state`,
being retired). Meta fields: `_control_revision` (monotonic), `_turn_claim` (holder + heartbeat + TTL),
`_handoff_trace` (bookkeeping, not a control key).

```mermaid
stateDiagram-v2
  [*] --> Idle
  Idle --> Active: begin_task(agent, kind, payload)
  Active --> Active: update_phase(phase, awaiting)
  Active --> Suspended: suspend_active (on handoff)
  Suspended --> Active: resume_task (return path)
  Active --> PendingSwitch: propose_switch(to)
  PendingSwitch --> Active: resolve_switch = stay
  PendingSwitch --> Suspended: resolve_switch = switch (suspend prior)
  Active --> Idle: complete_task (terminal — clears active)
  PendingSwitch --> Idle: pending_switch TTL expires
  Suspended --> Idle: suspended_tasks TTL expires

  note right of Active
    active_task = {agent, kind, phase,
    payload, pending_ref}
    Cross-turn working memory lives in
    kind + payload — never parallel
    *_active/_phase/_state flags
  end note
```

Every write bumps `_control_revision` and emits a platform event, so "why did routing choose X, and when?" is a
SQL query, not a graph-checkpoint deserialization. Finite picks (numbered menus) live in `pending_question`, not
free-text re-inference.

---

## 5. The hot-potato (ping-pong) guard

A→B→A bounce burns tokens and confuses users. `handoff_guard.py` records `_handoff_trace` and `decide_turn`
blocks the immediate bounce back.

```mermaid
sequenceDiagram
  participant U as User
  participant DT as decide_turn
  participant HG as handoff_guard
  participant A as Agent A
  participant B as Agent B
  U->>DT: turn 1
  DT->>A: dispatch (A owns)
  A-->>DT: TaskTransition → hand to B
  DT->>HG: append_handoff_trace(A→B)
  DT->>B: dispatch (B owns)
  B-->>DT: TaskTransition → hand back to A
  DT->>HG: would_ping_pong(B→A)?
  HG-->>DT: YES (A→B→A)
  DT-->>U: bot0 detour (hot_potato_guard) — bounce blocked
```

Complementary guards on the same class of loop: Switch/Stay confirmation (no silent bounce), `suspend_active`
(a return path without re-inferring from text), and `pending_switch` TTL (stale offers expire).

---

## 6. The three-hop routing trace (observability)

Every turn persists one trace object (`route_data.routing` on the message; also streamed live and carried on
async-job results). This is the ledger's audit companion.

```mermaid
flowchart LR
  H1["Router (L0–L4)<br/>router_layer · router_intent · confidence"]
    --> H2["Control plane (decide_turn)<br/>mode · plan_summary · intent_source · reason"]
    --> H3["Executor<br/>agent · executor · dispatch · capability_key · skill_key"]
```

A short-circuit exit shows up as `plan_summary: 'Skipped decide_turn; <dispatch> short-circuit'` — the literal
fingerprint of the gauntlet competing with the authoritative decision.

---

## 7. Stage → portable anchor

> **Bot0 reference:** the monorepo diagram maps these stages to `api/services/host chat module (monorepo)::chat` line anchors
> for internal debugging. Adopters implement the **same stage order** in their host entrypoint; only
> `conversation_control/` modules in `reference/` are portable.

| Stage | Portable anchor | Kind |
|---|---|---|
| Turn claim / release | `ledger.claim_turn` / `release_turn` / `renew_turn_claim` | ▣ serialize |
| Guardrail | **Your** HTTP/chat boundary (auth, rate limit, safety) | ▨ safety |
| Pre-decide gauntlet | **Your** application layer (optional finite picks / gates) | ▣/▨ ⚡ |
| Unified router signal | **Your** bounded classifier → enums | ▨ perception |
| Router authority passes | `apply_unified_router_authorities` pattern (host-owned) | ▣ execution on signal |
| **decide_turn** | `decide.decide_turn` | ◆ authoritative |
| **Front-door delivery** | `delivery_order_contract` + host dispatch | ◆/▣ — **before** active-flow continue |
| Active-flow continue | Specialist `handle_turn` paths | ▣ — gated by `active_flow_handler_must_yield()` |
| Post-decide detours | Host discovery/orientation handlers | ▨/▣ |
| Ledger control keys | `ledger.py` | ▣ state |
| Hot-potato guard | `handoff_guard.py` | ▣ |
| Routing trace | `route_data.routing` per [SDK §11.1](conversation-control-plane-sdk.md#111-intent-router-layers-l0l4-and-per-turn-routing-trace) | observability |

---

## 8. The one thing to keep true

`decide_turn` (◆) is the **single writer** of the control keys and the **sole authoritative dispatcher**. Every ⚡
short-circuit in §1 that answers a turn *without* passing through it is a competing arbiter — acceptable only when
it (a) reads ledger/finite-grammar/structured state, not free-text meaning, and (b) leaves the ledger consistent.
The map exists so new fast-paths are added with eyes open: a detour that decides meaning and skips `decide_turn`
is the bug class (`Skipped decide_turn` traces, stale mirrors, orientation loops) this whole layer is hardening
against.

**2026-07-08 addendum — discovery detour precedence.** [SDK §2.1 discovery detour precedence](conversation-control-plane-sdk.md#discovery-detour-precedence-delivery-order-invariant):
`decide_turn` supersedes active guided flows when `discovery_kind` ∈ `FRONT_DOOR_DETOUR_KINDS`;
the chat entrypoint delivers front-door answers (`STAGE_FRONT_DOOR_DELIVERY`) **before**
ledger-first continuations. New handlers must call `active_flow_handler_must_yield()` — not
ad-hoc `_plan_mode != "detour"` copies. Ratchet: `test_delivery_order_contract.py`.

**2026-07-08 addendum — grounded glossary / concept gate (CAQ-15).** [SDK §2.1 grounded glossary](conversation-control-plane-sdk.md#grounded-glossary--concept-gate-mid-authoring-detour--caq-15):
retrieval-grounded definitional asks deliver via `concept_gate` on the post-decide ladder
(`DETOUR_DELIVERY_ORDER_TABLE` row `concept_gate`) **before** resume/orientation, scorecards
inventory, and prose intake. Render: `glossary_concept` block + code-owned intro.

**Readiness is not one thing.** Semantic intake readiness belongs in ▨; shape rubrics are ▣ fail-soft fallback only when the router did not assess — see [SDK §11.4](conversation-control-plane-sdk.md#114-classifier-rubric-ownership-prompt-library-pattern).

---

## 9. Host-specific intake (monorepo detail)

Bot0's prose-intake and readiness merge (`enrich_intake_assessment`, `apply_strength_rubric`, …) live in the
monorepo host — not in the portable `reference/` slice. Adopters: **semantic readiness in classifiers** (▨),
**gates/transitions in code** (▣); see [SDK §11.4](conversation-control-plane-sdk.md#114-classifier-rubric-ownership-prompt-library-pattern)
and [SDK §2.1](conversation-control-plane-sdk.md#21-integration-guardrails-portable-contract).

---

## 10. Is this a LangGraph? (honest answer)

**Semantics, not a framework mandate.** The diagrams describe control-plane behavior you can implement
imperatively (`decide.py` + `ledger.py` in `reference/`) or optionally host as LangGraph nodes later — the
**contract** (single writer, cognition → execution split, explicit ledger state) stays the same.

| Layer | This SDK | LangGraph (optional) |
|---|---|---|
| **Control plane** (who owns the turn?) | Ledger + `decide_turn` precedence | Optional meta-graph host — [SDK §14](conversation-control-plane-sdk.md#14-ecosystem-layering--langgraph-crewai-temporal-and-the-control-plane) |
| **Perception** | Bounded classifiers → enums | Classifier **nodes** — same contract either way |
| **Specialist agents** | `ConversationalAgent` under dispatch | Subgraphs / crews — Layer 1 execution |
| **Checkpoints** | `control_revision` + routing trace | Mid-agent checkpointer — **orthogonal** (run replay ≠ Switch/Stay) |

Load-bearing rules: (1) one writer of control keys (`decide_turn`); (2) ▨ labels, ▣ transitions
([SDK §2.1](conversation-control-plane-sdk.md#21-integration-guardrails-portable-contract)); (3) explicit ledger
state, not parallel context flags.

**Compose, don't replace:** LangGraph for **agent internals**; ledger + `decide_turn` for **cross-agent ownership**
([SDK §14](conversation-control-plane-sdk.md#14-ecosystem-layering--langgraph-crewai-temporal-and-the-control-plane)).
