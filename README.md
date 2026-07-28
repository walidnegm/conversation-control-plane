# Conversation Control Plane

**Turn-ownership ledger** for multi-agent product chat: who is foreground, what is
pinned, when ownership may yield — portable across how each turn is **run**
(LangGraph · agent SDKs · Temporal · plain code · human operator).

Package: `conversation-control-plane` · **MIT** · [Bot0.ai](https://bot0.ai)

**Not** a LangGraph / Temporal / ChatKit replacement. Keep those for *how* a turn
executes. This package owns *who holds the thread* across turns and specialists.

**Persistence is assumed** (your SQL store). **DB-backed is not the USP** —
portable authority semantics are.

---

## Contract at a glance

**Spec (lookup):** [docs/conversation-control-plane-sdk.md](docs/conversation-control-plane-sdk.md)  
**Lifecycle diagram:** [docs/conversation-turn-lifecycle-diagram.md](docs/conversation-turn-lifecycle-diagram.md)  
**Host laws:** [docs/host-transition-discipline.md](docs/host-transition-discipline.md)  
**Authority diagnostics:** [docs/conversational-authority-diagnostic-taxonomy.md](docs/conversational-authority-diagnostic-taxonomy.md) (diagnose before patch; A# ↔ failure modes)

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

| Type | Meaning |
|------|---------|
| `TaskTransition.BEGIN` | Start a multi-turn kind (`phase`, `pending_ref`) |
| `CONTINUE` | Same task; optional phase / awaiting update |
| `COMPLETE` | Success — release stickiness |
| `ABANDON` | User/reset bail — release stickiness (≠ complete) |
| `NONE` | No task semantics (pure Q&A) |

Agents return `TaskTransition` (+ domain-only `context_updates`).  
`strip_control_keys(...)` removes control keys from agent payloads.  
**Only** host / `decide_turn` write `active_task` and siblings.

### Multi-turn invariants (portable)

1. **Phase owns dispatch** — open vs continue vs pick phases are code gates.  
2. **Pin owns identity** — after pin, payload ids are authority (not ambient `last_read_*`).  
3. **LLM owns continue meaning** — labels / enums into the plane; not free-text ownership.  
4. **Finite grammar only when armed** — ordinals / approve only if a gate or menu was set.

### What this package does *not* own

Orchestration graphs · durable job infra · prompt registries · tool/MCP schemas ·
model memory · model vendors. Compose with them; do not re-implement them here.

Full anti-pattern library (A1–A19): [SDK §1.6](docs/conversation-control-plane-sdk.md#16-adoption-anti-patterns-engineering-doctrine--do-not-generate-these).

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
for NL meaning. No parallel ownership flags (A1). No ambient last-read as sole identity after pin.

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
