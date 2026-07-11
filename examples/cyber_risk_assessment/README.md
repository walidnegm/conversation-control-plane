# Cyber Risk Assessment — optional specialist scaffold

**Status:** **Optional shape pin** — not production product code, not the primary on-ramp.

Most coding agents should start from the package [README On-ramp](../../README.md)
(**lessons learnt + kickoff prompt**). The SDK doc is the **spec** for lookup. This folder is a
**token saver** when you want a concrete KindSpec / thin payload / sole-writer host — agents can
usually generate the same shape from the lessons alone. Full product cyber (LangGraph strategist,
scoring engines) is intentionally **not** shipped here.

## Developer surface (keep small)

| Artifact | Role |
|---|---|
| Package [README](../../README.md) **On-ramp** | Lessons learnt, setup, **kickoff prompt** (start here) |
| [SDK contract](../../docs/conversation-control-plane-sdk.md) | Spec for lookup — not cover-to-cover |
| **This example** | Optional runnable shape (KindSpec, thin pins, HITL VERIFY, host sketch) |

## What this example proves (production-grade map)

| Claim | How the scaffold shows it |
|---|---|
| **P4** immutable `task_id` | Host `begin_task` assigns id; agent only echoes it |
| **P5** COMPLETE ≠ ABANDON | Distinct journal types in `host_sketch.py` |
| **P6** `command_id` | Every `TaskTransitionRequest` carries one |
| **P15** thin projection | `payload_patch` = pins only; IR under `pending_ref` domain store |
| **P16** KindSpec | `kind_spec.py` → register before begin |
| **§2.1** multi-turn stream | Resolve only in `anchor`; continue uses pins; VERIFY = human_approval finite grammar |
| **Single writer** | Agent returns transitions; host applies them |

L2 journal + `expected_version` fencing + outbox are **host ledger** concerns — use the reference `ledger.py` in your port; this sketch uses an in-memory FakeLedger for the dialogue shape only.

## Layered stack

| Layer | This example |
|---|---|
| **1 — In-agent execution** | Phase walk + optional HITL at VERIFY (swap in LangGraph later) |
| **2 — Conversation control** | `kind=cyber_risk_assessment` + host sole writer |
| **3 — Memory** | Thin pins on projection; **IR in domain store** via `pending_ref` |

## Files

| File | Purpose |
|---|---|
| `kind_spec.py` | B6 KindSpec + allowed thin payload keys |
| `assessment_ir.py` | Domain IR (`cyber_risk_assessment_ir_v1`) — specialist store only |
| `agent_stub.py` | Specialist: BEGIN / CONTINUE / COMPLETE / ABANDON + thin payload |
| `host_sketch.py` | **Runnable** in-memory host dialogue (begin → pin → VERIFY approve → complete) |
| `decide_integration.md` | `decide_turn` sole-continue branch pattern |

## Run the dialogue

```bash
cd examples/cyber_risk_assessment
python host_sketch.py
```

You should see a single `task_id` across turns, thin `payload` pins, domain IR off-projection, and journal rows `task_began` … `task_completed` (or `task_abandoned` if you cancel).

## Multi-turn stream (do not skip)

After the entity is **pinned**, continue turns follow
[SDK §2.1](../../docs/conversation-control-plane-sdk.md#21-multi-turn-stream-contract-every-sole-continue-kind):

1. **Phase owns dispatch** — no greenfield re-resolve in continue phases  
2. **Pin owns identity** — payload ids only  
3. **LLM owns continue meaning** — in product; scaffold advances phases deterministically  
4. **Finite grammar when armed** — e.g. VERIFY waits for `approve`  

Helpers: `reference/api/services/conversation_control/multi_turn_stream_contract.py`.

## Model A lifecycle

| Command | Projection | Journal |
|---|---|---|
| Begin | `begin_task` → `task_id` | `task_began` |
| Continue | `update_phase` (same `task_id`) | progress (optional) |
| Finish | `complete` | `task_completed` |
| Cancel | `abandon` | `task_abandoned` |

## Builder checklist (coding agent)

1. Register `CYBER_RISK_KIND_SPEC`  
2. First sticky turn → transition `begin`; host assigns `task_id`  
3. Domain IR → `pending_ref` store; projection → pins only  
4. Gate continue with multi-turn helpers  
5. Return `TaskTransitionRequest` with `task_id` + `command_id`  
6. Cancel → abandon; save → complete  
7. Pin tests: resume, complete, abandon, no auto-switch, **no re-resolve after pin**, IR not in control payload  

## Intentionally omitted

- Production scoring engines and full risk catalogs  
- Product UI / admin  
- Full LangGraph strategist (compose as Layer 1 when ready — see package README wrap sketch)  
- Real Postgres (use reference ledger modules)
