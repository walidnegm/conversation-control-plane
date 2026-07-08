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

**Canonical architecture (4 of 4).** Part of the four-document set with the [SDK](conversation-control-plane-sdk.md),
Bot0 implementation playbook (monorepo only), and
. Index:
.

**What this is.** A single, code-accurate map of one chat turn through `api/services/bot0.py::chat` and the
`conversation_control/` package. It shows *exactly* where intent classification, routing, decisioning, detouring,
and hot-potato handling happen — and where the **ledger** is read and written, which is what makes the flow a
real capability rather than a stateless prompt chain.

**Honest framing.** This documents the flow **as it is**, not the idealized "one router → `decide_turn`" version
in the [SDK contract](conversation-control-plane-sdk.md). The pre-decide **gauntlet** is real: several fast-paths
and detours can short-circuit before `decide_turn` runs. Retiring that competition (detours → ledger tasks, one
authoritative decision) is the  work;
this diagram is the honest baseline it works against.

**Code anchors** (2026-07-07): `chat()` [bot0.py:6071](../../api/services/bot0.py#L6071) · guardrail
[:6131](../../api/services/bot0.py#L6131) · pre-decide gauntlet [:6333–6430](../../api/services/bot0.py#L6333) ·
unified router + authority passes [:6461–6505](../../api/services/bot0.py#L6461) · `decide_turn`
[:7447](../../api/services/bot0.py#L7447) · prose intake / readiness path [:8183](../../api/services/bot0.py#L8183) ·
post-decide detours [:7520–7608](../../api/services/bot0.py#L7520). Ledger
[ledger.py:274](../../api/services/conversation_control/ledger.py#L274) · hot-potato
[handoff_guard.py](../../api/services/conversation_control/handoff_guard.py) · intake maturity
[intake_maturity.py](../../api/services/conversation_control/intake_maturity.py) · enrich intake
[workflow_intake.py](../../api/services/conversation_control/workflow_intake.py).

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

## 7. Stage → code anchor

| Stage | Where | Kind |
|---|---|---|
| Turn claim / release | `ledger.claim_turn` / `release_turn` / `renew_turn_claim` | ▣ serialize |
| Guardrail | [bot0.py:6131](../../api/services/bot0.py#L6131) `check_message` | ▨ safety |
| Pre-decide gauntlet | [bot0.py:6333–6406](../../api/services/bot0.py#L6333) (`_try_catalog_handoff` → `_try_prose_intake_early_enqueue`) | ▣/▨ ⚡ |
| Unified router | [bot0.py:6461](../../api/services/bot0.py#L6461) `classify_unified_turn` | ▨ perception |
| Router authority passes | [bot0.py:6476–6505](../../api/services/bot0.py#L6476) `apply_*_authority` | ▣ execution on signal |
| Intent router L0–L4 | `bot0_intent_router.py` (`_structural_builder_route_or_llm_veto`) | ▣/▨ perception |
| Prose intake + readiness | [bot0.py:8183](../../api/services/bot0.py#L8183); `enrich_intake_assessment` | ▨ labels → ▣ gates |
| Finite picks + reset | pending picks [bot0.py:6834–6903](../../api/services/bot0.py#L6834); reset `reset_commands.py` | ▣ ⚡ |
| **decide_turn** | [bot0.py:7432](../../api/services/bot0.py#L7432) → `decide.py::decide_turn` | ◆ authoritative |
| **Front-door delivery** | [bot0.py](../../api/services/bot0.py) post-`decide_turn` · `delivery_order_contract.py` | ◆/▣ — **before** active-flow continue |
| Active-flow continue | `realization_intake` / `outcome_value_setup` handlers | ▣ — gated by `active_flow_handler_must_yield()` |
| Post-decide detours | orientation demotion · discovery demotion · concept gate · prose intake | ▨/▣ |
| Ledger control keys | [ledger.py:274](../../api/services/conversation_control/ledger.py#L274) | ▣ state |
| Hot-potato guard | [handoff_guard.py](../../api/services/conversation_control/handoff_guard.py) `would_ping_pong` | ▣ |
| Routing trace | `route_data.routing` (`Bot0RoutingTrace`) | observability |

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

**2026-07-07 addendum — readiness is not one thing.** 
names three readiness flavors across prose → intake → IR → sim → deploy. Only **semantic** intake readiness (how rich is the description?) belongs
in ▨. Shape rubrics (`apply_strength_rubric`) are **fail-soft fallback** when the router did not assess — they must
not discard `authoring_maturity` / `missing_segments` from the unified router.

---

## 9. Prose intake + readiness gauntlet (post-`decide_turn`)

Opens when `_workflow_prose_intake_active` is true **after** `decide_turn` (typically `effective_intent != workflow_builder`,
`workflow_draft_request` or structural paste gate). This is **not** the same as pre-decide `prose_intake_early_enqueue`
(▣ structural shape/length only — async enqueue accelerator).

```mermaid
flowchart TD
  GATE["▣ _workflow_prose_intake_active<br/>structural paste gate — NOT semantic readiness"]
  GATE -->|false| SKIP["fall through to specialist dispatch"]
  GATE -->|true| COG

  subgraph COG["Cognition — already on UnifiedTurnSignal from §1"]
    U1["▨ user_wants — draft_help | use_as_is | …"]
    U2["▨ authoring_maturity — M0..M5"]
    U3["▨ missing_segments — gap prose"]
    U4["▨ intake_readiness hint"]
  end
  COG --> AUTH2

  subgraph AUTH2["▣ Code authority on signal (pre-merge)"]
    A1["apply_workflow_prose_intake_authority<br/>workflow_draft_request; no commit_ready force"]
    A2["apply_drafting_signal_authority<br/>draft_help → drafting lane"]
  end
  AUTH2 --> ASSESS

  subgraph ASSESS["▣ Assessment merge + enrich (single source)"]
    M1["assessment_from_unified_signal (S4 fast-path)"]
    M2["assess_workflow_intake (optional full hop)"]
    M3["merge_intake_assessments — router maturity wins"]
    M4["enrich_intake_assessment — LLM gaps/maturity authoritative"]
    M5["apply_strength_rubric — fallback ONLY when LLM did not assess"]
    M1 --> M3
    M2 --> M3
    M3 --> M4
    M4 -->|no LLM assess| M5
  end
  ASSESS --> EXEC

  subgraph EXEC["▣ Execution gates — no NL guessing"]
    E1["should_block_auto_interpret — draft_help blocks IR handoff"]
    E2["intake_should_offer_fork — user_wants + maturity"]
    E3["intake_prefers_direct_interpret — use_as_is / structure_now only"]
    E4["begin_task kind=drafting OR interpret handoff"]
  end
  EXEC -->|fork / coaching| SHORT
  EXEC -->|handoff| WB["workflow_builder async"]
  EXEC -->|sparse elicit| SHORT

  note1["Rubric prose lives in conversation_unified_router<br/>prompt library — not Python execution"]
```

| Step | Module | Cognition vs execution |
|---|---|---|
| Paste is workflow-shaped | `_workflow_prose_intake_active` | ▣ structural gate (length/shape) |
| User intent this turn | `UnifiedTurnSignal.user_wants` | ▨ classifier rubric → ▣ `safe_user_wants` |
| Content maturity | `authoring_maturity` + `missing_segments` | ▨ rubric → ▣ `readiness_from_authoring_maturity` |
| Override product detour | `apply_workflow_prose_intake_authority` | ▣ clears how-to; sets `workflow_draft_request` |
| Block auto-IR | `should_block_auto_interpret` | ▣ policy on LLM label |
| Fallback rubric | `apply_strength_rubric` | ▣ only when `assess_source != llm` |

Regression pins: `test_cognition_execution_readiness_gauntlet.py`, `test_intake_maturity_routing_contract.py`.

---

## 10. Is this a LangGraph? (honest answer)

**The diagrams describe semantics, not a framework choice.** Bot0's control plane is already a **state machine**
(§4 ledger `stateDiagram`) plus a **deterministic dispatcher** (`decide_turn` flowchart in §3). It was built
imperatively — `bot0.chat()` gauntlet, `decide.py`, `ledger.py` — through production incidents, not by drawing
LangGraph first.

| Layer | Today | LangGraph? |
|---|---|---|
| **Control plane** (who owns the turn?) | Ledger JSONB + `decide_turn` precedence | *Optional future* meta-graph host ([future-state-langgraph-migration.md](future-state-langgraph-migration.md) **target**, not required) |
| **Perception** | Bounded classifiers → enums | Classifier **nodes** — same contract either way |
| **Specialist agents** | Heterogeneous (while-loop, FSM, StateGraph) | Workflow builder already uses LangGraph **internally**; advisor uses while-loop |
| **Checkpoints** | `_control_revision` + DB context + routing trace | LangGraph checkpointer answers a *different* question (run replay), not Switch/Stay precedence |

**Provocation you named is partly right:** we did assemble graph-shaped behavior backwards — gauntlet layers,
ledger states, readiness gates — and the diagrams make that visible. **That does not mean the control plane must
become a LangGraph StateGraph to be correct.** The load-bearing contract is:

1. **One writer** of control keys (`decide_turn`).
2. **Cognition → execution split** (▨ labels, ▣ transitions) — [SDK §2.1](conversation-control-plane-sdk.md#21-integration-guardrails-portable-contract).
3. **Explicit state** on the ledger, not implicit flags.

LangGraph could **host** the meta-graph later (supervisor node ≈ `decide_turn`, classifier node ≈ unified router)
while preserving the same precedence rules as product IP. Until then, these mermaid diagrams *are* the state
graph — expressed as documentation + regression pins, not as `StateGraph` edges. Adding LangGraph without
collapsing the gauntlet would duplicate the two-state-system bug (ledger vs graph checkpoint).

**Rule of thumb:** LangGraph for **agent internals** and optional **runtime plumbing**; ledger + `decide_turn`
for **cross-agent ownership** — compose, don't replace ([SDK §14](conversation-control-plane-sdk.md#14-ecosystem-layering-compose-dont-replace)).
