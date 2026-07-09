# Conversation Control Plane SDK

*Conversation Control Plane SDK* — reference implementation by [Bot0.ai](https://bot0.ai)

**Who owns the conversation** — not how each specialist runs inside its turn.

Execution frameworks (LangGraph, CrewAI, Temporal, plain Python) keep getting better at graphs, crews, and
durable workflows. Production **multi-specialist chat** still needs a narrow, load-bearing layer on top:
**cross-agent session lifecycle** — resume, suspend, handoff, detour, and gate semantics in one thread.
This SDK formalizes that **conversation control plane**. You keep your execution stack; you add (or port) the
ledger when session ownership is what breaks in production.

Full layering guide: [SDK §14](docs/conversation-control-plane-sdk.md#14-ecosystem-layering--langgraph-crewai-temporal-and-the-control-plane)

---

## Three-layer agentic stack

| Layer | What | This repo |
|---|---|---|
| **1 — In-agent execution** | LangGraph/Crew/plain Python: planning, tools, checkpoint *inside* one specialist | Your runtime under `ConversationalAgent` |
| **2 — Multi-agent meta** | Who owns the shared chat thread, handoffs, resume | **This SDK** (`decide_turn` + ledger) — or a graph supervisor; pick one authority |
| **3 — Memory** | Vector/RAG, crew memory, Redis, … **plus** ledger `active_task.payload` for routing | Third-party for recall; **ledger owns control keys** |

Detail: [SDK §0.1.1](docs/conversation-control-plane-sdk.md#011-three-layer-model-of-an-agentic-system) · compose: [§14](docs/conversation-control-plane-sdk.md#14-ecosystem-layering--langgraph-crewai-temporal-and-the-control-plane)

## Where this sits in the stack

| Layer | Typical tools | Question it answers |
|---|---|---|
| **Conversation control (meta)** | **This SDK** | Who owns the thread right now? Why did this turn route to specialist X? |
| **Specialist execution** | LangGraph, CrewAI, Temporal, Python, … | How does this specialist run tools, IR, or domain logic? |
| **Mid-agent recovery** | LangGraph checkpointer, your checkpoints | How do we survive a crash *inside* one specialist turn? |
| **Memory substrate** | Postgres ledger, vector DB, vendor session APIs | What persists for routing vs retrieval vs domain artifacts? |

Same Postgres can host both a LangGraph checkpointer and this ledger — they store **different shapes for
different questions**. Checkpoints answer “what was graph state at step N?” The ledger answers “why did this
**turn** route to agent X, and what task is foreground?”

**Integration rule:** classifiers propose labels; **`decide_turn` enforces** transitions. Specialists implement
`ConversationalAgent`, return `TaskTransition` only, and never write `active_task` / `pending_switch`.

---

## Writing a specialist (builder contract)

Use this when you add a **multi-turn** agent (builder, cyber assessment, cost, intake, …). One-shot tools may
skip a ledger kind; **follow-ups on the same entity must not**.

| Rule | Owner | Do | Don't |
|---|---|---|---|
| **Register a kind** | Your code | Closed enum string on `active_task.kind` | Free-text kinds from RAG / embeddings |
| **Start the stream** | Your code | `begin_task` / `update_phase` when multi-turn work starts | Treat “tool succeeded last turn” as ownership |
| **Pin identity** | Ledger payload | Typed ids (`workflow_id`, `project_id`, `run_id`, …) | Ambient `last_read_*` as sole authority after pin |
| **Phase owns dispatch** | Host + [§2.1 multi-turn stream](docs/conversation-control-plane-sdk.md#21-multi-turn-stream-contract-every-sole-continue-kind) | Entity resolve only in open/pick phases | Re-resolve by name on every continue turn |
| **LLM owns continue meaning** | Bounded classifier / specialist | Sizing, verify, refine labels | Regex/wordlists as sole arbiter of meaning |
| **Finite grammar when armed** | Code | Bare `1` / `yes` only if `pending_question` / menu was set | Every digit steals any list in the thread |
| **Handoffs** | `TaskTransition` | Declare begin / continue / complete / detour | Specialists write control keys |

**Four multi-turn invariants** (portable): phase owns dispatch · pin owns identity · LLM owns continue meaning ·
finite grammar only when armed. Reference helpers: `reference/.../multi_turn_stream_contract.py`.

**Worked example:** [examples/cyber_risk_assessment/](examples/cyber_risk_assessment/) — design stub only
(not production product code). Copy the **shape** (`kind`, phases, `TaskTransition`, decide branch), not private
engines or UI.

---

## Compose — don't rip and replace

LangGraph (and peers) give you real wins: checkpointing, subgraph interrupts, Studio-style debugging, crew
delegation. For a single-agent tool loop, that is often enough.

When **several chat specialists share one thread** for hours or days, teams usually still wire ad-hoc session
flags or hope graph resume re-enters the right node. This SDK adds a **SQL-friendly control slice**
(`active_task`, `suspended_tasks`, `pending_switch`) with single-writer discipline, Switch/Stay handoffs, and
routing traces — without replacing your subgraphs or crews.

| Your situation | Recommendation |
|---|---|
| One agent, one tool loop | **Execution framework only** — this SDK is optional overhead |
| Multiple specialists, sticky chat, resume language | **Compose** — framework for brains; ledger for skeleton |
| Custom session manager on top of a graph | Compare to [SDK §5 invariants](docs/conversation-control-plane-sdk.md#5-invariants-non-negotiable); port ledger semantics instead of a third state system |
| Compliance: prove routing on date T | Ledger + `route_data.routing`; keep checkpoints for execution forensics |

| | Ledger SDK | LangGraph | CrewAI |
|---|---|---|---|
| Best audit question | Why did this **turn** route to X? | What was graph state at step N? | What did the crew remember? |
| Handoffs | `pending_switch` + TTL, code-owned | Interrupts / edges | Delegation |
| Ground truth | DB + `control_revision` | Checkpoints | Crew memory |

LangGraph is Bot0's **reference execution example**, not a dependency. CrewAI and Temporal fit the same
compose story when chat reliability is the bottleneck.

---

## Repository layout

| Path | What it is |
|---|---|
| [`docs/`](docs/) | Contract + lifecycle diagram only (loops/traces/scale are SDK §3.1 + §11.1) |
| [`reference/`](reference/) | Portable reference modules (`decide_turn`, ledger, delivery-order contract, …) |
| [`examples/`](examples/) | Sanitized integration stubs — copy the shape, bring your own prompts/tools |
| [`tests/`](tests/) | Portable contract tests you can run without the Bot0 monorepo |

**Contract:** [docs/conversation-control-plane-sdk.md](docs/conversation-control-plane-sdk.md)

---

## Adopt when

- Several conversational agents share **one thread** (builder, advisor, editor, …)
- Users say "pick up where we left off," "switch to the other one," or detour mid-task
- You need **why did routing choose X?** without deserializing a graph checkpoint
- Multi-worker chat needs **turn serialization** (`_turn_claim`, `control_revision`)

## Skip when

- Single-agent tool loop, no cross-agent stickiness
- Batch automation with no resume language
- You want graph Studio / rapid topology edits more than ledger discipline

---

## Core features

- **Publishable ledger** — `active_task`, `suspended_tasks`, `pending_switch`, `control_revision`, turn claims
- **Deterministic routing** via `decide_turn` (single writer)
- **`ConversationalAgent`** protocol for specialists
- **Delivery-order contract** — front-door discovery detours beat stale context pins
- **Multi-turn stream contract** — phase / pin / LLM continue / finite picks ([SDK §2.1](docs/conversation-control-plane-sdk.md#21-multi-turn-stream-contract-every-sole-continue-kind))
- Portable regression harness — LLM proposes, control plane enforces

---

## Status

| Shipped | Still open (Phase 1b) |
|---|---|
| SDK docs + lifecycle + three-layer stack | `pip install conversation-control-plane` |
| Reference modules under `reference/` (incl. multi-turn stream helpers) | Adapter interfaces + decoupled imports |
| Delivery-order + multi-turn stream contracts | LangGraph/CrewAI adapter packages |
| Cyber risk assessment **design stub** | Production specialist implementations (stay in your host product) |

The **integration contract is stable** — port and test against it now.

---

## Examples

| Example | Pattern | Status |
|---|---|---|
| [`examples/cyber_risk_assessment/`](examples/cyber_risk_assessment/) | Bounded setup + async specialist ([SDK §9.1](docs/conversation-control-plane-sdk.md) + multi-turn stream) | **Design stub only** |

**Privacy:** sanitized stubs only — no tenant data, no internal backlogs, no production scoring engines or
product UI. Copy **ledger `kind`**, **phases**, **`TaskTransition`**, and the **`decide_turn` branch** pattern.

---

## Quick start

1. **This README** — niche + compose decision + *Writing a specialist* (above)
2. [SDK contract](docs/conversation-control-plane-sdk.md) — Getting started · §2.1 multi-turn stream · §5 invariants
3. Port `decide_turn` + ledger slice to your `conversations` store (JSONB control slice is fine)
4. `pip install -e ".[dev]"` then `pytest tests/ -q`
5. Pin §6–§7 regression cases; for multi-turn kinds, pin “no re-resolve after pin”
6. Optionally study [cyber stub](examples/cyber_risk_assessment/) for a bounded specialist shape

---

## Maintainers

Publish from the Bot0 monorepo:

```bash
./scripts/publish_control_plane_public_repo.sh --repo /path/to/clone --push
```

---

## License

MIT — see [LICENSE](LICENSE).