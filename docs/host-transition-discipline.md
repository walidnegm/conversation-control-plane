# Host transition discipline

**Audience:** adopters integrating the Conversation Control Plane (CCP) SDK, and anyone
adding a new multi-turn kind. 
**Companion:** [SDK §2.1 multi-turn stream](conversation-control-plane-sdk.md#21-multi-turn-stream-contract-every-sole-continue-kind) ·
[SDK §3.1 — loops & stuck threads](conversation-control-plane-sdk.md#31-hard-questions-for-adopters) ·
[Conjecture Behaviour Runner](https://github.com/walidnegm/conjecture-behaviour-runner) (state-law scripts / parameterized templates).

This is **host law**, not a new ledger API. The ledger faithfully records whatever
transition you apply. Wrong COMPLETE / missing CONTINUE is a **host bug**.

---

## 0. Specialists own their own machinery

The control plane does **not** run your product state machine for you. It only:

* records **who owns** the conversation (`active_task.kind`, phase, pins), and 
* applies **honest transitions** you request (begin / continue / complete / abandon).

**Each multi-turn specialist (agent) is responsible for its own finite machinery** —
closed phases, legal next steps, and the **user-visible surface** that advertises those
steps. If the agent’s phases, CTAs, and advance path drift apart, users feel that
“the system has no memory of its own rules.” That frustration is almost always a
**specialist / host FSM bug**, not a broken ledger and not something Conjecture can
fix at runtime (Conjecture only ratchets the failure after you write a seal).

| Layer | Owns |
|---|---|
| **Specialist FSM** | Phase enum, what “confirm” means *this* phase, which button is legal, apply vs redisplay |
| **Host loop** | claim → decide → handle → apply transition → release; never invent COMPLETE |
| **Ledger** | Projection + journal of what you applied |
| **Conjecture** | Freeze-safe proof that ownership/phase law held across turns |

### Surface must not lie about phase

Intent and surface must agree.

**Bad (dogfood incident class):** the *intent* of the gate is “confirm structural
fixes first,” but the card advertises **Continue to staffing** (or **Yes** / **OK**)
while still in `repair_proposal`. The user follows the button and the turn
redisplays or skips apply — the product *looks* broken even when the user did the
reasonable thing.

**Good:** one honest primary action per phase, for example:

| Phase | Primary CTA (example) |
|---|---|
| Repair / fix plan pending | **Confirm fixes** |
| Structure clear | **Continue to staffing** (or your domain’s next phase) |
| Staffing clear | **Continue to compile** / commit |

Do not offer the *next* phase’s action while the *current* phase is still blocking.
Do not use vague **Yes** / **OK** as the only labels when the phase has a named
product meaning.

**Rule of thumb:** if a user can click the primary button and *not* advance the
phase you claimed, the specialist’s state machine is wrong — fix the agent/host
path, not the ledger API.

---

## 1. Every host result names a transition

After `handle_turn` (or any specialist/async worker result that affects ownership), the
host must apply **exactly one** lifecycle signal via ledger APIs:

| Transition | Meaning | Typical journal / projection effect |
|---|---|---|
| **begin** | Open or re-open a multi-turn stream | `task_began`; set `active_task.kind` + phase + pins |
| **continue** | Same stream still owns the next turn | `update_phase` / pin refresh — **active_task stays** |
| **complete** | Product terminal success | `task_completed`; clear stickiness |
| **abandon** | User/system cancel (not success) | `task_abandoned`; clear stickiness — **≠ complete** |
| **none** | No ownership change this turn | Do not call complete “to clean up” |

### Rule

> **Never infer COMPLETE from missing fields** (e.g. `agent_type is None`, empty
> `context_updates`, “looks like the builder finished”). 
> **Only COMPLETE when the product is actually done** (saved, committed, failed closed
> as terminal, or user abandoned).

Illegal COMPLETE triggers (non-exhaustive):

| Situation | Correct transition |
|---|---|
| Idle / session reorient card (Resume / Start Fresh) | **continue** (gate) — not complete |
| User clicked **Resume** | **continue** (+ redisplay checkpoint) |
| User clicked **Start Fresh** | **abandon** (or complete only if product defines discard as complete — prefer abandon) |
| Status ask (“what am I working on?”, “what we have so far”) | **continue** or **none** — never complete |
| Detour Q&A while sole-continue is live | Usually **none** / suspend policy — not complete of the primary stream |
| Ambiguous classifier miss | Clarify or continue — not complete |

---

## 2. Session reorient and resume (portable)

When the user returns after a long idle gap while restorable multi-turn state exists:

1. **Show an honest gate** (Resume / Start Fresh) — do not silently run multi-LLM continue.
2. The gate turn is **CONTINUE**: the stream remains the owner; the journal must **not**
 write `task_completed` merely because a reorient card was shown.
3. **Resume** restores working state and **redisplays the checkpoint** (structure / IR /
 phase card) path-faithfully — not empty prose alone.
4. **Start Fresh** is the explicit terminal discard path (abandon/clear).

If reorient falsely COMPLETE’s the task, the next status leaf will invent a hollow
inventory of old suspended work and **contradict** the reorient card. That is a host
orchestration bug, not an LLM bug.

---

## 3. Adding a new multi-turn agent / kind

Laws are **agent-agnostic**. Scripts and kind names are **not** automatic for every
new specialist.

| Step | What | Portable? |
|---|---|---|
| **1. Declare law** | Kind id, exclusive-owner name, closed phases, pin fields, when begin/continue/complete/abandon are legal | Yes (KindSpec + this checklist) |
| **2. Implement writes** | Only `begin_task` / `update_phase` / `complete_task` / abandon via the sole writer; every envelope carries an explicit transition | Yes |
| **3. Seal** | Unit ratchets on dangerous call sites; **1–3 Conjecture scripts** for open → continue → steal-shaped → detour/terminal | Laws yes; script *instances* are host-specific |
| **4. Do not reuse other kinds’ goldens** | `cost_out_*` (or any product family) does not cover a new kind | Yes |

### Specialist checklist (minimum)

1. Register **KindSpec** (phases, pin keys, sole-continue membership). 
2. First sticky turn → **begin** with kind + phase + pins. 
3. Continue turns → **continue** + phase/pin updates only. 
4. Terminal success → **complete**; cancel → **abandon**. 
5. Tests: resume, complete, abandon ≠ complete, no auto-switch, no re-resolve after pin. 
6. Optional Conjecture: instantiate portable templates with *your* kind/owner strings 
 (see CBR `templates/` — sole-continue family + reorient-keeps-owner).

---

## 4. Laws vs goldens (Conjecture)

| Layer | What it is | Shared publicly? |
|---|---|---|
| **State law** | Sole-continue sticks; pin holds; COMPLETE ≠ reorient; exclusive owner beats steal | Yes — CCP + CBR invariant library |
| **Parameterized templates** | Same story shape, host fills `kind` / `exclusive_owner` / pin keys | Yes — CBR templates |
| **Product goldens** | Dogfood scripts for one host’s vocabulary | Host-private instances |

Conjecture is **not** “one script library that magically applies to every agent.” 
It is **freeze-safe regression for control-plane state law**, parameterized by **your**
ledger vocabulary.

---

## 5. DB session discipline (all conversational surfaces)

**Host / orchestrator doctrine** — not a specialist pattern, not Conjecture, not “agent personality.”
Monorepo map: 
(contract vs pattern vs host doctrine; Workflow Builder vs Bot0 copy templates).

**Separate from ownership transitions** — this is connection / lock law.

`claim_turn` and default `renew_turn_claim` open a **second** short-lived DB
session and `UPDATE conversations`. Ledger multi-key writes on the request
(or worker) session use `SELECT … FOR UPDATE`. If that TX is still open when
the second connection claims/renews → **self-deadlock** (worker hung forever;
local single-worker API unhealthy; AWS often “one chat stuck” with healthy ALB).

| Do | Don’t |
|---|---|
| Claim only via host helper `claim_turn_for_conversation(db, …)` | Bare `claim_turn(...)` after hygiene / decide / hydrate writes |
| `prepare_session_for_second_connection(db)` (session boundary commit) before any 2nd-conn op | Hope a random `db.commit` exists at this call site |
| Renew on the **same** open session (`renew_turn_claim(..., db=db)`) when the worker holds the row | Open a second connection for renew while holding FOR UPDATE |
| Commit boundary before long LLM awaits | Hold conversations-row locks across model latency |

**Monorepo owner:** `api/services/conversation_control/turn_session_discipline.py` 
**Primitives:** `commit_conversation_session_boundary` · `claim_turn` · `release_turn` 
**Applies to:** `/chat`, `/chat-stream`, `specialist agent_turn`, and any future
conversational agent entrypoint — **not** per-specialist invention.

Incidents: conv_66a6cced (SSE), conv_7a953788 (worker renew), conv_9c5f24a6 (hydrate→claim).

---

## 6. Coding-agent paste (host discipline)

```text
Host transition discipline (Conversation Control Plane):
- Specialists own their own phase machine; the ledger only records honest transitions.
- Surface must not lie: never advertise the next phase while this phase still blocks
 (e.g. "continue to staffing" while repair still needs "confirm fixes").
- Every specialist/async result that affects ownership MUST set an explicit
 transition: begin | continue | complete | abandon | none.
- Never COMPLETE because context_updates omitted agent_type or transition.
- Idle reorient / Resume gate = CONTINUE (active_task stays). Start Fresh = abandon.
- COMPLETE only on real product terminal (saved/committed/failed-closed as terminal).
- New multi-turn kind: declare KindSpec + pins + when COMPLETE is legal; implement
 only via ledger APIs; seal with unit ratchets + 1–3 Conjecture scripts for THAT
 kind; do not expect another product's goldens to cover it.
- Path-faithful: Resume redisplays the checkpoint surface, not empty prose.
- DB session law: claim only via claim_turn_for_conversation(db, …); never bare
 claim_turn after ledger writes; commit session boundary before 2nd-conn ops /
 long awaits; renew with db= when the lease session may hold the row.
```

---

## 7. Related

| Doc | Owns |
|---|---|
| SDK §2.1 multi-turn stream | Phase / pin / continue / finite grammar |
| SDK §3.1 concurrency | claim / row locks / session boundary |
| SDK §5 invariants | Single writer, COMPLETE≠ABANDON |
| Loop playbook | Orientation loops, hot-potato, stuck claims |
| CBR templates | Parameterized sole-continue + reorient goldens |
| CBR standard invariants | `exclusive_owner`, `pin_present`, `owner_not`, … |
| `turn_session_discipline` (host) | claim after boundary; renew same-session |
