# Conversation Control Plane

**Infrastructure-first state machine for reliable multi-agent conversational AI.**

A DB-authoritative ledger + control plane that brings durable session ownership, deterministic handoffs, task lifecycle management, and strong auditability to multi-agent chat systems.

Built as a clean layer on top of execution frameworks like LangGraph, CrewAI, or custom agents.

### Key Features
- Publishable conversation ledger (`active_task`, `suspended_tasks`, `pending_switch`, `control_revision`, etc.)
- Single-writer `decide_turn` dispatcher
- `ConversationalAgent` protocol for specialists
- Strong invariants, concurrency safety, and production hardening
- Clean separation: LLM proposes intent → control plane enforces transitions

### Status
Reference implementation + integration contract (originally developed inside Bot0.ai).  
Currently in early extraction phase.

---

**Ideal for** teams building sophisticated multi-agent chat products that need reliable long-lived conversations, safe handoffs between specialists, and clear routing audit trails.
