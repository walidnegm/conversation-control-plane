# Conversational Routing as Authority Adjudication (portable note)

**Companion to** [conversation-control-plane-sdk.md](conversation-control-plane-sdk.md) 
**Not** a second control plane. This note is the **cognitive architecture** of one turn;
the SDK is the **implementation contract** for authority (ledger, `decide_turn`, sole writer).

**Where this package sits in the pipeline** (canonical tables live in
[SDK §0.0.2](conversation-control-plane-sdk.md#authority-adjudication-pipeline-sdk-seat)):

| Essay layer | SDK role (implementation) | App role |
|-------------|---------------------------|----------|
| **0 Hydration** | Ledger projection / KindSpec / pins = SoR the View is built from | Builds the brief (`allowed_operations`, surface map) |
| **1 Semantic** | Law only: meaning → closed enums, never free-text authority | Classifiers, op enum *values*, schemas |
| **2 Adjudication** | **Core:** `decide_turn`, sole writer, exclusive owner, A18 allow-list shape | Which leaves / EXTRA rows |
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

The package does **not** hardcode product continuum tables or classifier field lists.
Extension-point shapes: [SDK §2.1.x](conversation-control-plane-sdk.md#21x-extension-points-enums-kinds-surfaces-continuum).

## Non-negotiable invariant

> **No negative result** (unsupported op, policy defer, unarmed affirm, validation fail)
> **is permission to fall through into an unowned conversational path.**

`UNSUPPORTED` stays with the owner (re-show card / clarify / refuse) — never
`return None` → default freestyle node.

## Closed enums, kinds, surfaces, continuum

| Extension | Package requires | App defines |
|-----------|------------------|-------------|
| Operation / meaning enums | Schema-validated closed set | Values (`SET_FIELD`… or product-act ids) |
| Task kinds + phases | Registered streams; phase owns dispatch | Your product streams |
| Product surfaces | Literacy so proposals can be adjudicated | Leaf / card map |
| Continuum edges | Invite + same-turn pin + armed-only affirm | Edge inventory + chip `send_text` |

## Graph runtimes (LangGraph, …)

Keep for **execution** (Layer 4). Conditional edges should **pre-adjudicate** (owner +
typed proposal + policy) before choosing a target node. This package’s
`claim → decide_turn → handle → apply → release` is the product-chat form of that law.

## Failure modes (proof package)

Named authority modes + Conjecture seeds live in the sibling public package
**[conjecture-behaviour-runner](https://github.com/walidnegm/conjecture-behaviour-runner)**
(`incidents/registry.yaml`). This SDK owns **anti-patterns A1–A19** and the diagnostic
ladder; CBR owns **mode slugs + runnable proofs**.

| Need | Where |
|------|--------|
| Adopt ledger + decide | This package |
| Named mode + seed + FAIL-planted discipline | Conjecture Behaviour Runner |
| Diagnostic ladder / seal recipe | [conversational-authority-diagnostic-taxonomy.md](conversational-authority-diagnostic-taxonomy.md) |

## One-line summary

> **Hydrate View from ledger. LLM proposes closed enums. SDK adjudicates ownership.
> Policy tables constrain. App executes. Product voice delivers; continuum advances
> only when armed.**
