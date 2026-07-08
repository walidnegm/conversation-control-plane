# Conversation Control Plane SDK

*Conversation Control Plane SDK* — reference implementation by [Bot0.ai](https://bot0.ai)

**Infrastructure-first state machine for reliable multi-agent chat.**

This SDK provides a **DB-authoritative ledger** and control plane that cleanly separates LLM cognition from conversation orchestration. Every turn, task transition, and handoff is explicitly tracked with strong single-writer guarantees, making long-lived, multi-specialist conversations reliable and auditable.

---

## Repository layout

| Path | What it is |
|---|---|
| [`docs/`](docs/) | Integration contract, lifecycle diagram, applicability one-pager |
| [`reference/`](reference/) | Portable reference modules (`decide_turn`, ledger, delivery-order contract, …) |
| [`examples/`](examples/) | Sanitized integration stubs — copy the shape, bring your own prompts/tools |
| [`tests/`](tests/) | Portable contract tests you can run without the Bot0 monorepo |

**Start with:** [docs/conversation-control-plane-sdk.md](docs/conversation-control-plane-sdk.md) (Getting started + §5 invariants)

---

## Why this exists

LangGraph, CrewAI, and Temporal are strong **execution** layers. Multi-specialist **chat** still needs an explicit **conversation layer**: who owns the turn, how handoffs work, resume vs gate semantics, and routing audit. This SDK formalizes that layer so you can **compose** it with the tools you already use.

---

## Core features

- **Publishable ledger** — `active_task`, `suspended_tasks`, `pending_switch`, `control_revision`, turn claims
- **Deterministic routing** via `decide_turn` (single writer)
- **`ConversationalAgent`** protocol for specialists
- **Delivery-order contract** — front-door discovery detours beat stale context pins
- Strong invariants and a portable regression harness
- Clean separation: LLM proposes → control plane enforces

---

## Status

| Shipped | Still open (Phase 1b) |
|---|---|
| SDK docs + lifecycle diagram | `pip install conversation-control-plane` |
| Reference modules under `reference/` | Full adapter interfaces + monorepo import decoupling |
| Delivery-order contract + portable tests | LangGraph/CrewAI adapter packages |
| Cyber risk assessment **design stub** | Production specialist implementations |

The **integration contract is stable** — port and test against it now. The Bot0 monorepo remains the authoritative sync source until package boundaries ship.

---

## Examples

Sanitized stubs only — no tenant data, no internal backlogs, no marketplace wiring.

| Example | Pattern | Status |
|---|---|---|
| [`examples/cyber_risk_assessment/`](examples/cyber_risk_assessment/) | Bounded setup + async specialist ([SDK §9.1](docs/conversation-control-plane-sdk.md)) | Design stub |

Copy **ledger `kind`**, **`TaskTransition`**, and the **`decide_turn` branch** pattern. Implement your own prompts, tools, and persistence.

---

## Quick start

1. Read [docs/conversation-control-plane-applicability.md](docs/conversation-control-plane-applicability.md) — adopt vs skip in one screen
2. Read [docs/conversation-control-plane-sdk.md](docs/conversation-control-plane-sdk.md) — bootstrap + §5 invariants
3. Port `decide_turn` + ledger slice to your `conversations` store (JSONB control slice is fine)
4. Run portable tests:

```bash
pip install -e ".[dev]"
pytest tests/ -q
```

5. Pin §6–§7 regression cases from the SDK in your host app

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

## Ecosystem layering

| Layer | Typical tools | This SDK's role |
|---|---|---|
| **Conversation control** | This contract | `decide_turn` + ledger — who owns the thread |
| **Specialist execution** | LangGraph, CrewAI, plain Python, Temporal, … | `ConversationalAgent` + `TaskTransition` underneath dispatch |
| **Mid-agent recovery** | LangGraph checkpointer, your checkpoints | Orthogonal to ledger rows |

LangGraph is Bot0's **reference execution example** — optional. See [SDK §14](docs/conversation-control-plane-sdk.md#14-ecosystem-layering--langgraph-crewai-temporal-and-the-control-plane).

---

## Sync from Bot0 monorepo

Maintainers publish from the Bot0 monorepo:

```bash
git clone https://github.com/walidnegm/conversation-control-plane.git /tmp/conversation-control-plane
./scripts/publish_control_plane_public_repo.sh --repo /tmp/conversation-control-plane --push
```

---

## License

MIT — see [LICENSE](LICENSE).