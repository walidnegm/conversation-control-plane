"""B5 — strict control_payload for ledger ``active_task.payload``.

Ledger may carry **pins, gates, and thin identity only**. Domain artifacts
(IR, draft body, graph, strategist blobs) live behind ``pending_ref`` in the
specialist's store — never as control authority.

Enforced at ``begin_task`` / ``update_phase`` via :func:`sanitize_control_payload`.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Optional

# Keys that must never be stored on the ledger control projection.
# Exception: kind=drafting may carry a bounded ``draft`` / ``intake_seed`` —
# that stream has no separate specialist store yet; stripping them caused
# staging interpret loops (UI showed steps, ledger always steps=0).
FORBIDDEN_CONTROL_PAYLOAD_KEYS: frozenset[str] = frozenset({
    "ir",
    "draft",
    "graph",
    "graph_json",
    "strategist_payload",
    "strategist_preview",
    "canonical_spec",
    "task_table",
    "intent_json",
    "full_ir",
    "workflow_ir",
    "builder_pending",
})

# Allowlisted pin / gate / identity fields (plus kind-specific thin keys).
ALLOWED_CONTROL_PAYLOAD_KEYS: frozenset[str] = frozenset({
    # Entity pins
    "workflow_id",
    "workflow_name",
    "project_id",
    "project_name",
    "scenario_id",
    "run_id",
    "profile_id",
    "plan_id",
    "panel_session_id",
    "assessment_session_id",
    "risk_id",
    "recent_risk_ids",
    "category",
    # Phase / gate mirrors (thin)
    "phase",
    "gates",
    "gate_id",
    "awaiting_field",
    "agent_label",
    "pending_pick_purpose",
    "focus_categories",
    "verify_choice",
    "artifact_version",
    "artifact_hash",
    # O&V flat scorecard pins (not nested IR)
    "unit_of_flow_label",
    "baseline_annual_units",
    "revenue_per_unit_usd",
    "workflow_type",
    "absorption_ratio",
    "opportunity_cost_per_unit_usd",
    # Cost thin
    "chat_seed",  # still bounded by max bytes below
    "awaiting_gap",
    "intake_focus_field",
    "gap_context",  # thin pointers only — sanitized for size
    # Catalog role create (thin identity only — bulk previews stay off-ledger)
    "role_name",
    "bulk_count",
    "catalog_phase",
})

# kind=drafting / handoff: carried process draft (not WorkflowIR). Bounded below.
DRAFTING_CONTROL_PAYLOAD_KEYS: frozenset[str] = frozenset({
    "draft",
    "draft_handoff",
    "intake_seed",
    "domain",
    "awaiting_intake_choice",
    "intake",
    "intake_fork_resolved",
})

# Soft max serialized size for the control payload (bytes).
CONTROL_PAYLOAD_MAX_BYTES = 4096
# Drafting stream may carry multi-step prose drafts; keep under a hard cap.
DRAFTING_CONTROL_PAYLOAD_MAX_BYTES = 24_576

CODE_CONTROL_PAYLOAD_INVALID = "control_payload_invalid"


class ControlPayloadError(Exception):
    """Raised when a payload cannot be sanitized to a valid control_payload."""

    def __init__(self, message: str, *, stripped: Optional[list[str]] = None) -> None:
        self.code = CODE_CONTROL_PAYLOAD_INVALID
        self.stripped = list(stripped or [])
        super().__init__(message)


def sanitize_control_payload(
    payload: Optional[Mapping[str, Any]],
    *,
    kind: Optional[str] = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Return a ledger-safe control_payload.

    * Drops :data:`FORBIDDEN_CONTROL_PAYLOAD_KEYS` (IR/graph/…; ``draft`` except
      for ``kind=drafting`` / ``workflow_build`` handoff).
    * When ``strict``, drops unknown keys not in the allowlist.
    * Enforces size cap (:data:`CONTROL_PAYLOAD_MAX_BYTES`, or drafting cap).
    """
    if not payload:
        return {}
    if not isinstance(payload, Mapping):
        raise ControlPayloadError("control_payload must be a mapping")

    kind_norm = (kind or "").strip().lower()
    drafting_stream = kind_norm in ("drafting", "workflow_build")
    allowed = ALLOWED_CONTROL_PAYLOAD_KEYS
    if drafting_stream:
        allowed = ALLOWED_CONTROL_PAYLOAD_KEYS | DRAFTING_CONTROL_PAYLOAD_KEYS
    # IR/graph still always forbidden; draft body only for drafting stream.
    forbidden = FORBIDDEN_CONTROL_PAYLOAD_KEYS
    if drafting_stream:
        forbidden = FORBIDDEN_CONTROL_PAYLOAD_KEYS - {"draft"}

    stripped: list[str] = []
    out: dict[str, Any] = {}
    for key, value in payload.items():
        k = str(key or "").strip()
        if not k:
            continue
        if k in forbidden:
            stripped.append(k)
            continue
        if strict and k not in allowed:
            stripped.append(k)
            continue
        out[k] = value

    # Nested IR sneak-path: gates must stay small dicts of booleans/strings.
    gates = out.get("gates")
    if isinstance(gates, dict):
        out["gates"] = {
            str(gk): gv
            for gk, gv in gates.items()
            if isinstance(gv, (bool, int, float, str, type(None), dict))
        }

    max_bytes = (
        DRAFTING_CONTROL_PAYLOAD_MAX_BYTES
        if drafting_stream
        else CONTROL_PAYLOAD_MAX_BYTES
    )
    raw = json.dumps(out, default=str, separators=(",", ":"))
    if len(raw.encode("utf-8")) > max_bytes:
        # Drop largest string-ish values until under cap (preserve pins + draft.steps).
        pin_keys = (
            "workflow_id",
            "project_id",
            "plan_id",
            "panel_session_id",
            "phase",
            "draft",
            "draft_handoff",
            "intake_seed",
        )
        for drop_key in sorted(
            out.keys(),
            key=lambda kk: len(json.dumps(out.get(kk), default=str)),
            reverse=True,
        ):
            if drop_key in pin_keys:
                continue
            stripped.append(drop_key)
            out.pop(drop_key, None)
            raw = json.dumps(out, default=str, separators=(",", ":"))
            if len(raw.encode("utf-8")) <= max_bytes:
                break
        if len(raw.encode("utf-8")) > max_bytes:
            raise ControlPayloadError(
                f"control_payload exceeds {max_bytes} bytes after sanitize",
                stripped=stripped,
            )
    return out


def assert_control_payload_clean(payload: Optional[Mapping[str, Any]]) -> None:
    """Raise if payload still contains forbidden keys (post-sanitize check)."""
    if not payload:
        return
    bad = sorted(set(payload.keys()) & FORBIDDEN_CONTROL_PAYLOAD_KEYS)
    if bad:
        raise ControlPayloadError(
            f"control_payload contains forbidden keys: {bad}",
            stripped=bad,
        )


__all__ = [
    "ALLOWED_CONTROL_PAYLOAD_KEYS",
    "CODE_CONTROL_PAYLOAD_INVALID",
    "CONTROL_PAYLOAD_MAX_BYTES",
    "DRAFTING_CONTROL_PAYLOAD_KEYS",
    "DRAFTING_CONTROL_PAYLOAD_MAX_BYTES",
    "ControlPayloadError",
    "FORBIDDEN_CONTROL_PAYLOAD_KEYS",
    "assert_control_payload_clean",
    "sanitize_control_payload",
]
