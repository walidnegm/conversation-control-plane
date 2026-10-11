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


#: B-248: decision confidence → the float IntentResult internals compare
#: against (same mapping the retired projection used).
_DECISION_CONFIDENCE = {"high": 0.9, "medium": 0.7, "low": 0.4}


def _relative_intent_from_decision(decision: Any) -> Any:
    """The turn's decision, read relative to the open task (B-248).

    decide_turn's internals were written against an ``IntentResult``; this is
    that shape built from the ONE decision, in decision vocabulary — not a
    second classification. ``continue`` continues; ``abandon`` / ``reset``
    abandon; ``resume`` / ``handoff`` name a target; ``unknown`` is unclear.
    Every other act is read through the decision's own ledger effect
    (``decision.ledger``, set by the boundary): ``none`` — a read-only act
    that does not move the open task — is a bounded detour; ``suspend`` /
    ``begin`` is a new stream. decide_turn writes the ledger, so it executes
    the effect the boundary decided rather than re-deriving one.
    """
    from conversation_control_plane.classifier import IntentResult

    act = str(decision.act or "")
    slots = dict(decision.slots or {})
    if act == "continue":
        intent = "continue"
    elif act in ("abandon", "reset"):
        intent = "abandon"
    elif act in ("resume", "handoff"):
        intent = act
    elif act == "unknown":
        intent = "unclear"
    elif str(getattr(decision, "ledger", "") or "none") == "none":
        intent = "detour"
    else:
        intent = "new_task"
    return IntentResult(
        intent=intent,
        target_task=(slots.get("target_agent") or None) if act in ("resume", "handoff") else None,
        task_text=(slots.get("task_text") or None) if act in ("resume", "handoff") else None,
        confidence=_DECISION_CONFIDENCE.get(str(decision.confidence or ""), 0.7),
        reason=decision.reason or f"decision:{act}",
        source="decision",
    )


def _perceive_relative_intent(
    db: Any,
    tenant_id: str,
    *,
    query: str,
    active_task: Optional[dict] = None,
    suspended_tasks: Optional[list] = None,
    messages: Optional[list] = None,
) -> Any:
    """Relative task perception for decide_turn.

    B-248: when the turn has its one decision, perception IS that decision —
    no text fast path, no second classifier. Without a decision (a direct
    caller outside a chat turn) the classifier's fast path, then the bounded
    classifier, perceive it as before.
    """
    from conversation_control_plane.classifier import classify_intent, _fast_path
    from conversation_control_plane.turn_decision_contract import (
        get_turn_decision,
    )

    decision = get_turn_decision()
    if decision is not None:
        return _relative_intent_from_decision(decision)
    fp = _fast_path(query, active_task)
    if fp is not None:
        return fp
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

    B-248: what the turn IS comes from its one ``ResolvedTurnDecision``
    (``get_turn_decision()``), read here in decision vocabulary. The legacy
    ``unified_signal`` / ``live_route`` / ``workflow_draft_request`` parameters
    (a projection of that decision) are gone. With no decision (a direct
    caller outside a chat turn) every decision read below is empty and the
    ledger-only path runs as before.
    """
    def _canonical(a: str) -> str:
        return canonical_agent(a) or a  # single source (contract.canonical_agent)

    # ─── The turn's one decision (B-248) ───
    from conversation_control_plane.turn_decision_contract import (
        get_turn_decision,
    )

    _decision = get_turn_decision()
    _act = str(_decision.act or "") if _decision is not None else ""
    _slots: dict[str, Any] = dict(_decision.slots or {}) if _decision is not None else {}
    _router_evidence: dict[str, Any] = (
        dict(next((e for e in (_decision.evidence or ()) if e.get("from") == "router"), {}))
        if _decision is not None
        else {}
    )
    _continue_meaning = (
        str(_slots.get("continue_meaning") or "advance") if _act == "continue" else ""
    )
    #: The draft acts (produce a workflow / show one).
    _draft_act = _act in ("draft_work", "show_example")

    live_route_intent = _canonical(live_route_intent)
    q = (query or "").strip().lower()

    if not conversation_id:
        return TurnPlan(agent=live_route_intent or "bot0", mode="fresh",
                        reason="no conversation_id")

    control = get_control_state(db, tenant_id, conversation_id)
    current_active = control.get("active_task")

    # ─── A TASK WHOSE WORK GOT DONE ELSEWHERE DOES NOT STEER THE TURN ───
    #
    # An active_task's completion condition usually lives in ANOTHER TABLE,
    # and `complete_task` is only ever called by the flow that owns the task.
    # Satisfy the condition out of band — a card save, a canvas edit, a second
    # tab — and the task never finds out. It has no TTL either, unlike
    # pending_switch and suspended_tasks, so nothing else will ever retire it.
    #
    # conv_a7222ad3: `outcome_value_setup` sat `awaiting: in_progress` for two
    # hours and across a change of subject, asking for a revenue-per-unit that
    # had been supplied through the value-metrics card minutes earlier. It
    # still held the pre-answer copy — cost_center, 105,120 — while the
    # workflow read lead / 10,512 / $657 / revenue_center with NO outstanding
    # gap.
    #
    # THIS IS LAYER 2 OF THREE, and only a backstop. Mutation-time
    # reconciliation (layer 1) is what prevents the divergence; the sweeper
    # (layer 3) is what catches tasks nobody ever comes back to. Read-time
    # repair alone fixes conv_a7222ad3 precisely because someone returned to
    # it — an abandoned conversation would stay in_progress forever.
    #
    # Checked here because this is the single read point: reconcile once,
    # before anything downstream can act on a task that is already done.
    # Conservative by construction — a kind with no predicate, a missing
    # reference or any exception leaves the task exactly as it is.
    #
    # LIVENESS ONLY. This establishes that the obligation still exists. It
    # does NOT establish that a live task is entitled to steer THIS turn —
    # that is a separate invariant and is not decided here.
    if isinstance(current_active, dict):
        from conversation_control_plane.task_completion_predicates import (
            obligation_discharged,
        )

        _done, _why = obligation_discharged(db, tenant_id, current_active)
        if _done:
            logger.info(
                "active_task %s (%s) satisfied out of band — closing: %s",
                current_active.get("task_id"), current_active.get("kind"), _why,
            )
            try:
                complete_task(
                    db, tenant_id, conversation_id,
                    agent=current_active.get("agent") or "bot0",
                    reason="satisfied",
                    # Layer 2 runs MID-TURN and does not commit — the turn
                    # owns that, exactly as the `superseded` close below
                    # does. Committing here would commit whatever else the
                    # turn has pending.
                    trigger="read_reconciliation",
                    task_id=(
                        current_active.get("task_id")
                        if isinstance(current_active.get("task_id"), str)
                        else None
                    ),
                )
            except Exception:  # noqa: BLE001 — never break a turn on cleanup
                logger.debug("could not close satisfied task", exc_info=True)
            else:
                current_active = None
                control = get_control_state(db, tenant_id, conversation_id)

    current_pending = control.get("pending_switch") or pending_switch_from_context
    suspended = control.get("suspended_tasks") or []
    current_plan = control.get("plan")

    # Live agent cost preview — the decision's estimate_cost act, or a continue
    # whose meaning is a cost operation (not a keyword gate).
    # Multi-turn: kind=cost_out continues without clearing; otherwise open cost_out.
    if _act == "estimate_cost" or _continue_meaning in (
        "amend_estimate", "reestimate_pin", "reprice_catalog", "show_profile",
    ):
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
            reason="decision estimate_cost — opened cost_out task",
        )

    # S2 coherence epic: demote discovery to ledger task.
    # The decision's orient (its focus) / choose_path (intent_clarify) acts name
    # a front-door kind; here we open a bot0-owned discovery task instead of
    # letting an early caller short-circuit with an answer. This makes "what do
    # we have setup" a resumable task that consults the live ledger.
    from conversation_control_plane.delivery_order_contract import (
        is_front_door_detour_kind,
    )

    if _act == "orient":
        dk = str(_slots.get("focus") or "orientation").strip().lower()
    elif _act == "choose_path":
        dk = "intent_clarify"
    else:
        dk = "none"
    if dk != "none" and is_front_door_detour_kind(dk):
        # DT-name-as-greenfield: open advisor project-create owns free text
        # (e.g. project name "Kinano2") — discovery must not supersede.
        _block_discovery_create = False
        try:
            from conversation_control_plane.advisor_create_continue_contract import (
                suppress_discovery_for_advisor_create,
            )

            _block_discovery_create = suppress_discovery_for_advisor_create(
                context if isinstance(context, dict) else {},
                history=messages,
                query=query,
            )
        except Exception:  # noqa: BLE001
            _block_discovery_create = False
        if _block_discovery_create:
            # Resume create owner; do not open discovery task.
            if current_active:
                active_task_obj = ActiveTask(**{
                    k: v for k, v in current_active.items()
                    if k in (
                        "agent", "phase", "awaiting", "pending_ref", "kind", "payload",
                    )
                })
                return TurnPlan(
                    agent=_canonical(
                        current_active.get("agent") or "transformation_advisor",
                    ),
                    mode="resume",
                    task=active_task_obj,
                    reason=(
                        f"advisor project-create open — suppress discovery "
                        f"detour ({dk})"
                    ),
                )
            return TurnPlan(
                agent="transformation_advisor",
                mode="new",
                reason=(
                    f"advisor project-create open (create_graph_step) — "
                    f"suppress discovery ({dk})"
                ),
            )
        # §2c (conv_e130aef4) — a live concept thread the user is NARROWING is
        # not a detour. B-248: that verdict is the decided ``continue`` act, and
        # a decided continue never reaches this block (only orient /
        # choose_path name a front-door kind). The branch that weighed a
        # discovery label against a continuation label on one turn was a
        # second decider over two fields of one projection — deleted.
        active_task_obj = None
        if current_active:
            active_task_obj = ActiveTask(**{
                k: v for k, v in current_active.items()
                if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")
            })
        # B-258: a ``begin_task(kind="discovery")`` stood here from 07-05
        # (bbb7797ed) and never ran — it passed ``task_text``, which
        # begin_task does not accept, and a bare except swallowed the
        # TypeError. Deleted rather than repaired: the decision owns the
        # ledger effect (B-248), and for orient / choose_path that effect is
        # "none" — a read-only detour. Opening a task here would be a second
        # authority over the ledger, and every flow since was built without it.
        return TurnPlan(
            agent="bot0",
            mode="discovery" if not current_active else "detour",
            task=active_task_obj,
            reason=(
                f"discovery ({dk}) — read-only, no ledger task"
                if not current_active
                else f"discovery detour ({dk}) supersedes active task"
            ),
            discovery_kind=dk,
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

    # --- Step 2/3: confirmed_intent and pending_switch reply (server state + the decision) ---
    # These must be resolved from *server* pending_switch state (not just FE field).
    # The decision's continue meaning accept_switch / decline_switch answers
    # the pending card. A new question is not an answer to it.
    if current_pending:
        if _continue_meaning in ("accept_switch", "decline_switch"):
            plan = TurnPlan(
                agent=_canonical(current_pending.get("to_agent", live_route_intent)),
                mode="switch_confirm",
                reason="Pending agent switch awaiting confirmation",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "pending_switch reply",
            )
            return plan
        current_pending = None

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
                messages=messages,
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

        if intent != "new_task":
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
        # new_task: fall through to sticky-kind Switch/Stay (TC-D E4).

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
                messages=messages,
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

        if intent != "new_task":
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
        # new_task: fall through to sticky-kind Switch/Stay (TC-D E4).

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
                messages=messages,
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

        if intent != "new_task":
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
        # new_task: fall through to sticky-kind Switch/Stay (TC-D E4).

    # New/keep ask owns the next turn (open-leaf arming). The token "new" is
    # grammar for the parked spec, not a greenfield workflow_draft_request
    # (conv_daf74954). Continue the builder so Step A extracts the park.
    try:
        from conversation_control_plane.new_vs_previous_continue_contract import (
            NEW_VS_PREVIOUS_AWAITING as _NVP_AWAITING,
            new_vs_previous_gate_owns_turn as _nvp_owns,
        )

        if _nvp_owns(
            context=context if isinstance(context, dict) else {},
            history=messages,
            db=db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        ):
            _nvp_active = current_active if isinstance(current_active, dict) else {}
            _nvp_kind = str(_nvp_active.get("kind") or "").strip()
            if _nvp_kind == "drafting":
                complete_task(
                    db, tenant_id, conversation_id, agent="bot0",
                    reason="superseded",
                    task_id=(
                        _nvp_active.get("task_id")
                        if isinstance(_nvp_active.get("task_id"), str)
                        else None
                    ),
                )
            if _nvp_kind != WORKFLOW_BUILD_KIND:
                begin_task(
                    db, tenant_id, conversation_id,
                    agent="workflow_builder",
                    phase="active",
                    awaiting=_NVP_AWAITING,
                    kind=WORKFLOW_BUILD_KIND,
                    pending_ref=f"pending_workflow:{conversation_id}",
                )
            plan = TurnPlan(
                agent="workflow_builder",
                mode="continue",
                task=ActiveTask(
                    agent="workflow_builder",
                    phase="active",
                    awaiting=_NVP_AWAITING,
                    kind=WORKFLOW_BUILD_KIND,
                    pending_ref=f"pending_workflow:{conversation_id}",
                ),
                reason=(
                    "new_vs_previous gate armed — extract parked spec "
                    "(not greenfield drafting)"
                ),
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "new_vs_previous continue builder",
            )
            return plan
    except Exception:  # noqa: BLE001
        logger.debug("new_vs_previous continue skipped", exc_info=True)

    # --- Step 3.5: ledger-tracked DRAFTING task (CAQ-7) ---
    # A "produce a workflow for me" request (workflow_draft signal) opens a bot0-owned
    # drafting task. While it is active, the drafting task OWNS refinement turns:
    # "make MRI and CAT scan parallel" is a draft edit, not a fresh Workflow Builder
    # extraction. Only an LLM-perceived handoff to workflow_builder releases it.
    #
    # conv_7aec5ce7: false open under pin left sticky drafting; about-pin
    # continued sole-continue → builder "tell me a domain" (worse). Shared helper.
    if _active_kind == "drafting" and current_active:
        try:
            from conversation_control_plane.pin_reentry_open_contract import (
                should_collapse_hollow_sticky_drafting as _collapse_hollow_draft,
            )

            if _collapse_hollow_draft(
                active_task=current_active,
                context=context if isinstance(context, dict) else {},
                query=query,
            ):
                complete_task(
                    db,
                    tenant_id,
                    conversation_id,
                    agent=str(current_active.get("agent") or "bot0"),
                    reason="superseded",
                    task_id=(
                        current_active.get("task_id")
                        if isinstance(current_active.get("task_id"), str)
                        else None
                    ),
                )
                logger.info(
                    "collapsed hollow sticky drafting under pin "
                    "(class post_complete_pin_greenfield_drafting) conv=%s",
                    conversation_id,
                )
                current_active = None
                _active_kind = ""
        except Exception:  # noqa: BLE001
            logger.debug("sticky drafting pin collapse skipped", exc_info=True)

    if _active_kind == "drafting":
        active_task_obj = ActiveTask(**{k: v for k, v in current_active.items()
                                        if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")})
        _draft_payload = (current_active or {}).get("payload") or {}
        _carried_draft = _draft_payload.get("draft")
        intent: str | None = None
        target = ""
        confidence = 0.0
        intent_source = "heuristic"
        _force_drafting_refine = False
        # conv_db94316d / conv_8eaa39b3: content-strength "Draft with assumptions"
        # (or armed prefer_chat_first_sketch) is chat invent sole-continue — never
        # relative-intent handoff → hollow workflow_builder with chip as paste,
        # never fresh-domain supersede that parks the chip as domain.
        try:
            from conversation_control_plane.draft_content_strength_contract import (
                content_strength_advance_owns_turn as _strength_owns,
            )

            if _strength_owns(query, payload=_draft_payload if isinstance(_draft_payload, dict) else None):
                _force_drafting_refine = True
                intent = "continue"
                target = ""
                confidence = 1.0
                intent_source = "content_strength_advance_sole_continue"
        except Exception:  # noqa: BLE001
            logger.debug("content strength advance sole-continue skip", exc_info=True)
        if isinstance(_carried_draft, dict) and _carried_draft.get("steps"):
            try:
                from conversation_control_plane.prose_intake_contract import (
                    resolve_carried_draft_turn_kind,
                )

                _draft_turn, _aff_conf = resolve_carried_draft_turn_kind(
                    db,
                    tenant_id,
                    query=query,
                    messages=messages,
                    active_task=current_active,
                    payload=_draft_payload,
                )
                if _draft_turn in ("interpret", "build") and _aff_conf >= 0.5:
                    intent = "handoff"
                    target = "workflow_builder"
                    confidence = _aff_conf
                elif _draft_turn in (
                    "refine",
                    "apply_structural",
                    "recommend_prioritize",
                    "how_to_implement",
                ) and _aff_conf >= 0.5:
                    # Stay on drafting (improvement cognition + free-text refine)
                    intent = "continue"
                    confidence = _aff_conf
                    intent_source = f"drafting_{_draft_turn}"
                    _force_drafting_refine = True
            except Exception:  # noqa: BLE001
                logger.debug(
                    "drafting interpret fast-path skipped", exc_info=True,
                )

        # B-248: this override re-classified the turn (improvement act,
        # strengtheners, interpret-command text) and forced continue/refine
        # over cognition. When the turn has its one decision, continue vs
        # anything else was ruled at the boundary; this runs only without one.
        if _decision is None:
            # Improvement cognition / deictic apply must not hand off even if
            # relative-intent later labels handoff/new_task by mistake.
            try:
                from conversation_control_plane.draft_improvement_cognition import (
                    resolve_draft_improvement_action as _improve_dec,
                )
                from conversation_control_plane.draft_strengtheners_contract import (
                    is_apply_structural_strengtheners_request as _apply_str_dec,
                )

                _pl_dec = _draft_payload if isinstance(_draft_payload, dict) else None
                _act_dec = _improve_dec(
                    db,
                    tenant_id,
                    query=query,
                    messages=messages,
                    active_task=current_active,
                    payload=_pl_dec,
                    # Prefer prior resolve_carried path; still allow deictic + free
                    # refine protect if that path labeled handoff incorrectly.
                    skip_llm=True,
                )
                # B-248: the glossary-detour / named-new-process guards read
                # labels only a decided turn carries; this branch runs only
                # without a decision, so they could never be true — deleted
                # (conv_4ac10b7c's law holds at the boundary, which decides
                # draft_work vs continue).
                if (
                    _act_dec.applies_structural_brief
                    or _act_dec.turn_kind in (
                        "recommend_prioritize",
                        "how_to_implement",
                        "apply_structural",
                        "refine",
                        "invite_refine",
                    )
                    or _apply_str_dec(query, payload=_pl_dec)
                ):
                    _force_drafting_refine = True
                    intent = "continue"
                    target = ""
                    intent_source = (
                        f"improvement_{_act_dec.label}"
                        if _act_dec.confidence >= 0.5
                        else "apply_structural_strengtheners"
                    )
                    confidence = max(float(confidence or 0.0), 0.9)
                # draft_improve_to_ir: open NL labeled handoff without finite interpret
                if intent == "handoff" and not _force_drafting_refine:
                    try:
                        from agent.workflow_builder.input_shape import (
                            looks_like_interpret_command_request as _fin_i,
                        )
                        from conversation_control_plane.classifier import (
                            drafting_interpret_gate_reply as _fin_g,
                        )

                        if not (_fin_g(query) or _fin_i(query)):
                            _force_drafting_refine = True
                            intent = "continue"
                            target = ""
                            intent_source = "draft_improve_to_ir_seal"
                            confidence = max(float(confidence or 0.0), 0.9)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass

        perceived = None
        # Do not let relative-intent steal apply-strengtheners / forced refine
        # into handoff (conv_735f617a).
        if intent != "handoff" and not _force_drafting_refine:
            try:
                perceived = _perceive_relative_intent(
                    db, tenant_id, query=query,
                    active_task=current_active, suspended_tasks=suspended,
                    messages=messages,
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

        # Coherence (epic 1e S1/S4): respect new_task from the decision (or a
        # draft act for a substantial query). A "lets work on incident response"
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
        _process_seed = False
        try:
            from conversation_control_plane.draft_content_strength_contract import (
                live_query_is_process_seed as _fresh_proc_seed,
            )

            _process_seed = bool(_fresh_proc_seed(q))
        except Exception:  # noqa: BLE001
            _process_seed = False
        _fresh_drafting_domain = (
            (intent == "new_task" or (_draft_act and len(q) > 10))
            and not _fork_reply_in_progress(_draft_payload, q)
            and not _has_carried_draft_steps
            # Clarity advance / invent chip is not a new process domain.
            and not _force_drafting_refine
            # A process body is extract, not an empty drafting fork.
            and not _process_seed
        )
        # Never park finite control chips as domain authority.
        try:
            from conversation_control_plane.draft_content_strength_contract import (
                is_draft_control_chip_token as _is_ctrl_chip,
            )

            if _is_ctrl_chip(q):
                _fresh_drafting_domain = False
        except Exception:  # noqa: BLE001
            pass
        if _fresh_drafting_domain:
            # Pin re-entry open seal: do not supersede into greenfield drafting
            # when a workflow identity pin is present unless cognition marks
            # new_process (see pin_reentry_open_contract).
            from conversation_control_plane.pin_reentry_open_contract import (
                may_begin_greenfield_drafting as _may_draft,
            )

            if not _may_draft(context=context, query=q):
                # Stay on current drafting refinement path (do not fork greenfield)
                pass
            else:
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

                # Domain is model-owned (intake assessor) — never free-text query
                # as Domain: authority (chip "draft with assumptions" burned here).
                _fresh_payload: dict[str, Any] = {"draft": None, "domain": None}
                task = begin_task(
                    db, tenant_id, conversation_id, agent="bot0", kind="drafting",
                    phase="awaiting_details",
                    pending_ref=_drafting_pending_ref(conversation_id),
                    payload=_fresh_payload,
                )
                if isinstance(task, dict):
                    task_obj = ActiveTask(**{k: v for k, v in task.items()
                                             if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")})
                else:
                    task_obj = ActiveTask(
                        agent="bot0", phase="awaiting_details", kind="drafting",
                        payload=dict(_fresh_payload),
                    )
                plan = TurnPlan(agent="bot0", mode="drafting", task=task_obj,
                                reason="fresh drafting task (new_task or draft act while prior drafting active)")
                _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                    live_route_layer, "fresh drafting after new domain")
                return plan
        # If the LLM classified this as a cost query (not "new_task"), it will fall through to normal bot0 handling below.

        if (
            intent == "handoff"
            and target == "workflow_builder"
            and confidence >= 0.5
            and not _force_drafting_refine
        ):
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

        # Finite product actions on an open drafting task: interpret / save must
        # NEVER become "drafting detour (retrieval_grounding)" (staging
        # conv_dc75f5f4 / conv_119bdab7 — bare "Interpret" re-drafted forever).
        # B-248: with a decision, interpret/save is its continue meaning
        # (drafting_turn_kind, handled above) — not a re-read of the text.
        _interpret_or_save = False
        try:
            from agent.workflow_builder.input_shape import (
                looks_like_draft_finalize_command_request as _looks_finalize,
                looks_like_interpret_command_request as _looks_interpret,
            )
            from conversation_control_plane.turn_decision_contract import (
                get_turn_decision as _get_decision_ig,
            )

            if _get_decision_ig() is None:
                _q_gate = (query or "").strip()
                _interpret_or_save = bool(
                    _looks_interpret(_q_gate) or _looks_finalize(_q_gate)
                )
        except Exception:  # noqa: BLE001
            _interpret_or_save = False

        if _interpret_or_save and intent != "handoff":
            # Re-try handoff when steps exist; otherwise stay on drafting so
            # bot0 early interpret can thin-refuse or hand off — not detour.
            if isinstance(_carried_draft, dict) and _carried_draft.get("steps"):
                intent = "handoff"
                target = "workflow_builder"
                confidence = max(float(confidence or 0.0), 0.9)
                intent_source = "drafting_interpret_finite_grammar"
            else:
                plan = TurnPlan(
                    agent="bot0",
                    mode="drafting",
                    task=active_task_obj,
                    reason="drafting interpret/save gate (no detour; material check in bot0)",
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "drafting interpret gate",
                )
                return plan

        # Re-enter handoff after finite-grammar upgrade.
        if intent == "handoff" and target == "workflow_builder" and confidence >= 0.5:
            _handoff_payload2: dict[str, Any] = {}
            if isinstance(_carried_draft, dict) and _carried_draft.get("steps"):
                _handoff_payload2 = {
                    "draft_handoff": _carried_draft,
                    "domain": _draft_payload.get("domain"),
                }
            if _handoff_payload2:
                complete_task(
                    db, tenant_id, conversation_id, agent="bot0",
                    reason="superseded",
                    task_id=(
                        current_active.get("task_id")
                        if isinstance(current_active.get("task_id"), str)
                        else None
                    ),
                )
                from conversation_control_plane.ledger import (
                    handoff as _unified_handoff2,
                )

                _unified_handoff2(
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
                        payload=_handoff_payload2 or None,
                    ),
                    reason="drafting task handed off to workflow_builder",
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "drafting handoff",
                )
                return plan

        # Risk catalog browse mid-drafting — yield exclusive draft owner (detour).
        try:
            from conversation_control_plane.risk_catalog_turn import (
                looks_like_risk_catalog_open_request as _risk_open,
            )
            from conversation_control_plane.turn_decision_contract import (
                get_turn_decision as _get_decision_rk,
            )

            # B-248: with a decision, browsing the risk registry is the explain
            # act (product_knowledge) — not a text reading inside decide_turn.
            if _get_decision_rk() is None and _risk_open(query):
                plan = TurnPlan(
                    agent="bot0",
                    mode="detour",
                    task=active_task_obj,
                    reason="drafting detour (risk_catalog_open)",
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "drafting risk catalog detour",
                )
                return plan
        except Exception:  # noqa: BLE001
            logger.debug("drafting risk-open detour skipped", exc_info=True)

        # **Cognition decides this is a concept question; retrieval never did.**
        #
        # A retrieval backstop used to turn a labelled concept question into a
        # "drafting detour (retrieval_grounding)" when relative intent had not
        # already said detour. Retrieval grounds essentially anything — measured
        # 2026-08-11, ``grounded=True`` for "who am i" (1.0), a real glossary
        # ask (4.75) and a 5.6k workflow description (11.5) — so it was gated
        # on cognition's concept label (conv_73cdd4b6: a 5,655-char clinical
        # process pasted at ``awaiting: intake`` became a glossary detour).
        #
        # B-248: the decided ``explain`` act IS that label, and it is read-only,
        # so its ledger effect is ``none`` and relative intent is already
        # ``detour`` above. The backstop could only fire when the decision had
        # NOT said detour — i.e. it re-read a turn the boundary decided. Second
        # decider; deleted. Prose intake (not an explain act) stays intake.

        # conv_4ac10b7c: a process body on an open drafting task is the
        # work, not a glossary detour and not an 80-tool prose draft.
        # Hand off to the builder so extract runs.
        # Salvage is for UNNAMED turns (cognition missed the flag). A named
        # act the open kind does not own is a detour — G5 I8, conv_0f96d344.
        if not _force_drafting_refine:
            try:
                from conversation_control_plane.draft_content_strength_contract import (
                    live_query_is_process_seed as _proc_body_draft,
                )
                from conversation_control_plane.pre_decide_owner_contract import (
                    named_acts_are_foreign_to_task_kind as _named_foreign_draft,
                )

                if _named_foreign_draft(
                    str(current_active.get("kind") or "drafting"),
                ):
                    pass
                elif _proc_body_draft(query or ""):
                    complete_task(
                        db, tenant_id, conversation_id, agent="bot0",
                        reason="superseded",
                        task_id=(
                            current_active.get("task_id")
                            if isinstance(current_active.get("task_id"), str)
                            else None
                        ),
                    )
                    from conversation_control_plane.ledger import (
                        handoff as _proc_handoff,
                    )

                    _proc_handoff(
                        db, tenant_id, conversation_id,
                        target_agent="workflow_builder",
                        task_text="in_progress",
                        reason="process body on drafting",
                    )
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
                            "process body on drafting — builder owns extract "
                            f"({intent_source})"
                        ),
                    )
                    _maybe_log_conflict(
                        db, tenant_id, conversation_id, plan,
                        live_route_intent, live_route_layer,
                        "process body drafting handoff",
                    )
                    return plan
            except Exception:  # noqa: BLE001
                logger.debug(
                    "process-body drafting handoff skipped", exc_info=True,
                )

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
    # The draft acts (draft_work / show_example) are the prose-intake signal.
    _prose_workflow_intake = _draft_act
    # Fast path may serve drafting; it may not substitute for D4 when another
    # sole-continue kind is sticky (epic §7.2 · conv_92def296). Cognition
    # already labeled continue / detour / new_task; D4 owns the transition.
    _yield_prose_to_d4 = False
    if (
        _prose_workflow_intake
        and isinstance(current_active, dict)
        and _active_kind not in ("drafting", WORKFLOW_BUILD_KIND, "", None)
    ):
        try:
            from conversation_control_plane.task_pin_contract import (
                SOLE_CONTINUE_KINDS as _SCK_YIELD,
            )

            _yield_prose_to_d4 = str(_active_kind or "") in _SCK_YIELD
        except Exception:  # noqa: BLE001
            _yield_prose_to_d4 = bool(_active_kind)
        if _yield_prose_to_d4:
            logger.info(
                "prose intake yields to D4 sticky_kind=%s conv=%s",
                _active_kind, conversation_id,
            )
    if (
        _prose_workflow_intake
        and _active_kind != "drafting"
        and _active_kind != WORKFLOW_BUILD_KIND
        and not _yield_prose_to_d4
    ):
        try:
            from api.services.bot0_intent_router import (
                explicit_ordered_workflow_steps_supplied as _explicit_steps,
            )
            if _explicit_steps(query):
                # Pack spine seal (conv_e343fb86): do not steal dual initiative
                # into cold builder when cognition asked for pack or pack bag
                # still has open hops. Pack open stays cognition-only; code
                # only refuses builder steal (pack_structure_spine_contract).
                _pack_ok_builder = True
                try:
                    from conversation_control_plane.pack_structure_spine_contract import (
                        may_begin_greenfield_builder_for_explicit_steps as _may_ep_builder,
                    )

                    # B-248: one act per turn — a draft act is never also
                    # an engagement_pack request.
                    _pack_ok_builder, _pack_block = _may_ep_builder(
                        context=context if isinstance(context, dict) else None,
                        engagement_pack_request=False,
                    )
                except Exception:  # noqa: BLE001
                    _pack_ok_builder, _pack_block = True, "probe_failed"
                if _pack_ok_builder:
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
                logger.info(
                    "explicit-steps builder open blocked for pack spine "
                    "reason=%s conv=%s",
                    _pack_block,
                    conversation_id,
                )
        except Exception:  # noqa: BLE001 — structural guard must never break routing
            logger.debug("explicit-steps drafting bypass skipped", exc_info=True)

        # Purity open seal: pin-resume forbids greenfield drafting unless
        # cognition marks new_process (pin_reentry_open_contract).
        from conversation_control_plane.pin_reentry_open_contract import (
            drafting_open_blocked_reason as _draft_block_reason,
            may_begin_greenfield_drafting as _may_open_draft,
        )

        if not _may_open_draft(context=context, query=query):
            _why = _draft_block_reason(context=context, query=query)
            logger.info(
                "decide_turn refused greenfield drafting open: %s",
                _why or "pin_reentry",
            )
            # Fall through — pin-bound leaves / default bot0 with pin brief
        else:
            # Open a bot0-owned drafting task so the NEXT turn (the domain/details
            # answer) is owned by drafting. Cognition open signal only — no laundry.
            if current_active:
                suspend_active(db, tenant_id, conversation_id, reason="drafting_detour")
            _open_q = (query or "").strip()
            _open_seed_kind = "none"
            _open_domain = _open_q[:500] if len(_open_q) > 10 else None
            try:
                from conversation_control_plane.intake_assessment_contract import (
                    normalize_process_topic_at_boundary as _normalize_open_topic,
                )
                from conversation_control_plane.workflow_seed_kind_contract import (
                    safe_workflow_seed_kind as _safe_seed_kind,
                    workflow_seed_kind_can_name_process as _seed_kind_can_name,
                )

                _open_seed_kind = _safe_seed_kind(
                    _router_evidence.get("seed_kind", "none")
                    if _act == "draft_work"
                    else "none",
                )
                if _open_seed_kind != "none" and not _seed_kind_can_name(
                    _open_seed_kind,
                ):
                    _open_domain = None
                elif _open_seed_kind != "none":
                    # A draft act carries no task_text (only handoff does):
                    # the topic candidate is the message itself.
                    _candidate_topic = _open_q
                    _open_domain = (
                        _normalize_open_topic(
                            _candidate_topic,
                            source_query=_open_q,
                            workflow_seed_kind=_open_seed_kind,
                        )
                        or None
                    )
            except Exception:  # noqa: BLE001
                _open_seed_kind = "none"
            from conversation_control_plane.workflow_intake import (
                drafting_pending_ref as _drafting_pending_ref,
            )
            _open_payload = {
                "draft": None,
                "domain": _open_domain,
                "intake_seed": _open_q,
            }
            if _open_seed_kind != "none":
                _open_payload["workflow_seed_kind"] = _open_seed_kind
                _open_payload["intake"] = {
                    "workflow_seed_kind": _open_seed_kind,
                }

            task = begin_task(
                db, tenant_id, conversation_id, agent="bot0", kind="drafting",
                phase="awaiting_details",
                pending_ref=_drafting_pending_ref(conversation_id),
                payload=_open_payload,
            )
            if isinstance(task, dict):
                task_obj = ActiveTask(**{k: v for k, v in task.items()
                                         if k in ("agent", "phase", "awaiting", "pending_ref", "kind", "payload")})
            else:
                task_obj = ActiveTask(
                    agent="bot0",
                    phase="awaiting_details",
                    kind="drafting",
                    payload=_open_payload,
                )
            plan = TurnPlan(agent="bot0", mode="drafting", task=task_obj,
                            reason="open drafting task (workflow_draft signal)")
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                live_route_layer, "drafting task opened")
            return plan

    # --- Step 3.9 (IC4) retired, B-248: the router-ambiguity clarifier keyed
    # on ``live_route_intent == "ambiguous"``, which no producer sends now —
    # chat passes the decided act's agent. Ambiguity is the boundary's
    # ``choose_path`` act, decided once.

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

    # S3: simulate/optimize on a pinned workflow is Rec 2.0 / sim-entry.
    # After confirmed_switch and post-commit release, before sticky continue.
    # Cognition ``simulate_workflow`` beats leftover builder (conv_b899a066 B).
    try:
        from conversation_control_plane.recommender_task_contract import (
            simulate_on_pinned_workflow as _s3_sim_pin,
        )

        _s3_wf = _s3_sim_pin(
            context=context if isinstance(context, dict) else {},
            live_route_intent=live_route_intent,
            live_route_layer=live_route_layer,
        )
    except Exception:  # noqa: BLE001
        _s3_wf = ""
        logger.debug("S3 simulate-on-pin probe skipped", exc_info=True)
    if _s3_wf:
        return TurnPlan(
            agent="bot0",
            mode="continue",
            reason=(
                f"simulate/optimize on {_s3_wf} → rec2/sim_entry "
                "(not advisor handoff)"
            ),
        )

    if current_active:
        # A task with a phase and no awaiting cannot be continued into — the
        # branch below reads `awaiting` and, finding none, hands the turn to
        # prose. Recover it from the last card the user was actually shown
        # before that read happens (conv_40db3389: the domain picker, one
        # message behind the hollow turn that buried it). Only reaches rows
        # stranded before `arm_fat_leaf_awaiting` existed; a healthy task
        # fails the guard and nothing is written.
        try:
            from conversation_control_plane.claimed_turn_complete_contract import (
                heal_stranded_awaiting as _heal_awaiting,
            )

            _healed = _heal_awaiting(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                active_task=current_active,
            )
            if _healed:
                current_active = {**current_active, "awaiting": _healed}
                logger.info(
                    "STRANDED_AWAITING_HEALED conv=%s awaiting=%s — recovered "
                    "from the last card shown; the turn can continue.",
                    conversation_id, _healed,
                )
        except Exception:  # noqa: BLE001 — a repair never blocks routing
            logger.debug("stranded awaiting heal skipped", exc_info=True)

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
                messages=messages,
            )
            intent, intent_source = perceived.intent, perceived.source
        except Exception:  # noqa: BLE001 — perception must never explode routing
            logger.debug("decide_turn classifier failed → heuristic", exc_info=True)

        # Stream change under sticky sole-continue: cognition named new_task /
        # handoff (or a different-stream act). Code owns Switch/Stay — do not
        # silent begin_task. Bounded detour stays Grade A (conv_92def296).
        try:
            from conversation_control_plane.ledger_conflict_adjudication_contract import (
                Verdict as _KindVerdict,
                adjudicate_sticky_kind_change as _adj_kind,
                departure_target_agent as _dep_agent,
            )

            # B-248: both read the turn's decision themselves; no signal (or
            # a SimpleNamespace stand-in for one) is threaded through.
            _kadj = _adj_kind(current_active)
            _cur_agent = _canonical(current_active.get("agent") or "bot0")
            _to = _dep_agent(current_active)
            # ASK without a named destination is not a builder switch.
            # Defaulting empty `_dep_agent` to workflow_builder turned a
            # glossary detour into "You're still deciding whether to switch
            # to Workflow Builder" (conv_996b4ec0). conv_debaea7b was the
            # self-switch cousin of the same default.
            if (
                _kadj.verdict is _KindVerdict.ASK
                and _to
                and _canonical(_to) != _cur_agent
            ):
                propose_switch(
                    db, tenant_id, conversation_id,
                    from_agent=_cur_agent,
                    to_agent=_canonical(_to),
                    original_message=query or "",
                )
                plan = TurnPlan(
                    agent=_cur_agent,
                    mode="switch_confirm",
                    task=active_task_obj,
                    reason=_kadj.reason,
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "sticky kind Switch/Stay",
                )
                return plan
            # conv_4ac10b7c: glossary + named draft leave is not Switch/Stay
            # and not D4-to-bot0. Complete the concept thread and open the
            # named owner once. Destination comes from departure_target_agent
            # (already computed as _to) — do not invent a default agent.
            if (
                _kadj.verdict is _KindVerdict.COGNITION_WINS
                and str(current_active.get("kind") or "") == "concept_thread"
                and _to
                and _canonical(_to) != _cur_agent
            ):
                try:
                    from conversation_control_plane.concept_thread_pin_contract import (
                        concept_thread_leaves_for_draft as _ct_leave,
                    )

                    if _ct_leave():
                        complete_task(
                            db, tenant_id, conversation_id, agent="bot0",
                            reason="superseded",
                            task_id=(
                                current_active.get("task_id")
                                if isinstance(current_active.get("task_id"), str)
                                else None
                            ),
                        )
                        _dest = _canonical(_to)
                        _dest_kind = ledger_kind_for_agent(_dest)
                        begin_task(
                            db, tenant_id, conversation_id, agent=_dest,
                            phase="active", awaiting="in_progress",
                            kind=_dest_kind,
                            pending_ref=f"{_dest}:{conversation_id}",
                        )
                        plan = TurnPlan(
                            agent=_dest,
                            mode="active_task",
                            task=ActiveTask(
                                agent=_dest,
                                phase="active",
                                awaiting="in_progress",
                                kind=_dest_kind,
                            ),
                            reason=(
                                "leave concept_thread for named draft "
                                f"({intent_source})"
                            ),
                        )
                        _maybe_log_conflict(
                            db, tenant_id, conversation_id, plan,
                            live_route_intent, live_route_layer,
                            "concept_thread leave named draft",
                        )
                        return plan
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "concept_thread named-draft leave skipped",
                        exc_info=True,
                    )
        except Exception:  # noqa: BLE001
            logger.debug("sticky kind change adjudication skipped", exc_info=True)

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
            # B-240: a perceived CONTINUE resumes (§7 above) — a length check
            # may not turn cognition's "continue" into a new task.
            and intent in (None, "unclear", "handoff")
        )

        # 1) Explicit new task, OR (mid-flight only) a divergent route claiming one → suspend (resumable)
        # + begin the new one. The conv_2999b108 save — now gated so it can't fire at a confirmation gate.
        # B-240: a message cannot displace the task it opened. The worker
        # re-decides the message the main process already admitted; reading
        # its own task as "previous work" suspended and re-began the builder
        # inside one turn (conv_b4bc0ea1 replay, conv_10152a62 seq 3→5→6).
        from conversation_control_plane.admission_contract import (
            opened_by_this_message as _opened_by_this_message,
        )

        if _opened_by_this_message(current_active) and (
            intent == "new_task" or route_claims_new_task or fresh_new_spec
        ):
            plan = TurnPlan(
                agent=agent, mode="active_task", task=active_task_obj,
                reason=f"task opened by this message continues ({intent_source})",
            )
            _maybe_log_conflict(
                db, tenant_id, conversation_id, plan, live_route_intent,
                live_route_layer, "same message: own task is not displaced",
            )
            return plan
        if intent == "new_task" or route_claims_new_task or fresh_new_spec:
            # conv_4ac10b7c: a named draft act on an already-open drafting /
            # workflow_build owner is that task's work, not D4 suspend.
            try:
                from conversation_control_plane.pre_decide_owner_contract import (
                    named_acts_continue_task_kind as _named_own_d4,
                )

                if _named_own_d4(str(current_active.get("kind") or "")):
                    plan = TurnPlan(
                        agent=agent, mode="active_task", task=active_task_obj,
                        reason=(
                            "D4 named act is the open owner's work "
                            f"({intent_source})"
                        ),
                    )
                    _maybe_log_conflict(
                        db, tenant_id, conversation_id, plan,
                        live_route_intent, live_route_layer,
                        "D4 named-act keep owner",
                    )
                    return plan
            except Exception:  # noqa: BLE001
                logger.debug("D4 named-act keep skipped", exc_info=True)
            try:
                from conversation_control_plane.domain_create_intake_contract import (
                    create_act_keeps_workflow_build as _dom_create_keep,
                )

                if _dom_create_keep(q) and str(
                    current_active.get("kind") or ""
                ) in ("workflow_build", "drafting"):
                    plan = TurnPlan(
                        agent=agent, mode="active_task", task=active_task_obj,
                        reason=(
                            "D4 domain-create act is the open owner's work "
                            f"({intent_source})"
                        ),
                    )
                    _maybe_log_conflict(
                        db, tenant_id, conversation_id, plan,
                        live_route_intent, live_route_layer,
                        "D4 domain-create keep owner",
                    )
                    return plan
            except Exception:  # noqa: BLE001
                logger.debug("D4 domain-create keep skipped", exc_info=True)
            # Parked new/keep ask owns "new" — it is not D4 new_task
            # (conv_daf74954). Same shape as advisor project-create suppress.
            try:
                from conversation_control_plane.new_vs_previous_continue_contract import (
                    NEW_VS_PREVIOUS_AWAITING as _NVP_AWAITING_D4,
                    new_vs_previous_gate_owns_turn as _nvp_owns_d4,
                )

                if _nvp_owns_d4(
                    context=context if isinstance(context, dict) else {},
                    history=messages,
                    db=db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                ):
                    plan = TurnPlan(
                        agent="workflow_builder",
                        mode="continue",
                        task=ActiveTask(
                            agent="workflow_builder",
                            phase=str(current_active.get("phase") or "active")
                            if isinstance(current_active, dict)
                            else "active",
                            awaiting=_NVP_AWAITING_D4,
                            kind=WORKFLOW_BUILD_KIND,
                            pending_ref=(
                                current_active.get("pending_ref")
                                if isinstance(current_active, dict)
                                else None
                            ) or f"pending_workflow:{conversation_id}",
                        ),
                        reason=(
                            "new_vs_previous gate armed — suppress new_task "
                            f"steal ({intent_source})"
                        ),
                    )
                    _maybe_log_conflict(
                        db, tenant_id, conversation_id, plan, live_route_intent,
                        live_route_layer, "D4 new_task suppressed new_vs_previous",
                    )
                    return plan
            except Exception:  # noqa: BLE001
                logger.debug(
                    "new_vs_previous D4 suppress skipped",
                    exc_info=True,
                )
            # Open project-create owns free text (re-paste team sizing after name-ask
            # error must not D4-suspend into bot0 ceremony — conv_648143cd).
            # Same table as D4 abandon suppress + discovery suppress.
            try:
                from conversation_control_plane.advisor_create_continue_contract import (
                    advisor_project_create_open as _create_open_new,
                )

                _ctx_nt = context if isinstance(context, dict) else {}
                if _create_open_new(_ctx_nt, history=messages):
                    plan = TurnPlan(
                        agent=_canonical(
                            current_active.get("agent")
                            or "transformation_advisor",
                        ),
                        mode="continue",
                        task=ActiveTask(
                            agent=_canonical(
                                current_active.get("agent")
                                or "transformation_advisor",
                            ),
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
                            "advisor project-create open — suppress new_task "
                            f"steal ({intent_source})"
                        ),
                    )
                    _maybe_log_conflict(
                        db, tenant_id, conversation_id, plan, live_route_intent,
                        live_route_layer, "D4 new_task suppressed create open",
                    )
                    return plan
            except Exception:  # noqa: BLE001
                logger.debug(
                    "advisor create open new_task suppress skipped",
                    exc_info=True,
                )
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
            # Open advisor project-create owns free text (name / roles / FTE).
            # Soft abandon labels must not wipe create mid-flight — same class as
            # DT-name-as-greenfield (conv_665da16b). Exact reset still wins earlier
            # via is_exact_reset_command / bot0 _is_reset_cmd.
            try:
                from conversation_control_plane.advisor_create_continue_contract import (
                    advisor_project_create_open as _create_open_abandon,
                )

                # State only: open create leaf owns free text (name/roles/desc).
                # No skip-phrase laundry — cognition + create tool handle "skip".
                _ctx_ab = context if isinstance(context, dict) else {}
                if _create_open_abandon(_ctx_ab, history=messages):
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
                            f"D4 abandon suppressed — advisor project-create open "
                            f"({intent_source})"
                        ),
                    )
                    _maybe_log_conflict(
                        db, tenant_id, conversation_id, plan, live_route_intent,
                        live_route_layer, "D4 abandon suppressed create open",
                    )
                    return plan
            except Exception:  # noqa: BLE001
                logger.debug(
                    "advisor create open abandon suppress skipped",
                    exc_info=True,
                )
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
        # B-248: a decided ``continue`` IS the decision to stay on the open task;
        # the route label for a bot0-owned continue (concept_thread, drafting…)
        # is just that task's owner, not a break to bot0.
        route_broke_to_bot0 = live_route_intent == "bot0" and _act != "continue"
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
        # C26 S1c — open task is not evidence this turn continues it
        # (conv_c00f6ff). Foreign editor route or a wf_ token at a staffing/IR
        # gate demotes continue. Finite yes/no still continues.
        if continues:
            try:
                from conversation_control_plane.active_task_continue_contract import (
                    continue_permitted as _continue_ok,
                )

                if not _continue_ok(
                    active_agent=agent,
                    live_route_intent=live_route_intent,
                    awaiting=awaiting,
                    query=query,
                    finite_gate_ack=_finite_gate_ack,
                    classifier_continue=(intent == "continue"),
                ):
                    continues = False
            except Exception:  # noqa: BLE001
                pass
        # Create leaf open (or finite post-create match/save): never detour to
        # bot0 freestyle ceremony (conv_6ca62a5c / conv_648143cd re-paste).
        if not continues and agent in (
            "transformation_advisor", "advisor", "bot0",
        ):
            try:
                from conversation_control_plane.advisor_create_continue_contract import (
                    advisor_project_create_open as _create_open_cont,
                    should_force_create_flow_for_post_create_continue as _force_pc,
                )

                _hist = None
                if messages:
                    _hist = [
                        (m.get("role"), m.get("content"))
                        if isinstance(m, dict)
                        else m
                        for m in messages
                    ]
                _ctx_c = context if isinstance(context, dict) else {}
                if _create_open_cont(_ctx_c, history=_hist) or _force_pc(
                    _ctx_c, query, history=_hist,
                ):
                    continues = True
                    if agent in ("bot0", ""):
                        agent = "transformation_advisor"
            except Exception:  # noqa: BLE001
                pass
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
            try:
                from conversation_control_plane.claimed_turn_complete_contract import (
                    confirm_fails_soft_to_redisplay as _failsoft_pick,
                )

                if _failsoft_pick(awaiting=awaiting, query=query):
                    # conv_7eb60d26: "ok" at the domain picker is not a domain.
                    # Clearing awaiting here sent the turn to the builder LLM
                    # with nothing to continue — hollow recap, blocks=[].
                    plan = TurnPlan(
                        agent=agent,
                        mode="active_task",
                        task=active_task_obj,
                        reason=(
                            f"failsoft_redisplay fat_leaf awaiting={awaiting}"
                        ),
                    )
                    _maybe_log_conflict(
                        db, tenant_id, conversation_id, plan,
                        live_route_intent, live_route_layer,
                        "failsoft_redisplay fat_leaf",
                    )
                    return plan
            except Exception:  # noqa: BLE001 — fail-soft must never block continue
                logger.debug("failsoft fat-leaf redisplay skipped", exc_info=True)
            plan = TurnPlan(agent=agent, mode="active_task", task=active_task_obj,
                            reason=f"active_task continue for {awaiting} ({intent_source})")
            _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                                live_route_layer, "active_task continue")
            update_phase(db, tenant_id, conversation_id, agent=agent,
                         phase=current_active.get("phase", "active"), awaiting=None)
            return plan

        # 4b) Cognition named an act the OPEN TASK owns — that is the task's own
        # work arriving, not a side question. conv_7446cb2a: a process paste
        # named a draft act (workflow_draft_request) while workflow_build was open, fell
        # through to (5), and dispatched to the 78-tool orchestrator, which
        # picked draft_workflow and minted a prose card the kill-switch had
        # already turned off. The owner was declared the whole time; only the
        # trace-time instrument read it. Fails closed on an unnamed turn.
        try:
            from conversation_control_plane.pre_decide_owner_contract import (
                named_acts_continue_task_kind,
            )

            if named_acts_continue_task_kind(
                str(current_active.get("kind") or ""),
            ):
                plan = TurnPlan(
                    agent=agent, mode="active_task", task=active_task_obj,
                    reason=(
                        f"active_task continue: cognition named the task's own "
                        f"act ({intent_source})"
                    ),
                )
                _maybe_log_conflict(
                    db, tenant_id, conversation_id, plan, live_route_intent,
                    live_route_layer, "active_task continue (named act)",
                )
                update_phase(db, tenant_id, conversation_id, agent=agent,
                             phase=current_active.get("phase", "active"),
                             awaiting=None)
                return plan
            # conv_4ac10b7c retry: cognition missed the flag; the open
            # owner still owns a process-body turn. Never 80-tool detour
            # into draft_workflow prose.
            # A named foreign act is not a missed flag — G5 I8 forbids
            # reinterpreting it as process body (conv_0f96d344).
            _open_kind = str(current_active.get("kind") or "")
            if _open_kind in ("drafting", WORKFLOW_BUILD_KIND):
                try:
                    from conversation_control_plane.draft_content_strength_contract import (
                        live_query_is_process_seed as _proc_body_d4,
                    )
                    from conversation_control_plane.pre_decide_owner_contract import (
                        named_acts_are_foreign_to_task_kind as _named_foreign_d4,
                    )

                    if _named_foreign_d4(_open_kind):
                        pass
                    elif _proc_body_d4(query or ""):
                        if (
                            _open_kind == WORKFLOW_BUILD_KIND
                            or agent == "workflow_builder"
                        ):
                            plan = TurnPlan(
                                agent=agent, mode="active_task",
                                task=active_task_obj,
                                reason=(
                                    "active_task continue: process body on "
                                    f"open owner ({intent_source})"
                                ),
                            )
                            _maybe_log_conflict(
                                db, tenant_id, conversation_id, plan,
                                live_route_intent, live_route_layer,
                                "active_task continue (process body)",
                            )
                            update_phase(
                                db, tenant_id, conversation_id, agent=agent,
                                phase=current_active.get("phase", "active"),
                                awaiting=None,
                            )
                            return plan
                        complete_task(
                            db, tenant_id, conversation_id, agent="bot0",
                            reason="superseded",
                            task_id=(
                                current_active.get("task_id")
                                if isinstance(current_active.get("task_id"), str)
                                else None
                            ),
                        )
                        from conversation_control_plane.ledger import (
                            handoff as _d4_proc_handoff,
                        )

                        _d4_proc_handoff(
                            db, tenant_id, conversation_id,
                            target_agent="workflow_builder",
                            task_text="in_progress",
                            reason="process body on drafting",
                        )
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
                                "process body on drafting — builder owns "
                                f"extract ({intent_source})"
                            ),
                        )
                        _maybe_log_conflict(
                            db, tenant_id, conversation_id, plan,
                            live_route_intent, live_route_layer,
                            "D4 process body drafting handoff",
                        )
                        return plan
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "process-body owner continue skipped", exc_info=True,
                    )
        except Exception:  # noqa: BLE001 — a rescue must never break the turn
            logger.debug("named-act continue check skipped", exc_info=True)

        # 5) Otherwise a detour while active (a side question; answer then offer resume).
        plan = TurnPlan(agent=live_route_intent, mode="detour", task=active_task_obj,
                        reason=f"detour while active_task present ({intent_source})")
        _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent,
                            live_route_layer, "detour while active_task")
        return plan

    # --- Step 5/6/7: detour classification + resume from suspended + default ---
    # Use the router's proposed agent (live_route_intent) as the outcome.
    # The real implementation will call the (demoted) classifier only for genuine detours.
    # Check for resume from suspended first (step 6): if a suspended task's "awaiting"
    # plausibly matches the message, we resume it (after resolve_pending in real code).
    # When the live router broke to bot0, this turn is a Bot0 question/detour — do
    # NOT auto-resume a suspended heavy task. Resume only when the bounded LLM
    # classifier perceives continue/resume targeting the suspended agent.
    route_broke_to_bot0 = live_route_intent == "bot0" and _act not in ("continue", "resume")
    for s in suspended:
        s_agent = _canonical(s.get("agent", ""))
        if not s.get("awaiting") or route_broke_to_bot0:
            continue
        perceived = None
        try:
            perceived = _perceive_relative_intent(
                db, tenant_id, query=query,
                active_task=None, suspended_tasks=suspended,
                messages=messages,
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

    # B-240: the router's agent is a PROPOSAL. Opening its ledger task here
    # left admitted work behind whenever a later leaf answered the turn
    # (conv_b4bc0ea1: an advisor task opened, never ran, then suspended with
    # no journal row). Admission happens at the agent's dispatch entry —
    # `admission_contract.admit_at_dispatch` — where it is true.
    from conversation_control_plane.admission_contract import propose as _propose

    _propose(
        agent=target,
        router_intent=live_route_intent,
        router_layer=live_route_layer,
        kind=ledger_kind_for_agent(target),
    )

    _maybe_log_conflict(db, tenant_id, conversation_id, plan, live_route_intent, live_route_layer,
                        "default: router proposal (admitted at dispatch)")
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
