"""The words a person reads for our internal kinds and agents (B-266 S2, D6).

Walid, 10-12, on the resume card ("We were mid-workflow build (staffing)"):
messages say "workflow" when the person likely means a formation — "just move
to work system, so we don't have to decipher". Three modules each kept their
own table of these words (session_staleness, session_activities, bot0); this
is the one table they all read.

Keys are internal ids (``active_task.kind``, agent ids) and never change; only
the words do. No value may say "workflow" — `test_kind_labels_say_work_system`.
"""
from __future__ import annotations

from typing import NamedTuple


class KindWords(NamedTuple):
    #: A title, e.g. in the list of open activities ("Work system design").
    title: str
    #: A phrase after "in the middle of" ("building a work system").
    phrase: str


#: ``active_task.kind`` → its words. A phrase containing "a work system" names
#: the work system when its name is known (``kind_phrase``).
KIND_WORDS: dict[str, KindWords] = {
    "cost_out": KindWords("Agent cost / TCO", "the agent cost-out"),
    "agent_cost_pricing": KindWords("Agent cost profile", "the agent cost profile"),
    "cyber_risk_assessment": KindWords("Cyber risk assessment", "the cyber risk assessment"),
    "realization_intake": KindWords("Agent realization", "the realization plan"),
    "outcome_value_setup": KindWords("Outcome & value setup", "the outcome & value setup"),
    "drafting": KindWords("Work system draft", "drafting a work system"),
    "project_workspace": KindWords("Project setup (roles & simulation)", "the project setup"),
    "scorecard_interrogate": KindWords("Scorecard review", "the scorecard review"),
    "risk_catalog_learning": KindWords("Risk catalog", "the risk catalog"),
    "workflow_build": KindWords("Work system design", "building a work system"),
    "pattern_midflight": KindWords("Simulation pattern", "the simulation pattern"),
    "recommendation_setup": KindWords("Recommendation setup", "the recommendation setup"),
    "engagement_pack_plan": KindWords("Initiative plan", "the initiative plan"),
    "input_state_setup": KindWords("Simulation inputs", "the simulation inputs"),
    "pending_question": KindWords("Waiting for your pick", "your pick"),
    "workspace_list": KindWords("Workspace list", "the workspace list"),
}

#: Agent id → the name a person sees.
AGENT_WORDS: dict[str, str] = {
    "workflow_builder": "Work System Builder",
    "workflow_editor": "Work System Editor",
    "transformation_advisor": "Transformation Advisor",
    "transformation_recommender": "Transformation Recommender",
    "advisor": "Transformation Advisor",
    "recommender": "Transformation Recommender",
    "bot0": "Bot0 Assistant",
}


def kind_title(kind: str) -> str:
    words = KIND_WORDS.get(str(kind or ""))
    return words.title if words else ""


def kind_phrase(kind: str, *, work_system_name: str = "") -> str:
    """The phrase for a kind, naming the work system when it is known:
    "building **Victorious Product Launch** (a work system)"."""
    words = KIND_WORDS.get(str(kind or ""))
    if not words:
        return ""
    name = str(work_system_name or "").strip()
    if name and "a work system" in words.phrase:
        return words.phrase.replace("a work system", f"**{name}** (a work system)")
    return words.phrase


def agent_name(agent: str) -> str:
    return AGENT_WORDS.get(str(agent or ""), str(agent or ""))


__all__ = ["AGENT_WORDS", "KIND_WORDS", "KindWords", "agent_name", "kind_phrase", "kind_title"]
