"""Needs and personality pull on everyday choices (log-odds shifts per activity tag).

The model reads the person and their situation; these rules guarantee that needs
(hunger, tiredness, loneliness, stress) and personality (Big Five) still move choices
even when a model under-reads them. Every shift is named so traces can explain it.
"""

from __future__ import annotations

from ..population import Agent
from .config import Activity
from .feelings import Feelings


def activity_shifts(activity: Activity, agent: Agent, f: Feelings, slot_id: str) -> dict[str, float]:
    b5 = agent.big_five or {}
    e, c, a = b5.get("extraversion", 0.5), b5.get("conscientiousness", 0.5), b5.get("agreeableness", 0.5)
    o, n = b5.get("openness", 0.5), b5.get("neuroticism", 0.5)
    tags = set(activity.tags)
    s: dict[str, float] = {}
    if "eat" in tags:
        s["hunger"] = 2.0 * f.hunger - 0.8
    if "rest" in tags:
        s["tiredness"] = 1.8 * (1 - f.energy) - 0.6
    if "social" in tags:
        s["extraversion"] = 1.5 * (e - 0.5)
        s["wants company"] = 1.5 * (f.social_need - 0.5)
        if f.energy < 0.35:
            s["too tired to socialise"] = -0.8 * (1 - e)
    if "solo" in tags:
        s["introversion"] = 1.2 * (0.5 - e) + 0.8 * (0.5 - f.social_need)
    if "exercise" in tags:
        s["discipline"] = 0.8 * (c - 0.5)
        s["energy"] = 1.2 * (f.energy - 0.5)
        s["blow off steam"] = 0.6 * f.stress
    if tags & {"study", "work", "routine"}:
        s["conscientiousness"] = 1.6 * (c - 0.5)
    if "slack" in tags:
        s["low discipline"] = 1.6 * (0.5 - c)
    if "obligation" in tags:
        s["expected of them"] = 0.8
    if "truancy" in tags:
        s["breaks the rules"] = -0.8 - 0.8 * c
    if "media" in tags:
        s["follows feeds"] = 1.0 * (agent.traits.get("trend_following", 0.5) - 0.5)
        if slot_id == "night" and agent.chronotype == "night owl":
            s["night owl"] = 0.6
    if "post" in tags:
        s["likes posting"] = {"often": 1.2, "sometimes": 0.2, "rarely": -0.8, "never": -4.0}.get(agent.posting, 0.0)
    if "fun" in tags:
        s["stress relief"] = 0.8 * f.stress + 0.4 * (o - 0.5)
    if "family" in tags:
        s["warmth"] = 0.8 * (a - 0.5)
    if "worry" in tags:
        s["anxious mind"] = 2.0 * (n - 0.5) + 1.2 * (f.stress - 0.4)
    if "treat" in tags:
        s["mood to treat"] = 0.5 * (f.mood < 0) - 0.6 * agent.traits.get("price_sensitivity", 0.5)
    if "money" in tags:
        s["needs money"] = 1.2 * agent.traits.get("price_sensitivity", 0.5) - 0.4
    if "outing" in tags:
        s["curiosity"] = 0.5 * (o - 0.5)
    if slot_id == "night" and "rest" in tags:
        s["early bird"] = 0.7 if agent.chronotype == "early bird" else -0.4 if agent.chronotype == "night owl" else 0.0
    return {k: round(v, 3) for k, v in s.items() if abs(v) > 1e-6}
