# Control Plane SDK — Loop & Stuck-Thread Incident Playbook

Status: Living (2026-07-06) — public operational doc for adopters and CS/engineering  
Companion: [Conversation Control Plane SDK §3.1 Q2](conversation-control-plane-sdk.md#31-hard-questions-for-adopters) · [§0.7 honesty](conversation-control-plane-sdk.md#07-honest-limitations-weaknesses-and-applicability)

> **Honesty upfront.** Mitigations exist (precedence, Switch/Stay, `handoff_guard`, turn claims, IC4
> clarifier). They reduce loop frequency — they do **not** prove zero loops. Use this playbook to **recognize**,
> **triage**, and **fix at the contract layer**, not to patch symptoms in prompts.

---

## 1. When to use this playbook

| Signal | Likely class |
|---|---|
| User sees the **same orientation card** again after saying "continue" / "pick it up" | Orientation loop |
| User bounced **A → B → A** in one session with no progress | Handoff ping-pong |
| User finished a build but the next message still routes to the **old specialist** | Stale session capture |
| Routing strip shows `Skipped decide_turn; … short-circuit` | Pre-decide bypass (gauntlet violation) |
| Thread wedged — second message gets `conversation_turn_in_flight` forever | Stale turn claim |

---

## 2. Incident shapes (symptom → diagnosis → contract fix)

### 2.1 Orientation loop

**Symptom:** User asks to resume or continue; assistant re-renders the sessions/orientation card instead of
advancing the active task or enqueueing the specialist.

**Common causes**

| Cause | How to confirm | Contract-level fix |
|---|---|---|
| Discovery/orientation runs **before** `decide_turn` on a gate reply | Trace: `plan_summary` contains `discovery_detour` or `orientation`; layer is not `turn_plan:active_task` | Route gate replies through `decide_turn`; use `discovery_cognition_suppressed` / `authoring_gate_proceed` pattern |
| Resume at **open gate** routed to status card instead of builder enqueue | Trace: `discovery_kind=orientation`, `orientation_focus=status` at `domain_picker` phase | Engagement 2.1: `authoring_gate_proceed_owns_turn` before orientation dispatch |
| Classifier reads bare "yes" as orientation ask | `task_intent=detour` on finite gate reply | `WORKFLOW_CONFIRMATION_REPLIES` suppression + unified router gate rules |

**Regression pins:** `test_resume_authoring_routing`, `test_ledger_authoring_hygiene`, `test_decide_turn_control_plane` cases 1–3.

**Not a fix:** Adding more orientation prompt examples — that is NL cognition in prose (CAQ-8 anti-pattern).

---

### 2.2 Handoff ping-pong (hot-potato)

**Symptom:** Advisor hands to builder, builder immediately hands back; token burn with no user-visible progress.

**Common causes**

| Cause | How to confirm | Contract-level fix |
|---|---|---|
| Flaky classifier returns `handoff` on continue turns | Trace: `router_intent` ≠ `plan.agent`; `reason` mentions handoff | `decide_turn` precedence: continue wins at gate (§6 case 1) |
| No Switch/Stay on cross-agent move | `pending_switch` never set | `propose_switch` + user confirm for ambiguous targets |
| Immediate A→B→A bounce | Platform event `handoff_ping_pong_blocked` | `handoff_guard.would_ping_pong` — already shipped |

**Regression pins:** `test_control_plane_sdk_deliverables.DecideTurnHotPotatoTests`, `test_decide_turn_control_plane` case 8.

---

### 2.3 Stale session capture

**Symptom:** Build/commit finished but `active_task` still points at `workflow_builder`; next unrelated message
gets swallowed by the builder.

**Common causes**

| Cause | How to confirm | Contract-level fix |
|---|---|---|
| `complete_task` not called on terminal outcome | `get_control_state`: `active_task.agent` still set after success card | Terminal completion on commit/success paths (S1) |
| Ledger vs `workflow_builder_pending` drift | DB: context `active_task` disagrees with pending row phase | S5 two-state reconcile (open) |
| Post-commit builder not released | Trace: `workflow_builder` after `workflow_created` | `release_post_commit_builder` in `decide_turn` |

**Regression pins:** `test_ledger_authoring_hygiene`, terminal completion tests in control-plane epic.

---

### 2.4 Pre-decide short-circuit

**Symptom:** Trace shows `plan_summary: "Skipped decide_turn; …"` for a turn that should have opened or resumed
a ledger task.

**Common causes**

| Cause | How to confirm | Contract-level fix |
|---|---|---|
| Discovery/read detour `return` before `decide_turn` | `dispatch` in `_ALLOWED_PRE_DECIDE_DISPATCHES` but not code-owned finite pick | Demote to ledger task (S2/S4); only finite grammar picks may short-circuit |
| Multiple classifiers each with their own `return` | S7 warning `unexpected_skip_decide_turn` in platform events | Collapse to `conversation_unified_router` + single `decide_turn` |

**Regression pins:** `test_front_door_llm_hop_budget`, coherence S7 allow-list tests.

---

### 2.5 Stale turn claim (thread wedged)

**Symptom:** User cannot send a second message; API returns turn-in-flight indefinitely.

**Common causes**

| Cause | How to confirm | Contract-level fix |
|---|---|---|
| Worker died without `release_turn` | `_turn_claim` in context with old `claimed_at`, no `renewed_at` | Orphan steal after TTL (§11.2 `turn_claim_orphan_steal_seconds`) |
| Long SSE without heartbeat renew | Claim TTL exceeded mid-stream | `renew_turn_claim` during streaming |

**Regression pins:** `test_conversation_staleness_slice6`, turn-claim tests in ledger module.

---

## 3. Triage checklist (5 minutes)

1. **Read routing trace** on the stuck turn — `conversation_messages.route_data.routing` or SSE `routing` event.
2. **Read control slice** — `get_control_state` → `active_task`, `suspended_tasks`, `pending_switch`, `_control_revision`.
3. **Check platform events** — `handoff_ping_pong_blocked`, `unexpected_skip_decide_turn`, `ledger_agent_type_conflict`.
4. **Classify** using §2 above — orientation loop vs ping-pong vs stale capture vs short-circuit vs claim.
5. **Fix at contract layer** — precedence, suppression gate, `complete_task`, demote detour — not prompt band-aids.

---

## 4. Open gaps (not closed — track honestly)

| Gap | Status | Epic / backlog |
|---|---|---|
| Full **zero-loop proof** | Property harness expanding; Hypothesis sequences open | SDK §15, `test_control_plane_property_harness` |
| **S5** ledger ↔ builder pending reconcile | ⏳ | Control-plane #1 |
| **IC3** fix-forward validator alignment | ⏳ | CP §9b |
| **S4** classifier module retirement | 🔨 | Coherence #1e |
| Enterprise **scale soak** | Procedure doc only | [scale-smoke playbook](conversation-control-plane-scale-smoke.md) |

---

## 5. Related artifacts

| Doc | Role |
|---|---|
| [SDK §6–§7](conversation-control-plane-sdk.md) | Canonical regression cases + single-arbiter routing |
| [Trace export](conversation-control-plane-trace-export.md) | Export traces to Langfuse/OTel for loop forensics |
| [Property harness](../../regression_suite/test_control_plane_property_harness.py) | Scripted turn sequences |
