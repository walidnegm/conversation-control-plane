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
    # concept_thread (glossary Q&A) — thin topic anchors only
    "concept_slugs",
    "concept_headline",
    "prior_query",
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
    # Content-strength gate (must stick across turns — conv_ccff5b7d loop).
    # Without these, every "help fill gaps" re-opens the same clarity card.
    "awaiting_content_strength",
    "content_strength_clarified",
    "content_strength",
    "content_strength_skip_reason",
    "draft_advance_intent",
    # Post-clarity invent stamp — must survive sanitize (conv_db94316d re-entry).
    "prefer_chat_first_sketch",
})

# kind=engagement_pack_plan: thin plan projection + pins for handoffs.
# Fat pack body lives behind pending_ref / session store — not ledger JSON
# (anti-pattern: fat IR/draft in control JSON · context choke).
# Without these keys, sanitize wiped payload to {} (conv_17a7b496 / conv_af7701c9).
ENGAGEMENT_PACK_CONTROL_PAYLOAD_KEYS: frozenset[str] = frozenset({
    "plan",
    "pack_text",  # allowed only when short; long bodies stripped below
    "pack_chars",
    "pack_pending_ref",  # pointer to specialist store (thin pin)
    "profile",
    "artifacts",
    "decomposition",
    "engagement_summary",  # Stage-1 LLM narrative (open card)
    "deep_extract_done",
    "awaiting_detail",
    "staff_proposals",
    "staff_as_is_ok",
    "staff_to_be_ok",
    "role_types_by_name",
})

# Soft max serialized size for the control payload (bytes).
CONTROL_PAYLOAD_MAX_BYTES = 4096
# Drafting stream may carry multi-step prose drafts; keep under a hard cap.
DRAFTING_CONTROL_PAYLOAD_MAX_BYTES = 24_576
# Engagement: thin plan only — pack body must not ride the ledger.
ENGAGEMENT_PACK_CONTROL_PAYLOAD_MAX_BYTES = 12_288
# Inline pack_text above this is stripped (use pack_pending_ref / session).
ENGAGEMENT_PACK_INLINE_TEXT_MAX = 400

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
    engagement_stream = kind_norm == "engagement_pack_plan"
    allowed = ALLOWED_CONTROL_PAYLOAD_KEYS
    if drafting_stream:
        allowed = ALLOWED_CONTROL_PAYLOAD_KEYS | DRAFTING_CONTROL_PAYLOAD_KEYS
    if engagement_stream:
        allowed = ALLOWED_CONTROL_PAYLOAD_KEYS | ENGAGEMENT_PACK_CONTROL_PAYLOAD_KEYS
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

    # Engagement: never keep fat pack_preview / pack_text on the ledger.
    if engagement_stream:
        plan = out.get("plan")
        if isinstance(plan, dict):
            plan2 = dict(plan)
            if "pack_preview" in plan2:
                if not out.get("pack_chars") and not plan2.get("pack_chars"):
                    try:
                        out["pack_chars"] = len(str(plan2.get("pack_preview") or ""))
                    except (TypeError, ValueError):
                        pass
                elif plan2.get("pack_chars") and not out.get("pack_chars"):
                    out["pack_chars"] = plan2.get("pack_chars")
                plan2.pop("pack_preview", None)
                stripped.append("plan.pack_preview")
            # Drop nested fat fields that still bloat plan (process dump, etc.)
            for fat_k in ("process_description", "pack_text", "raw_pack"):
                if fat_k in plan2 and len(str(plan2.get(fat_k) or "")) > 200:
                    plan2.pop(fat_k, None)
                    stripped.append(f"plan.{fat_k}")
            # Cap findings/evidence quotes
            findings = plan2.get("findings")
            if isinstance(findings, list) and len(findings) > 24:
                plan2["findings"] = findings[:24]
            out["plan"] = plan2
        pack_body = str(out.get("pack_text") or "")
        if len(pack_body) > ENGAGEMENT_PACK_INLINE_TEXT_MAX:
            out["pack_chars"] = out.get("pack_chars") or len(pack_body)
            out.pop("pack_text", None)
            stripped.append("pack_text")
        # decomposition can be huge — keep only thin pins
        decomp = out.get("decomposition")
        if isinstance(decomp, dict):
            thin_d = {
                k: decomp[k]
                for k in (
                    "interpreted_objectives",
                    "profile_hint",
                    "analysis_mode",
                    "source",
                    "summary",
                )
                if k in decomp
            }
            # Cap objective list
            objs = thin_d.get("interpreted_objectives")
            if isinstance(objs, list):
                thin_d["interpreted_objectives"] = objs[:8]
            if thin_d != decomp:
                stripped.append("decomposition.fat")
            out["decomposition"] = thin_d

    max_bytes = CONTROL_PAYLOAD_MAX_BYTES
    if drafting_stream:
        max_bytes = DRAFTING_CONTROL_PAYLOAD_MAX_BYTES
    elif engagement_stream:
        max_bytes = ENGAGEMENT_PACK_CONTROL_PAYLOAD_MAX_BYTES
    raw = json.dumps(out, default=str, separators=(",", ":"))
    if len(raw.encode("utf-8")) > max_bytes:
        # Drop / thin largest values until under cap. Never drop plan.steps —
        # empty spine makes Draft IR / Staff chips no-op (conv_99b2c64e).
        pin_keys = (
            "workflow_id",
            "project_id",
            "plan_id",
            "panel_session_id",
            "phase",
            "draft",
            "draft_handoff",
            "intake_seed",
            "pack_chars",
            "pack_pending_ref",
            "profile",
            "awaiting_detail",
            "mapping_confirmed",
            "deep_extract_done",
        )
        # Engagement: thin artifacts.deep_extract before touching plan spine
        if engagement_stream and isinstance(out.get("artifacts"), dict):
            arts = dict(out["artifacts"])
            de = arts.get("deep_extract")
            if isinstance(de, dict):
                de2 = dict(de)
                for fat_k, cap in (
                    ("pack_preview", 400),
                    ("process_description", 2500),
                    ("goal_summary", 500),
                    ("engagement_summary", 500),
                ):
                    if fat_k in de2 and len(str(de2.get(fat_k) or "")) > cap:
                        de2[fat_k] = str(de2.get(fat_k) or "")[:cap]
                        stripped.append(f"artifacts.deep_extract.{fat_k}")
                if isinstance(de2.get("quotes"), list) and len(de2["quotes"]) > 4:
                    de2["quotes"] = de2["quotes"][:4]
                    stripped.append("artifacts.deep_extract.quotes")
                if isinstance(de2.get("draft_ir_seed"), dict):
                    seed = dict(de2["draft_ir_seed"])
                    for sk in ("brief", "preview_head", "preview_tail"):
                        if sk in seed and len(str(seed.get(sk) or "")) > 400:
                            seed[sk] = str(seed.get(sk) or "")[:400]
                    de2["draft_ir_seed"] = seed
                    stripped.append("artifacts.deep_extract.draft_ir_seed")
                arts["deep_extract"] = de2
                out["artifacts"] = arts
            raw = json.dumps(out, default=str, separators=(",", ":"))
        for drop_key in sorted(
            out.keys(),
            key=lambda kk: len(json.dumps(out.get(kk), default=str)),
            reverse=True,
        ):
            if drop_key in pin_keys:
                continue
            if drop_key == "plan" and isinstance(out.get("plan"), dict):
                pl = dict(out["plan"])
                # Trim fat on plan but KEEP steps (sole-continue spine)
                pl.pop("findings", None)
                pl.pop("engagement_summary", None)
                pl.pop("pack_preview", None)
                pl.pop("interpreted_objectives", None)
                # Cap step blurbs if still huge
                steps = pl.get("steps")
                if isinstance(steps, list) and len(json.dumps(steps, default=str)) > 6000:
                    thin_steps = []
                    for s in steps:
                        if not isinstance(s, dict):
                            continue
                        row = {
                            k: s.get(k)
                            for k in (
                                "step_id", "label", "status", "optional",
                                "blocking_reason", "display_num", "phase_id",
                                "readiness", "chat_capable",
                            )
                            if k in s
                        }
                        thin_steps.append(row)
                    pl["steps"] = thin_steps
                    stripped.append("plan.steps_thin")
                else:
                    stripped.append("plan.findings_summary")
                out["plan"] = pl
                raw = json.dumps(out, default=str, separators=(",", ":"))
                if len(raw.encode("utf-8")) <= max_bytes:
                    break
                continue
            # Prefer dropping fat bags over plan spine
            if drop_key in ("decomposition", "engagement_summary", "staff_proposals"):
                stripped.append(drop_key)
                out.pop(drop_key, None)
                raw = json.dumps(out, default=str, separators=(",", ":"))
                if len(raw.encode("utf-8")) <= max_bytes:
                    break
                continue
            if drop_key == "artifacts" and isinstance(out.get("artifacts"), dict):
                # Keep thin pins only
                arts = out["artifacts"]
                keep = {
                    k: arts[k]
                    for k in (
                        "as_is_workflow_id", "to_be_workflow_id", "workflow_id",
                        "staff_as_is_ok", "staff_to_be_ok", "deep_extract_done",
                        "role_types_by_name",
                    )
                    if k in arts
                }
                # Keep process seed head only if still present
                de = arts.get("deep_extract")
                if isinstance(de, dict):
                    keep["deep_extract"] = {
                        k: de.get(k)
                        for k in (
                            "goal_summary", "process_description", "pack_chars",
                            "dual_world_detected", "findings_count",
                        )
                        if de.get(k) is not None
                    }
                    proc = str(keep["deep_extract"].get("process_description") or "")
                    if len(proc) > 2000:
                        keep["deep_extract"]["process_description"] = proc[:2000]
                out["artifacts"] = keep
                stripped.append("artifacts.fat")
                raw = json.dumps(out, default=str, separators=(",", ":"))
                if len(raw.encode("utf-8")) <= max_bytes:
                    break
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
    "ENGAGEMENT_PACK_CONTROL_PAYLOAD_KEYS",
    "ENGAGEMENT_PACK_CONTROL_PAYLOAD_MAX_BYTES",
]
