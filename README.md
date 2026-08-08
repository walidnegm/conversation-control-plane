# Conversation Control Plane

**Conversation Control Plane SDK** — A production-grade, DB-authoritative control
plane for multi-agent conversational AI. **LLM proposes; code owns the turn.**
Durable session ownership, deterministic handoffs, task lifecycle, and resume —
compose with LangGraph/tools; **do not replace them.**

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
**Lifecycle diagram:** [docs/conversation-turn-lifecycle-diagram.md](docs/conversation-turn-lifecycle-diagram.md)  
**Host laws:** [docs/host-transition-discipline.md](docs/host-transition-discipline.md)  
**Authority diagnostics:** [docs/conversational-authority-diagnostic-taxonomy.md](docs/conversational-authority-diagnostic-taxonomy.md)  
**Optional multi-turn proof:** [Conjecture Behaviour Runner](https://github.com/walidnegm/conjecture-behaviour-runner) (sibling)  
Operating sheet: **ladder** (causal) vs **triage** (investigation order). Roots **M/E/S/D**
parallel (D = delivery *authority* leakage). Quality stack = CAQ/purity · named **ratchet**
≠ suite · CI · eval (WIP). **Sealed** = checklist, not “looks fixed.”

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
model memory · model vendors. Compose with them; do not re-implement them here.

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

```text
  Product chat / API / worker
            │
            ▼
  ┌─ This package ─────────────────────────────┐
  │  claim → decide_turn → handle → apply → release │
  │  L1 projection · L2 journal · gates · resume │
  └────────────────────────────────────────────┘
            │ handle dispatches into
            ▼
  LangGraph · Agents SDK · CrewAI · Rasa · ChatKit · plain Python · Temporal
            │
            ▼
  Models · tools / MCP · domain DB · model memory (Letta / mem0 / Zep / …)
```

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

## When to adopt

**Adopt when** you have multi-specialist sticky chat, need SQL-auditable ownership,
hit stuck sessions / double-writers, or mix run leaves without rewriting control law.

**Skip when** a single graph/session is enough, Temporal already owns everything you
care about, or you are still prototyping single-agent flows.

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
| [`src/conversation_control_plane/`](src/conversation_control_plane/) | Installable package |
| [`docs/`](docs/) | SDK contract + lifecycle + host discipline |
| [`examples/e2e_host_loop.py`](examples/e2e_host_loop.py) | Runnable host + COMPLETE≠ABANDON demo |
| [`examples/cyber_risk_assessment/`](examples/cyber_risk_assessment/) | Optional specialist scaffold |
| [`examples/integrations/`](examples/integrations/) | Wrap sketches (not full E2E products) |
| [`tests/`](tests/) | Portable contract tests |

---

## Maintainers

Publish from the Bot0 monorepo:

```bash
./scripts/publish_control_plane_public_repo.sh --repo /path/to/clone --push
```

---

## License

MIT — see [LICENSE](LICENSE).
