"""decide_turn — the deterministic entry point for conversation routing decisions.

This is the heart of the P2/P3 substrate (the "orchestrator" as a package, not an agent).

decide_turn is **AUTHORITATIVE for dispatch** (the D1 flip landed): it runs very early in
bot0.py:chat (after load + prune, before sticky blocks or heavy dispatch), and its returned
``TurnPlan.agent`` drives ``effective_intent`` (bot0.py ~2237). The live
``classify_intent_route`` result is passed in as ``live_route_intent`` — a proxy / cross-check,
NOT the authority.

It:
- consults the ledger first (active_task, suspended_tasks, pending_switch, plan) for the
  deterministic decisions (steps 1-4, 6);
- uses the LLM ``classify_intent`` only as PERCEPTION inside Step 4 (what this turn wants
  relative to the active task); the TRANSITION (suspend / switch / resume) is owned here,
  deterministically — classifier flakiness must never flip a transition;
- performs the ledger writes (begin_task, suspend_active, update_phase, resume_task, …) for
  the case it decides;
- emits ``ledger_agent_type_conflict`` when its plan disagrees with the live router (telemetry).

The 7-step algorithm below is the epic's spec. The control-plane regression suite
(``regression_suite/test_decide_turn_control_plane.py``) pins this logic with the classifier
mocked, so routing is testable independent of the LLM. The known active-task-continue
**MISROUTE** (Control-Plane & Ledger Hardening epic §3) is captured there as xfail cases,
pending the S2 precedence fix.

NOTE: ``reason`` strings on ``TurnPlan`` are surfaced in the Routing debug strip — keep them
human-readable (no epic phase codes like "P2a"). decide_turn is authoritative for dispatch.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from conversation_control_plane.contract import (
    ActiveTask,
    PendingSwitch,
    TurnPlan,
    WORKFLOW_BUILD_KIND,
    canonical_agent,
    ledger_kind_for_agent,
)
from conversation_control_plane.ledger import (
    get_control_state,
    propose_switch,
    begin_task,
    update_phase,
    suspend_active,
    resume_task,
    complete_task,
    _emit,
)

logger = logging.getLogger(__name__)


def _perceive_relative_intent(
    db: Any,
    tenant_id: str,
    *,
    query: str,
    active_task: Optional[dict] = None,
    suspended_tasks: Optional[list] = None,
    messages: Optional[list] = None,
    unified_signal: Any = None,
) -> Any:
    """Relative task perception for decide_turn — no duplicate LLM when S4 signal exists."""
    from conversation_control_plane.classifier import classify_intent, _fast_path

    fp = _fast_path(query, active_task)
    if fp is not None:
        return fp
    if unified_signal is not None:
        from conversation_control_plane.unified_turn_router import (
            intent_result_from_unified,
        )
        return intent_result_from_unified(unified_signal)
    return classify_intent(
        db, tenant_id, query=query,
        active_task=active_task, suspended_tasks=suspended_tasks,
        messages=messages,
    )


def decide_turn(
    *,
    db: Any,
    tenant_id: str,
    conversation_id: Optional[str],
    query: str,
    context: Optional[dict],
    live_route_intent: str,           # the current _route.intent from classify_intent_route
    live_route_layer: str,
    pending_switch_from_context: Optional[dict] = None,
    prior_agent_type: Optional[str] = None,
    messages: Optional[list] = None,
    workflow_draft_request: bool = False,  # _route.workflow_draft_request (produce-a-workflow)
    live_route: Optional[dict] = None,  # S4: full rich signal for collapse (includes discovery etc)
    unified_signal: Any = None,  # S4: UnifiedTurnSignal — avoids 2nd conversation_intent_classifier hop
) -> TurnPlan:
    """decide_turn — the AUTHORITATIVE control-plane dispatch decision (D1 flip).

    Returns the TurnPlan that drives dispatch. Always writes the ledger state
    (active_task / pending_switch / suspended) via the ledger single-writer
    API and emits `ledger_agent_type_conflict` (with rich reason) when its
    plan disagrees with what the live router said (telemetry).

    Implements the epic's 7-step algorithm (deterministic first, classifier
    last). `live_route_intent` / `live_route_layer` carry the router's
    classification as an input signal.

    T2 (turn-integrity epic): the ledger transitions this calls now WRITE
    THROUGH to the conversations.agent_type summary column — the ledger's
    active_task.agent is the single authority and the column is its
    denormalized summary (the P2a "never touch the column" rule is retired).
    """
    def _canonical(a: str) -> str:
        return canonical_agent(a) or a  # single source (contract.canonical_agent)

    live_route_intent = _canonical(live_route_intent)
    q = (query or "").strip().lower()

    if not conversation_id:
        return TurnPlan(agent=live_route_intent or "bot0", mode="fresh",
                        reason="no conversation_id")

    control = get_control_state(db, tenant_id, conversation_id)
    current_active = control.get("active_task")
    current_pending = control.get("pending_switch") or pending_switch_from_context
    suspended = control.get("suspended_tasks") or []
    current_plan = control.get("plan")

    cost_estimate_request = False
    if live_route is not None:
        if hasattr(live_route, "cost_estimate_request"):
            cost_estimate_request = bool(getattr(live_route, "cost_estimate_request", False))
        elif isinstance(live_route, dict):
            cost_estimate_request = bool(live_route.get("cost_estimate_request"))

    # Live agent cost preview — LLM-owned signal on IntentRoute (not a keyword gate).
    # Multi-turn: kind=cost_out continues without clearing; otherwise open cost_out.
    if cost_estimate_request:
        from conversation_control_plane.task_pin_contract import (
            COST_OUT_KIND,
            ensure_cost_out_task,
        )

        if (
            isinstance(current_active, dict)
            and current_active.get("kind") == COST_OUT_KIND
        ):
            active_task_obj = ActiveTask(**{
                k: v for k, v in current_active.items()
                if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")
            })
            return TurnPlan(
                agent="bot0",
                mode="continue",
                task=active_task_obj,
                reason="cost_out sole-continue (active_task.kind=cost_out)",
            )
        if current_active:
            try:
                complete_task(
                    db,
                    tenant_id,
                    conversation_id,
                    agent=current_active.get("agent") or "bot0",
                    reason="superseded",
                    task_id=(
                        current_active.get("task_id")
                        if isinstance(current_active.get("task_id"), str)
                        else None
                    ),
                )
            except Exception:  # noqa: BLE001
                pass
        try:
            ensure_cost_out_task(
                db,
                tenant_id,
                conversation_id,
                phase="open",
            )
        except Exception:  # noqa: BLE001
            pass
        return TurnPlan(
            agent="bot0",
            mode="answer",
            reason="LLM classified live agent cost estimate; opened cost_out task",
        )

    # S2 coherence epic: demote discovery to ledger task.
    # Router emits discovery_kind; here we open bot0-owned discovery task
    # instead of letting early caller short-circuit with answer.
    # This makes "what do we have setup" a resumable task that consults live ledger.
    discovery_kind = "none"
    if live_route:
        if hasattr(live_route, 'discovery_kind'):
            discovery_kind = getattr(live_route, 'discovery_kind') or "none"
        elif isinstance(live_route, dict):
            discovery_kind = live_route.get('discovery_kind') or "none"
    from conversation_control_plane.delivery_order_contract import (
        is_front_door_detour_kind,
    )

    dk = (discovery_kind or "none").strip().lower()
    if dk != "none" and is_front_door_detour_kind(dk):
        active_task_obj = None
        if current_active:
            active_task_obj = ActiveTask(**{
                k: v for k, v in current_active.items()
                if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")
            })
        else:
            try:
                begin_task(
                    db, tenant_id, conversation_id,
                    agent="bot0",
                    kind="discovery",
                    phase="active",
                    awaiting=dk,
                    task_text=f"discovery:{dk}",
                )
            except Exception:  # noqa: BLE001
                pass
        return TurnPlan(
            agent="bot0",
            mode="discovery" if not current_active else "detour",
            task=active_task_obj,
            reason=(
                f"discovery task opened for kind={dk}"
                if not current_active
                else f"discovery detour ({dk}) supersedes active task"
            ),
            discovery_kind=dk,
        )

    # S3: Simulate/optimize → recommender handoff (not stale builder task).
    # After S1 hygiene (complete on build), no stale active; here ensure
    # if live route is recommender/advisor + workflow ref, handoff.
    # live_route_intent already classifies "simulate this workflow" etc.
    if live_route_intent in ("recommender", "advisor", "transformation_recommender", "transformation_advisor"):
        wf_ref = (context or {}).get("workflow_id") or (context or {}).get("last_read_workflow_id")
        if wf_ref:
            if current_active:
                try:
                    complete_task(
                        db,
                        tenant_id,
                        conversation_id,
                        agent=current_active.get("agent") or "bot0",
                        reason="superseded",
                        task_id=(
                            current_active.get("task_id")
                            if isinstance(current_active.get("task_id"), str)
                            else None
                        ),
                    )
                except Exception:  # noqa: BLE001
                    pass
            target = _canonical(
                getattr(live_route, "target_agent", None)
                or live_route_intent
                if live_route
                else live_route_intent
            )
            try:
                begin_task(
                    db,
                    tenant_id,
                    conversation_id,
                    agent=target,
                    phase="active",
                    awaiting="in_progress",
                    pending_ref=f"{target}:{conversation_id}",
                )
            except Exception:  # noqa: BLE001
                pass
            return TurnPlan(
                agent=target,
                mode="handoff",
                reason=f"simulate/optimize on {wf_ref} → {target} handoff (S3/S4 rich)",
            )

    # P4c: active multi-task orchestrator plan takes precedence for routing.
    # If there is a persisted plan with pending/executing work, return a plan-directed
    # TurnPlan so the caller (bot0) can engage orchestrate_plan instead of single-agent.
    # This is the hook for plan-aware resume and continuation across turns.
    if current_plan:
        tasks = current_plan.get("tasks") or []
        if any(
            isinstance(t, dict) and t.get("status") in (None, "pending", "executing")
            for t in tasks
        ):
            plan = TurnPlan(
                agent="bot0",  # orchestrator cognition layer will be engaged by caller when mode=="plan"
                mode="plan",
                reason="active plan with unfinished tasks; orchestrate delegation / resume / repair",
            )
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent, live_route_layer,
                                "active orchestrator plan present")
            return plan

    # --- Step 1: command layer ---
    # EXACT, unambiguous discard commands only — deterministic full-message matches,
    # not NL cognition. "start over" is intentionally NOT here: it is context-dependent
    # (restart THIS task vs begin something NEW), so the LLM classifier must own it, not
    # a wordlist inside the control plane (conv_9594c5). Mirrors the same removal from
    # classifier._EXACT_RESET_COMMANDS (commit 27f8a927) — this was the duplicate that
    # still hard-mapped "start over" -> abandon and defeated that fix.
    from conversation_control_plane.reset_commands import is_exact_reset_command

    if is_exact_reset_command(q):
        if control.get("pending_question"):
            from conversation_control_plane.ledger import clear_pending_question

            clear_pending_question(
                db, tenant_id, conversation_id, reason="user_reset",
            )
        # COMPLETE ≠ ABANDON: exact reset clears active ownership via abandon
        # (distinct journal event type — not the success complete path).
        if isinstance(current_active, dict) and current_active:
            try:
                _agent = str(current_active.get("agent") or "bot0")
                complete_task(
                    db,
                    tenant_id,
                    conversation_id,
                    agent=_agent,
                    reason="abandon",
                    task_id=(
                        current_active.get("task_id")
                        if isinstance(current_active.get("task_id"), str)
                        else None
                    ),
                )
            except Exception:  # noqa: BLE001 — never block command ack on journal glitch
                logger.debug("reset abandon complete_task failed", exc_info=True)
        plan = TurnPlan(
            agent="bot0",
            mode="command",
            reason="Reset command — abandon",
        )
        _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent, live_route_layer, "command")
        return plan

    # --- Step 2/3: confirmed_intent and pending_switch reply (use passed data + live_route) ---
    # These must be resolved from *server* pending_switch state (not just FE field).
    # Typed replies ("switch", "stay", "yes", etc.) are parsed by code (classify_pending_switch_reply
    # in the shim/ledger layer), never by the classifier.
    # In P2a the actual ledger.propose/resolve calls happen via the mirrors in bot0.py and worker.
    if current_pending:
        plan = TurnPlan(
            agent=_canonical(current_pending.get("to_agent", live_route_intent)),
            mode="switch_confirm",
            reason="Pending agent switch awaiting confirmation",
        )
        _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent, live_route_layer,
                            "pending_switch present")
        # For P2a we let the live path (mirrors we added) do the actual propose/resolve writes
        return plan

    # --- Step 2.5: ledger-tracked pending_question (CAQ-3) ---
    # A bot0 detour pick-list owns the next finite-grammar reply so sticky builder
    # sessions cannot intercept a bare "2".
    current_pending_q = control.get("pending_question")
    if current_pending_q:
        from conversation_control_plane.pending_question import (
            is_finite_grammar_pick as _is_finite_pick,
            pending_question_is_stale as _pending_q_stale,
        )
        from conversation_control_plane.ledger import clear_pending_question

        if _pending_q_stale(current_pending_q, db=db):
            clear_pending_question(
                db, tenant_id, conversation_id, reason="stale_prune",
            )
        elif _is_finite_pick(query, current_pending_q):
            plan = TurnPlan(
                agent="bot0",
                mode="pending_question",
                reason="pending_question numeric pick",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "pending_question pick",
            )
            return plan
        else:
            # Systemic: ordinal_stream_contract owns same-turn open vs supersede.
            from conversation_control_plane.ordinal_stream_contract import (
                should_supersede_pending_on_non_pick as _should_super_pq,
            )

            if _should_super_pq(current_pending_q, query, db=db):
                clear_pending_question(
                    db, tenant_id, conversation_id, reason="superseded",
                )

    # --- Step 2.75: referential artifact binding (CAQ unified) ---
    # When the ledger holds an active artifact (draft, etc.), short referential
    # replies bind to it BEFORE generic active_task heuristics or a stale
    # workflow_builder session can run extraction on bare text ("Built it").
    try:
        from conversation_control_plane.referential_turn import (
            discover_active_artifact,
            plan_from_referential_binding,
            resolve_referential_binding,
        )

        _ref_artifact = discover_active_artifact(control)
        if _ref_artifact is not None:
            _ref_binding = resolve_referential_binding(
                db, tenant_id, query=query, artifact=_ref_artifact, messages=messages,
            )
            if _ref_binding is not None:
                plan = plan_from_referential_binding(
                    _ref_binding,
                    db=db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    control=control,
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "referential artifact binding",
                )
                return plan
    except Exception:  # noqa: BLE001 — referential binding must never explode routing
        logger.debug("referential artifact binding skipped", exc_info=True)

    # --- Step 2b: FE confirmed_switch (surface-action / clarification card) ---
    # A button click with confirmed_intent is deterministic — it must override active_task
    # stickiness. Without this, Step 4's active_task continue wins over the live router's
    # confirmed target (conv_7115bcdd: Rewire Work → editor greeting instead of recommender).
    if live_route_layer == "confirmed_switch" and live_route_intent:
        target = live_route_intent
        active_agent = _canonical((current_active or {}).get("agent", "")) if current_active else None
        if active_agent and active_agent != target:
            suspend_active(db, tenant_id, conversation_id, reason="confirmed_switch")
        if not current_active or active_agent != target:
            _target_kind = ledger_kind_for_agent(target)
            begin_task(
                db, tenant_id, conversation_id, agent=target,
                phase="active", awaiting="in_progress",
                kind=_target_kind,
                pending_ref=f"{target}:{conversation_id}",
            )
            task_obj = ActiveTask(
                agent=target, phase="active", awaiting="in_progress",
                kind=_target_kind,
            )
        else:
            task_obj = ActiveTask(**{k: v for k, v in current_active.items()
                                     if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")})
        plan = TurnPlan(
            agent=target,
            mode="active_task",
            task=task_obj,
            reason=f"confirmed_switch to {target}",
        )
        _maybe_log_conflict(
            db, tenant_id, conversation_id, plan, live_route_intent, live_route_layer,
            "confirmed_switch",
        )
        return plan

    _active_kind = (current_active or {}).get("kind")

    # --- Step 3.4: ledger-tracked outcome value setup (Lane 2a / §4e P3) ---
    if _active_kind == "outcome_value_setup":
        active_task_obj = ActiveTask(**{
            k: v for k, v in current_active.items()
            if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")
        })
        perceived = None
        intent = None
        intent_source = "heuristic"
        try:
            perceived = _perceive_relative_intent(
                db, tenant_id, query=query,
                active_task=current_active, suspended_tasks=suspended,
                messages=messages, unified_signal=unified_signal,
            )
            intent, intent_source = perceived.intent, perceived.source
        except Exception:  # noqa: BLE001 — perception must never explode routing
            logger.debug(
                "outcome_value_setup classifier failed → continue",
                exc_info=True,
            )

        if intent == "abandon":
            complete_task(
                db, tenant_id, conversation_id, agent="bot0",
                reason="abandon",
                task_id=(
                    current_active.get("task_id")
                    if isinstance(current_active.get("task_id"), str)
                    else None
                ),
            )
            plan = TurnPlan(
                agent="bot0",
                mode="command",
                reason=f"outcome_value_setup abandoned ({intent_source})",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "outcome_value_setup abandoned",
            )
            return plan

        _detour_conf = float(getattr(perceived, "confidence", 0.0) or 0.0)
        if intent == "detour" and _detour_conf >= 0.5:
            plan = TurnPlan(
                agent="bot0",
                mode="detour",
                task=active_task_obj,
                reason=f"outcome_value_setup detour ({intent_source})",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "outcome_value_setup detour",
            )
            return plan

        plan = TurnPlan(
            agent="bot0",
            mode="active_task",
            task=active_task_obj,
            reason="outcome value setup in progress",
        )
        _maybe_log_conflict(
            db, tenant_id, conversation_id, plan, live_route_intent,
            live_route_layer, "outcome_value_setup continue",
        )
        return plan

    # --- Step 3.4b: ledger-tracked realization intake (deploy walkthrough) ---
    if _active_kind == "realization_intake":
        active_task_obj = ActiveTask(**{
            k: v for k, v in current_active.items()
            if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")
        })
        perceived = None
        intent = None
        intent_source = "heuristic"
        try:
            perceived = _perceive_relative_intent(
                db, tenant_id, query=query,
                active_task=current_active, suspended_tasks=suspended,
                messages=messages, unified_signal=unified_signal,
            )
            intent, intent_source = perceived.intent, perceived.source
        except Exception:  # noqa: BLE001
            logger.debug(
                "realization_intake classifier failed → continue",
                exc_info=True,
            )

        if intent == "abandon":
            complete_task(
                db, tenant_id, conversation_id, agent="bot0",
                reason="abandon",
                task_id=(
                    current_active.get("task_id")
                    if isinstance(current_active.get("task_id"), str)
                    else None
                ),
            )
            plan = TurnPlan(
                agent="bot0",
                mode="command",
                reason=f"realization_intake abandoned ({intent_source})",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "realization_intake abandoned",
            )
            return plan

        _detour_conf = float(getattr(perceived, "confidence", 0.0) or 0.0)
        if intent == "detour" and _detour_conf >= 0.5:
            plan = TurnPlan(
                agent="bot0",
                mode="detour",
                task=active_task_obj,
                reason=f"realization_intake detour ({intent_source})",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "realization_intake detour",
            )
            return plan

        plan = TurnPlan(
            agent="bot0",
            mode="active_task",
            task=active_task_obj,
            reason="realization intake in progress",
        )
        _maybe_log_conflict(
            db, tenant_id, conversation_id, plan, live_route_intent,
            live_route_layer, "realization_intake continue",
        )
        return plan

    # --- Step 3.4c: ledger-tracked cyber risk assessment ---
    if _active_kind == "cyber_risk_assessment":
        active_task_obj = ActiveTask(**{
            k: v for k, v in current_active.items()
            if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")
        })
        perceived = None
        intent = None
        intent_source = "heuristic"
        try:
            perceived = _perceive_relative_intent(
                db, tenant_id, query=query,
                active_task=current_active, suspended_tasks=suspended,
                messages=messages, unified_signal=unified_signal,
            )
            intent, intent_source = perceived.intent, perceived.source
        except Exception:  # noqa: BLE001
            logger.debug(
                "cyber_risk_assessment classifier failed → continue",
                exc_info=True,
            )

        if intent == "abandon":
            complete_task(
                db, tenant_id, conversation_id, agent="bot0",
                reason="abandon",
                task_id=(
                    current_active.get("task_id")
                    if isinstance(current_active.get("task_id"), str)
                    else None
                ),
            )
            plan = TurnPlan(
                agent="bot0",
                mode="command",
                reason=f"cyber_risk_assessment abandoned ({intent_source})",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "cyber_risk_assessment abandoned",
            )
            return plan

        _detour_conf = float(getattr(perceived, "confidence", 0.0) or 0.0)
        if intent == "detour" and _detour_conf >= 0.5:
            plan = TurnPlan(
                agent="bot0",
                mode="detour",
                task=active_task_obj,
                reason=f"cyber_risk_assessment detour ({intent_source})",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "cyber_risk_assessment detour",
            )
            return plan

        plan = TurnPlan(
            agent="bot0",
            mode="active_task",
            task=active_task_obj,
            reason="cyber risk assessment in progress",
        )
        _maybe_log_conflict(
            db, tenant_id, conversation_id, plan, live_route_intent,
            live_route_layer, "cyber_risk_assessment continue",
        )
        return plan

    # --- Step 3.5: ledger-tracked DRAFTING task (CAQ-7) ---
    # A "produce a workflow for me" request (workflow_draft signal) opens a bot0-owned
    # drafting task. While it is active, the drafting task OWNS refinement turns:
    # "make MRI and CAT scan parallel" is a draft edit, not a fresh Workflow Builder
    # extraction. Only an LLM-perceived handoff to workflow_builder releases it.
    if _active_kind == "drafting":
        active_task_obj = ActiveTask(**{k: v for k, v in current_active.items()
                                        if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")})
        _draft_payload = (current_active or {}).get("payload") or {}
        _carried_draft = _draft_payload.get("draft")
        intent: str | None = None
        target = ""
        confidence = 0.0
        if isinstance(_carried_draft, dict) and _carried_draft.get("steps"):
            try:
                from conversation_control_plane.prose_intake_contract import (
                    resolve_carried_draft_turn_kind,
                )

                _draft_turn, _aff_conf = resolve_carried_draft_turn_kind(
                    db,
                    tenant_id,
                    query=query,
                    unified=unified_signal,
                    messages=messages,
                    active_task=current_active,
                    payload=_draft_payload,
                )
                if _draft_turn in ("interpret", "build") and _aff_conf >= 0.5:
                    intent = "handoff"
                    target = "workflow_builder"
                    confidence = _aff_conf
            except Exception:  # noqa: BLE001
                logger.debug(
                    "drafting interpret fast-path skipped", exc_info=True,
                )

        perceived = None
        intent_source = "heuristic"
        if intent != "handoff":
            try:
                perceived = _perceive_relative_intent(
                    db, tenant_id, query=query,
                    active_task=current_active, suspended_tasks=suspended,
                    messages=messages, unified_signal=unified_signal,
                )
            except Exception:  # noqa: BLE001 — perception must never explode routing
                logger.debug("drafting intent classifier failed → keep drafting", exc_info=True)

            intent = getattr(perceived, "intent", None)
            target = _canonical(getattr(perceived, "target_task", "") or "")
            confidence = float(getattr(perceived, "confidence", 0.0) or 0.0)
            intent_source = str(getattr(perceived, "source", None) or "heuristic")

        if intent == "abandon":
            complete_task(
                db, tenant_id, conversation_id, agent="bot0",
                reason="abandon",
                task_id=(
                    current_active.get("task_id")
                    if isinstance(current_active.get("task_id"), str)
                    else None
                ),
            )
            plan = TurnPlan(agent="bot0", mode="command", task=active_task_obj,
                            reason="drafting task abandoned")
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                live_route_layer, "drafting task abandoned")
            return plan

        # Coherence (epic 1e S1/S4): respect new_task from relative classifier (or live router
        # workflow_draft_request for a substantial query). A "lets work on incident response"
        # while a stale drafting task for a different domain must NOT continue as "refine".
        # Complete the prior drafting task and open a fresh empty drafting task so the
        # turn produces a new informative draft (not "Updated draft:").
        q = (query or "").strip()
        from conversation_control_plane.workflow_intake import (
            drafting_fork_reply_in_progress as _fork_reply_in_progress,
        )

        _has_carried_draft_steps = (
            isinstance(_carried_draft, dict) and bool(_carried_draft.get("steps"))
        )
        _fresh_drafting_domain = (
            (intent == "new_task" or (workflow_draft_request and len(q) > 10))
            and not _fork_reply_in_progress(_draft_payload, q)
            and not _has_carried_draft_steps
        )
        if _fresh_drafting_domain:
            # Trust the LLM classifier's "intent" (which now has strong instructions for cost+agent+describe = bot0, not drafting).
            # We no longer use keyword catches here to decide — that would violate the NL/LLM-owned intent rule.
            complete_task(
                db, tenant_id, conversation_id, agent="bot0",
                reason="superseded",
                task_id=(
                    current_active.get("task_id")
                    if isinstance(current_active.get("task_id"), str)
                    else None
                ),
            )
            from conversation_control_plane.workflow_intake import (
                drafting_pending_ref as _drafting_pending_ref,
            )

            task = begin_task(
                db, tenant_id, conversation_id, agent="bot0", kind="drafting",
                phase="awaiting_details",
                pending_ref=_drafting_pending_ref(conversation_id),
                payload={"draft": None, "domain": q or None},
            )
            if isinstance(task, dict):
                task_obj = ActiveTask(**{k: v for k, v in task.items()
                                         if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")})
            else:
                task_obj = ActiveTask(
                    agent="bot0", phase="awaiting_details", kind="drafting",
                    payload={"draft": None, "domain": q or None},
                )
            plan = TurnPlan(agent="bot0", mode="drafting", task=task_obj,
                            reason="fresh drafting task (new_task or workflow_draft_request while prior drafting active)")
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                live_route_layer, "fresh drafting after new domain")
            return plan
        # If the LLM classified this as a cost query (not "new_task"), it will fall through to normal bot0 handling below.

        if intent == "handoff" and target == "workflow_builder" and confidence >= 0.5:
            _handoff_payload: dict[str, Any] = {}
            if isinstance(_carried_draft, dict) and _carried_draft.get("steps"):
                _handoff_payload = {
                    "draft_handoff": _carried_draft,
                    "domain": _draft_payload.get("domain"),
                }
            complete_task(
                db, tenant_id, conversation_id, agent="bot0",
                reason="superseded",
                task_id=(
                    current_active.get("task_id")
                    if isinstance(current_active.get("task_id"), str)
                    else None
                ),
            )
            # S5: unified handoff
            from conversation_control_plane.ledger import handoff as _unified_handoff
            _unified_handoff(
                db, tenant_id, conversation_id,
                target_agent="workflow_builder",
                task_text="in_progress",
                reason="drafting handoff",
            )
            plan = TurnPlan(
                agent="workflow_builder", mode="active_task",
                task=ActiveTask(
                    agent="workflow_builder", phase="active",
                    awaiting="in_progress",
                    kind=WORKFLOW_BUILD_KIND,
                    payload=_handoff_payload or None,
                ),
                reason="drafting task handed off to workflow_builder",
            )
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                live_route_layer, "drafting handoff")
            return plan

        if intent != "detour" and db is not None and tenant_id and (query or "").strip():
            try:
                from api.services.bot0_product_knowledge import (
                    retrieval_grounds_concept_query,
                )

                if retrieval_grounds_concept_query(
                    db, query, tenant_id=tenant_id, messages=messages,
                ):
                    intent = "detour"
                    confidence = max(confidence, 0.85)
                    intent_source = "retrieval_grounding"
            except Exception:  # noqa: BLE001
                logger.debug("drafting concept detour backstop skipped", exc_info=True)

        _detour_conf = float(confidence or 0.0)
        if intent == "detour" and _detour_conf >= 0.5:
            plan = TurnPlan(
                agent="bot0",
                mode="detour",
                task=active_task_obj,
                reason=f"drafting detour ({intent_source})",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "drafting detour",
            )
            return plan

        plan = TurnPlan(agent="bot0", mode="drafting", task=active_task_obj,
                        reason="drafting task owns refinement")
        _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                            live_route_layer, "drafting task active")
        return plan
    _prose_workflow_intake = workflow_draft_request or (
        unified_signal is not None
        and (getattr(unified_signal, "builder_entry", None) or "") == "content"
    )
    if _prose_workflow_intake and _active_kind != "drafting":
        try:
            from api.services.bot0_intent_router import (
                explicit_ordered_workflow_steps_supplied as _explicit_steps,
            )
            if _explicit_steps(query):
                plan = TurnPlan(
                    agent="workflow_builder",
                    mode="active_task",
                    task=ActiveTask(
                        agent="workflow_builder",
                        phase="active",
                        awaiting="in_progress",
                        kind=WORKFLOW_BUILD_KIND,
                    ),
                    reason=(
                        "Explicit ordered step list — workflow_builder owns IR "
                        "(not bot0 drafting)"
                    ),
                )
                begin_task(
                    db, tenant_id, conversation_id, agent="workflow_builder",
                    phase="active", awaiting="in_progress",
                    kind=WORKFLOW_BUILD_KIND,
                    pending_ref=f"workflow_builder:{conversation_id}",
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "explicit steps bypass drafting",
                )
                return plan
        except Exception:  # noqa: BLE001 — structural guard must never break routing
            logger.debug("explicit-steps drafting bypass skipped", exc_info=True)
        # Open a bot0-owned drafting task so the NEXT turn (the domain/details answer)
        # is owned by drafting, not stolen by an active builder. Suspend any active
        # task first (single-writer). Gated on the workflow_draft signal → inert for
        # every existing flow.
        # We trust the live_route (LLM) here. The classifier prompt explicitly says cost+agent+describe = bot0,
        # not workflow_draft. No keyword filter deciding intent.
        if current_active:
            suspend_active(db, tenant_id, conversation_id, reason="drafting_detour")
        _open_q = (query or "").strip()
        _open_domain = _open_q[:500] if len(_open_q) > 10 else None
        from conversation_control_plane.workflow_intake import (
            drafting_pending_ref as _drafting_pending_ref,
        )

        task = begin_task(
            db, tenant_id, conversation_id, agent="bot0", kind="drafting",
            phase="awaiting_details",
            pending_ref=_drafting_pending_ref(conversation_id),
            payload={
                "draft": None,
                "domain": _open_domain,
                "intake_seed": _open_q,
            },
        )
        if isinstance(task, dict):
            task_obj = ActiveTask(**{k: v for k, v in task.items()
                                     if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")})
        else:
            task_obj = ActiveTask(
                agent="bot0",
                phase="awaiting_details",
                kind="drafting",
                payload={
                    "draft": None,
                    "domain": _open_domain,
                    "intake_seed": _open_q,
                },
            )
        plan = TurnPlan(agent="bot0", mode="drafting", task=task_obj,
                        reason="open drafting task (workflow_draft signal)")
        _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                            live_route_layer, "drafting task opened")
        return plan

    # --- Step 3.9: IC4 — router ambiguity clarifier before sticky resume ---
    _clarifier_q = None
    if live_route is not None:
        _clarifier_q = getattr(live_route, "clarifier_question", None)
    if live_route_intent == "ambiguous" or _clarifier_q:
        plan = TurnPlan(
            agent="bot0",
            mode="detour",
            reason="router_ambiguity_clarifier",
        )
        _maybe_log_conflict(
            db, tenant_id, conversation_id, plan, live_route_intent,
            live_route_layer, "IC4 clarifier before sticky resume",
        )
        return plan

    # --- Step 4: active_task awaiting (simple shape match using live as proxy for "does message answer it") ---
    # If there is an active_task with an "awaiting" (e.g. awaiting name, awaiting confirmation),
    # and the user message plausibly answers it, we route to that agent and update the phase.
    # This is deterministic (no classifier). The live route is used only as a proxy in P2a
    # for the "does the message look like an answer" heuristic.
    if current_active:
        awaiting = current_active.get("awaiting")
        agent = _canonical(current_active.get("agent", ""))
        merged_ctx = {**(context or {}), **control}
        if agent == "workflow_builder":
            try:
                from conversation_control_plane.workflow_builder_post_commit import (
                    is_workflow_builder_post_commit as _is_wb_post_commit,
                    release_post_commit_builder as _release_wb_post_commit,
                )

                if _is_wb_post_commit(
                    db, tenant_id, merged_ctx, current_active,
                ):
                    _release_wb_post_commit(
                        db, tenant_id, conversation_id, merged_ctx,
                    )
                    current_active = None
            except Exception:  # noqa: BLE001 — release must never block routing
                logger.debug("post-commit builder release in decide_turn failed", exc_info=True)

    if current_active:
        awaiting = current_active.get("awaiting")
        agent = _canonical(current_active.get("agent", ""))
        active_task_obj = ActiveTask(**{k: v for k, v in current_active.items()
                                        if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")})

        # D4 — perceive what this turn wants RELATIVE to the active task. The LLM
        # owns perception; decide_turn owns the transition + the ledger write. The
        # classifier's fast-paths short-circuit the obvious cases (exact commands,
        # a fresh titled spec = the conv_2999b108 case) without an LLM call. If the
        # classifier errors, intent stays None and we fall back to the heuristic
        # below — perception must never explode routing.
        intent = None
        intent_source = "heuristic"
        perceived = None
        try:
            perceived = _perceive_relative_intent(
                db, tenant_id, query=query,
                active_task=current_active, suspended_tasks=suspended,
                messages=messages, unified_signal=unified_signal,
            )
            intent, intent_source = perceived.intent, perceived.source
        except Exception:  # noqa: BLE001 — perception must never explode routing
            logger.debug("decide_turn classifier failed → heuristic", exc_info=True)

        specialized_agents = {
            "workflow_builder",
            "workflow_editor",
            "transformation_advisor",
            "transformation_recommender",
            "catalog_role_create",
        }
        # ── S2 precedence fix (Control-Plane & Ledger Hardening §8 + §3). The misroute came from letting a
        # non-deterministic classifier/route flip a transition. The key distinction is GATE vs MID-FLIGHT:
        #   • AT A SPECIFIC GATE (awaiting a confirmation / a name / …): the user's affirmative/answer
        #     CONTINUES the task; a flaky divergent route or a flaky "handoff" must NOT override it.
        #     ("lets go ahead" on awaiting-confirmation = the misroute.)
        #   • MID-FLIGHT (awaiting == "in_progress", no specific gate): a divergent specialist route, or a
        #     handoff, is a likely NEW task / real switch (the conv_2999b108 save).
        # Precedence: new_task(explicit) > mid-flight-route-claim > abandon > handoff(named|mid-flight) >
        #             CONTINUE active (wins at a gate) > detour.
        at_specific_gate = bool(awaiting) and awaiting != "in_progress"
        divergent_specialist = (
            live_route_intent in specialized_agents and live_route_intent != agent
        )
        # A divergent route claims a NEW task only MID-FLIGHT — never at a gate (this is the misroute fix).
        # Confidence-gated (user 2026-06-24): a perceived CONTINUE always resumes (§7
        # "continue resumes, never switches" — dropped from this set), and an unclear/None
        # turn only lets a divergent specialist route CLAIM a new task when the classifier is
        # CONFIDENT (>= 0.7, raised from 0.5 — T4, turn-integrity epic: at 0.5 a flaky
        # borderline classification could still hijack an ambiguous turn and auto-suspend
        # the active task with no confirmation; THE canonical misroute family). A
        # low-confidence "Let's go" must NOT silently switch agents — it falls through to
        # the resume branch below (assume-resume). A true low-confidence "go where?"
        # clarify gate is the follow-up (CP epic §9b; needs a TurnPlan clarify surface).
        _route_conf = float(getattr(perceived, "confidence", 0.0) or 0.0)
        route_claims_new_task = (
            divergent_specialist
            and not at_specific_gate
            and intent in ("continue", "unclear", None)
            and _route_conf >= 0.7
        )

        # S3/S4 enhancement for fresh specs: a clear new domain description (e.g. "lets work on incident response")
        # while active same heavy agent should start new, not continue the old IR/awaiting.
        # The router classified it as new builder; if substantial and not short answer to current awaiting, treat as new_task.
        # This prevents "hung" in mismatched previous builder state.
        fresh_new_spec = (
            live_route_intent in ("workflow_builder", "workflow_draft")
            and agent in ("workflow_builder", "workflow_draft")
            and not at_specific_gate
            and len(q) > 10   # substantial new description, not short confirmation
            and intent in (None, "unclear", "continue", "handoff")
        )

        # 1) Explicit new task, OR (mid-flight only) a divergent route claiming one → suspend (resumable)
        # + begin the new one. The conv_2999b108 save — now gated so it can't fire at a confirmation gate.
        if intent == "new_task" or route_claims_new_task or fresh_new_spec:
            new_agent = live_route_intent or agent
            suspend_active(db, tenant_id, conversation_id, reason="new_task_while_active")
            _new_kind = ledger_kind_for_agent(new_agent)
            begin_task(db, tenant_id, conversation_id, agent=new_agent,
                       phase="active", awaiting="in_progress",
                       kind=_new_kind,
                       pending_ref=f"{new_agent}:{conversation_id}")
            reason_source = (
                f"live_route_override:{live_route_layer}" if route_claims_new_task else intent_source
            )
            plan = TurnPlan(agent=new_agent, mode="active_task",
                            task=ActiveTask(
                                agent=new_agent, phase="active", awaiting="in_progress",
                                kind=_new_kind,
                            ),
                            reason=f"D4 new_task while active ({reason_source})")
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                live_route_layer, "D4 new_task suspends active")
            return plan

        # 2) Explicit abandon — destructive sole-continue wipe.
        # Low-confidence abandon (abuse/vent/mislabeled control) must NOT complete
        # the active task (conv_4ee886cf: "you are an idiot" → D4 abandon @0.7 →
        # cost_out destroyed + drafting gibberish). Same confidence floor as T4
        # mid-flight route claims (0.7 is not enough for permanent complete).
        if intent == "abandon":
            if _route_conf < 0.85:
                # Fail soft: resume active; never open a new stream from the insult.
                plan = TurnPlan(
                    agent=agent,
                    mode="continue",
                    task=ActiveTask(
                        agent=str(current_active.get("agent") or agent),
                        phase=str(current_active.get("phase") or "active"),
                        awaiting=awaiting or "in_progress",
                        kind=str(current_active.get("kind") or "") or None,
                        payload=(
                            current_active.get("payload")
                            if isinstance(current_active.get("payload"), dict)
                            else None
                        ),
                        pending_ref=current_active.get("pending_ref"),
                    ) if isinstance(current_active, dict) else None,
                    reason=(
                        f"D4 abandon low_conf={_route_conf:.2f} "
                        f"— resume active ({intent_source})"
                    ),
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "D4 abandon low_conf fail-soft",
                )
                return plan
            # Model A: abandon is a distinct journal event (not complete).
            complete_task(
                db,
                tenant_id,
                conversation_id,
                agent=agent,
                reason="abandon",
                task_id=(
                    current_active.get("task_id")
                    if isinstance(current_active.get("task_id"), str)
                    else None
                ),
            )
            # High-conf abandon is a full wipe of sole-continue streams —
            # stamp abandon so chat clears cost pin / drafting seed and
            # never "destroy then reopen" a gibberish draft (conv_4ee886cf).
            plan = TurnPlan(
                agent="bot0",
                mode="command",
                reason=f"D4 abandon active ({intent_source})",
            )
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                live_route_layer, "D4 abandon")
            return plan

        # 3) Handoff → silent ledger transfer when a target is NAMED, or when MID-FLIGHT with
        # sufficient confidence. Agents are background infrastructure — do not interrogate the
        # user with Switch/Stay unless the destination is ambiguous (no target). At a gate with
        # no named target, a flaky "handoff" falls through to continue/resume.
        # T4: a TARGETLESS mid-flight handoff uses the live router's guess only when confident
        # (>= 0.7); below that, resume instead of guessing.
        _named_target = bool(perceived and getattr(perceived, "target_task", None))
        if intent == "handoff" and (
            _named_target or (not at_specific_gate and _route_conf >= 0.7)
        ):
            to_agent = _canonical((perceived.target_task if perceived else "") or "") or live_route_intent or agent
            from conversation_control_plane.handoff_guard import (
                append_handoff_trace,
                read_handoff_trace,
                would_ping_pong,
            )
            _trace = read_handoff_trace(context)
            if would_ping_pong(_trace, from_agent=agent, to_agent=to_agent):
                _emit(
                    db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    event="handoff_ping_pong_blocked",
                    details={"from_agent": agent, "to_agent": to_agent},
                )
                plan = TurnPlan(
                    agent="bot0",
                    mode="detour",
                    task=active_task_obj,
                    reason="hot_potato_guard: handoff ping-pong blocked",
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "hot_potato_guard",
                )
                return plan
            suspend_active(db, tenant_id, conversation_id, reason="handoff_while_active")
            _to_kind = ledger_kind_for_agent(to_agent)
            begin_task(
                db, tenant_id, conversation_id, agent=to_agent,
                phase="active", awaiting="in_progress",
                kind=_to_kind,
                pending_ref=f"{to_agent}:{conversation_id}",
            )
            append_handoff_trace(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                from_agent=agent,
                to_agent=to_agent,
                prior_trace=_trace,
            )
            plan = TurnPlan(
                agent=to_agent,
                mode="active_task",
                task=ActiveTask(
                    agent=to_agent, phase="active", awaiting="in_progress",
                    kind=_to_kind,
                ),
                reason=f"D4 handoff silent ({intent_source})",
            )
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                live_route_layer, "D4 handoff silent")
            return plan

        # 4) CONTINUE / resume the active task — the default; WINS at a gate (the misroute fix): a
        # continue / ambiguous-but-answering / targetless-handoff message resumes; it never switches.
        # Router-broke-to-bot0 is the one detour exception (an explicit "this is a Bot0 question" signal).
        route_broke_to_bot0 = live_route_intent == "bot0"
        heuristic_answers = bool(awaiting) and (len(q) > 3 or "name" in awaiting.lower())
        # A perceived CONTINUE can resume even when the router broke to bot0, but only at a
        # specific gate where the user is plausibly answering the active task. Mid-flight/no-gate
        # Bot0 routes are detours: inventory/global reads like "list workflows" must not be
        # swallowed by a stale active builder just because the relative-task classifier said
        # "continue".
        bot0_midflight_detour = route_broke_to_bot0 and not at_specific_gate
        # Finite confirm/decline at an *armed* gate (or sole-continue stream) is
        # continue-shaped for resume + session reorient — independent of router
        # label. Bare "yes" after 10h at cost_profile_save_confirm was missing
        # reorient when the router did not emit intent=continue (conv_e6b8154e).
        _finite_gate_ack = False
        if at_specific_gate or bool(awaiting):
            try:
                from conversation_control_plane.finite_confirm_grammar import (
                    is_exact_confirm_or_decline as _is_finite_ack,
                )

                _finite_gate_ack = _is_finite_ack(query)
            except Exception:  # noqa: BLE001
                _finite_gate_ack = False
            if not _finite_gate_ack and awaiting == "cost_profile_save_confirm":
                try:
                    from api.services.agent_cost_profile_save import (
                        is_cost_profile_save_confirm as _is_cost_yes,
                    )

                    _finite_gate_ack = _is_cost_yes(query or "")
                except Exception:  # noqa: BLE001
                    pass
        continues = (
            (intent == "continue" and not bot0_midflight_detour)
            or (intent in (None, "unclear", "handoff") and heuristic_answers and not route_broke_to_bot0)
            or (_finite_gate_ack and at_specific_gate and not bot0_midflight_detour)
        ) and not fresh_new_spec  # fresh new spec wins over heuristic continue for same agent
        # Session reorient: specific gates OR sole-continue mid-stream after long gap.
        # (Silent "continue" after hours is a multi-turn trust failure — all paints.)
        _kind_for_stale = str(current_active.get("kind") or "").strip()
        try:
            from conversation_control_plane.multi_turn_stream_contract import (
                is_sole_continue_kind as _is_sole_cont,
            )
            _sole_for_stale = _is_sole_cont(_kind_for_stale) or _kind_for_stale == "workflow_build"
        except Exception:  # noqa: BLE001
            _sole_for_stale = _kind_for_stale == "workflow_build"
        # Reorient also when finite ack + multi-turn even if continues stayed
        # false (router mislabel) — still before silent commit of a 10h-old gate.
        _reorient_candidate = continues or (
            _finite_gate_ack and (_sole_for_stale or at_specific_gate)
        )
        if _reorient_candidate and (at_specific_gate or _sole_for_stale):
            from conversation_control_plane.session_staleness import (
                should_reorient_before_acting as _should_reorient,
            )
            if _should_reorient(db, context=context, query=query):
                plan = TurnPlan(
                    agent="bot0",
                    mode="detour",
                    task=active_task_obj,
                    reason="session_staleness reorient",
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "session_staleness reorient",
                )
                return plan
            if (context or {}).get("session_reorientation_pending"):
                plan = TurnPlan(
                    agent="bot0",
                    mode="detour",
                    task=active_task_obj,
                    reason="session_staleness awaiting ack",
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "session_staleness awaiting ack",
                )
                return plan
        if continues:
            plan = TurnPlan(agent=agent, mode="active_task", task=active_task_obj,
                            reason=f"active_task continue for {awaiting} ({intent_source})")
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                live_route_layer, "active_task continue")
            update_phase(db, tenant_id, conversation_id, agent=agent,
                         phase=current_active.get("phase", "active"), awaiting=None)
            return plan

        # 5) Otherwise a detour while active (a side question; answer then offer resume).
        plan = TurnPlan(agent=live_route_intent, mode="detour", task=active_task_obj,
                        reason=f"detour while active_task present ({intent_source})")
        _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                            live_route_layer, "detour while active_task")
        return plan

    # --- Step 5/6/7: detour classification + resume from suspended + default ---
    # Use live_route as the classification outcome (proxy for L1/L2/L3).
    # The real implementation will call the (demoted) classifier only for genuine detours.
    # Check for resume from suspended first (step 6): if a suspended task's "awaiting"
    # plausibly matches the message, we resume it (after resolve_pending in real code).
    # When the live router broke to bot0, this turn is a Bot0 question/detour — do
    # NOT auto-resume a suspended heavy task. Resume only when the bounded LLM
    # classifier perceives continue/resume targeting the suspended agent.
    route_broke_to_bot0 = live_route_intent == "bot0"
    for s in suspended:
        s_agent = _canonical(s.get("agent", ""))
        if not s.get("awaiting") or route_broke_to_bot0:
            continue
        perceived = None
        try:
            perceived = _perceive_relative_intent(
                db, tenant_id, query=query,
                active_task=None, suspended_tasks=suspended,
                messages=messages, unified_signal=unified_signal,
            )
        except Exception:  # noqa: BLE001 — perception must never explode routing
            logger.debug("suspended resume classifier failed", exc_info=True)
        intent = getattr(perceived, "intent", None)
        target = _canonical(getattr(perceived, "target_task", "") or "")
        confidence = float(getattr(perceived, "confidence", 0.0) or 0.0)
        if not (
            intent in ("continue", "resume")
            and confidence >= 0.5
            and (not target or target == s_agent)
        ):
            continue
        # resolve_pending per contract before resume (degrades on missing/stale)
        ref = s.get("pending_ref")
        resolved = _resolve_pending_for_agent(db, tenant_id, conversation_id, s_agent, ref)
        if resolved and resolved.get("status") in ("missing", "stale"):
            _emit(db, tenant_id=tenant_id, conversation_id=conversation_id,
                  event="task_resume_failed_no_pending_ref",
                  details={"agent": s_agent, "pending_ref": ref, "status": resolved.get("status")})
            # prune this suspended entry
            kept = [t for t in suspended if t.get("pending_ref") != ref]
            # (in real, use ledger to update the list under lock)
            continue

        plan = TurnPlan(agent=s_agent, mode="resume",
                        task=ActiveTask(**{k: v for k, v in s.items()
                                           if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")}),
                        reason=f"Resume suspended task: {s_agent}")
        _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent, live_route_layer,
                            "would resume suspended task")
        # P2a: record the resume in ledger
        resume_task(db, tenant_id, conversation_id, agent=s_agent)
        return plan

    # Default to live classification result, seed ledger for heavy agents
    # This is step 7 (default bot0) or a fresh heavy start.
    mode = "fresh" if (live_route_intent or "bot0") == "bot0" else "active_task"
    target = live_route_intent or "bot0"
    plan = TurnPlan(
        agent=target,
        mode=mode,
        reason=f"Intent router → {target} ({live_route_layer})",
    )

    if live_route_intent in (
        "workflow_builder", "transformation_advisor", "transformation_recommender",
        "workflow_editor",
    ):
        begin_task(
            db, tenant_id, conversation_id, agent=live_route_intent,
            phase="active", awaiting="in_progress",
            kind=ledger_kind_for_agent(live_route_intent),
            pending_ref=f"shadow:{live_route_intent}:{conversation_id}",
        )

    _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent, live_route_layer,
                        "P2a shadow default / classification proxy")
    return plan


def _maybe_log_conflict(
    db: Any,
    tenant_id: str,
    conversation_id: str,
    plan: TurnPlan,
    live_intent: str,
    live_layer: str,
    reason: str,
) -> None:
    """Emit ledger_agent_type_conflict only when the shadow plan disagrees with live.

    NOTE: positional params — every call site in decide_turn passes positionally.
    A prior keyword-only (`*`) signature made every call raise TypeError, which
    bot0.py's try/except silently swallowed, so the shadow conflict log never
    populated. Keep this positional so the shadow evidence channel actually works."""
    if plan.agent != live_intent:
        from api.services.event_logger import log_platform_event
        log_platform_event(
            db,
            "ledger_agent_type_conflict",
            "warning",
            "Shadow decide_turn disagreed with live router",
            tenant_id=tenant_id,
            details={
                "conversation_id": conversation_id,
                "shadow_agent": plan.agent,
                "shadow_mode": plan.mode,
                "live_intent": live_intent,
                "live_layer": live_layer,
                "reason": reason,
                "shadow_reason": plan.reason,
            },
        )
        logger.info(
            "ledger_agent_type_conflict conv=%s shadow=%s live=%s reason=%s",
            conversation_id, plan.agent, live_intent, reason,
        )


def _resolve_pending_for_agent(db: Any, tenant_id: str, conversation_id: str, agent: str, pending_ref: str | None) -> dict | None:
    """Resolve pending per the ConversationalAgent contract (P4c hardening).

    For workflow_builder: loads the pending row (prefer DB) and uses classify_agent_state.
    If the state is in a terminal post-commit/cleared shape, treat as missing/stale.
    For transformation_advisor: best-effort via phase (DONE or absent => not active).
    Other agents: optimistic exists (the stub contract).
    Called before every resume decision.
    """
    if not pending_ref:
        return {"status": "missing", "summary": "no ref"}

    a = (agent or "").lower()
    if a in ("workflow_builder", "builder"):
        try:
            # Use the builder's public-ish persistence + state classify (no private mutation).
            from agent.workflow_builder.tools import _pw_load_from_db as _load_pw
            from agent.workflow_builder.state import classify_agent_state as _classify
            # _pw_load_from_db expects the pk; derive conservatively from pending_ref or conv.
            # The ref shape is "pending_workflow:<session>" or just conv; try both.
            pk = pending_ref
            if pk.startswith("pending_workflow:"):
                pk = pk.split(":", 1)[1]
            else:
                pk = f"{tenant_id}:{conversation_id}"
            pending = _load_pw(tenant_id, pk) or {}
            state = _classify(pending, [])  # messages optional for coarse check
            # Terminal / committed / cleared states mean the ref is no longer a live task.
            terminal_names = {"committed", "editing_after_commit", "reset", "done"}
            sname = getattr(state, "name", str(state)).lower() if state else ""
            if any(t in sname for t in terminal_names) or not pending.get("nodes"):
                return {"status": "missing", "summary": "builder pending cleared or committed"}
            return {"status": "exists", "summary": f"builder {sname or 'in_progress'}"}
        except Exception:  # noqa: BLE001 — resolve must never explode routing
            return {"status": "exists", "summary": "builder (resolve best-effort)"}

    if canonical_agent(a) == "transformation_advisor":
        # P2c: if we had phase in context or a session row we would check != DONE.
        # For P4c start the ledger pending_ref + active_task presence is the signal;
        # here we are optimistic unless the ref itself signals done.
        if "done" in (pending_ref or "").lower():
            return {"status": "missing", "summary": "advisor flow done"}
        return {"status": "exists", "summary": "advisor active or consulting"}

    if a == "catalog_role_create":
        from api.services.catalog_role_ledger import resolve_catalog_pending

        return resolve_catalog_pending(db, tenant_id, conversation_id, pending_ref)

    # Default (other / unknown): exists so resume can proceed; real agents will implement the method.
    return {"status": "exists", "summary": f"pending for {agent}"}
