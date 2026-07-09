# Examples

Sanitized **design stubs** only. No tenant data, no private product engines.

| Example | Pattern | Status |
|---|---|---|
| [`cyber_risk_assessment/`](cyber_risk_assessment/) | Bounded multi-turn specialist + async job ([SDK §9.1](../docs/conversation-control-plane-sdk.md) + [§2.1 multi-turn stream](../docs/conversation-control-plane-sdk.md#21-multi-turn-stream-contract-every-sole-continue-kind)) | Design stub |

**Copy:** ledger `kind`, phases, `TaskTransition`, `decide_turn` branch, multi-turn pin/phase gates.  
**Do not copy:** anything that would appear only in a private monorepo (scoring formulas, backlogs, real agents).
