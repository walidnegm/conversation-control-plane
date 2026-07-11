# Integration wraps — control the agent, don't rewrite it

These sketches show the **host loop** around an existing agent runtime.
They are **not** full packages and do not call a live LLM.

| File | Runtime |
|---|---|
| [`wrap_python_loop.py`](wrap_python_loop.py) | Raw Python specialist |
| [`wrap_openai_loop.py`](wrap_openai_loop.py) | OpenAI-style chat/tool loop (pseudocode API) |
| [`wrap_langgraph.py`](wrap_langgraph.py) | LangGraph invoke *inside* one specialist turn |

**Invariant:** the agent returns a transition intent; the **host** calls ledger APIs.
Never `from ledger import begin_task` inside the specialist module.

See also the multi-turn design stub: [`../cyber_risk_assessment/`](../cyber_risk_assessment/).
