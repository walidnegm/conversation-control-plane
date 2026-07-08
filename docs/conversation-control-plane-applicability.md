# Conversation Control Plane SDK

*Conversation Control Plane SDK* — reference implementation by [Bot0.ai](https://bot0.ai)

**Public repository:** [github.com/walidnegm/conversation-control-plane](https://github.com/walidnegm/conversation-control-plane)

**Infrastructure-first state machine for reliable multi-agent chat.**

This SDK provides a **DB-authoritative ledger** and control plane that cleanly separates LLM cognition from conversation orchestration. Every turn, task transition, and handoff is explicitly tracked with strong single-writer guarantees, making long-lived, multi-specialist conversations reliable and auditable.

Distilled from the full [integration contract](conversation-control-plane-sdk.md) and [§14 ecosystem layering](conversation-control-plane-sdk.md#14-ecosystem-layering--langgraph-crewai-temporal-and-the-control-plane). Use as README front-matter after Phase 1b extraction.

---

## Why this exists

LangGraph, CrewAI, and Temporal are strong **execution** layers. Multi-specialist **chat** still needs an explicit **conversation layer**: who owns the turn, how handoffs work, resume vs gate semantics, and routing audit. This SDK formalizes that layer so you can **compose** it with the tools you already use.

---

## Core features

- **Publishable ledger** — `active_task`, `suspended_tasks`, `pending_switch`, `control_revision`, turn claims
- **Deterministic routing** via `decide_turn` (single writer)
- **`ConversationalAgent`** protocol for specialists
- Strong invariants and regression harness for production safety
- Built-in support for concurrency, hot-potato prevention, TTLs, and context hydration
- Clean separation: LLM proposes → control plane enforces

---

## Status

**Public home:** [github.com/walidnegm/conversation-control-plane](https://github.com/walidnegm/conversation-control-plane) — early extraction (README live; code sync in progress).

**Reference implementation** by Bot0.ai — authoritative source in the Bot0 monorepo today. The **integration contract is stable** — port and test against it now; **Phase 1b** adds `pip install` / `npm install` convenience.

---

## Start here

1. **This page** — fit in one screen (adopt vs skip below)
2. [Integration contract](conversation-control-plane-sdk.md) — Getting started + §5 invariants
3. Port `decide_turn` + ledger slice → pin regression cases (`test_decide_turn_control_plane` pattern)
4. Persist **`route_data.routing`** every turn ([trace export](conversation-control-plane-trace-export.md))

---

## Adopt when ✅

- Several conversational agents share **one thread** (builder, advisor, editor, …)
- Users say "pick up where we left off," "switch to the other one," or detour mid-task
- You need **why did routing choose X?** without deserializing a graph checkpoint
- Multi-worker chat needs **turn serialization** (`_turn_claim`, `control_revision`)

## Skip when ❌

- Single-agent tool loop, no cross-agent stickiness
- Batch automation with no resume language
- You want graph Studio / rapid topology edits more than ledger discipline

---

## Ecosystem layering (LangGraph / CrewAI / Temporal)

| Layer | Typical tools | This SDK's role |
|---|---|---|
| **Conversation control** | This contract | `decide_turn` + ledger — who owns the thread |
| **Specialist execution** | LangGraph, CrewAI, plain Python, Temporal, … | `ConversationalAgent` + `TaskTransition` underneath dispatch |
| **Mid-agent recovery** | LangGraph checkpointer, your checkpoints | Orthogonal to ledger rows |

LangGraph is Bot0's **reference execution example** — optional. See SDK §14 for the layering diagram.

---

## Minimum integration (Tier 0–1)

1. Wire chat: message → router signal → **`decide_turn`** → dispatch
2. Port ledger APIs to your `conversations` store (JSONB control slice is fine)
3. Pin §6–§7 regression cases (`test_decide_turn_control_plane` pattern)
4. Persist **`route_data.routing`** every turn ([trace export](conversation-control-plane-trace-export.md))

Full contract: [conversation-control-plane-sdk.md](conversation-control-plane-sdk.md)
