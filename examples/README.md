# Examples

**Primary on-ramp is the package README** (design principles + kickoff prompt), not this folder.
SDK doc = spec.

| Example | Pattern | Status |
|---|---|---|
| [`e2e_host_loop.py`](e2e_host_loop.py) | Real package imports + COMPLETE≠ABANDON journal | **Runnable** after `pip install -e .` |
| [`cyber_risk_assessment/`](cyber_risk_assessment/) | Sole-continue + host sketch (KindSpec, thin payload, HITL VERIFY) | Optional scaffold — FakeLedger |
| [`integrations/`](integrations/) | Host wraps (Python / OpenAI-style / LangGraph) | **Sketches only** — not E2E product integrations |

**Copy if useful:** KindSpec, thin pins, `TaskTransition`, host sole writer.  
**Do not copy:** private monorepo scoring, full corpora, product UI.
