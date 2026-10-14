"""Deeper personhood: personality, daily rhythm, home life, inner life and online life.

Sampled from its own seeded stream so adding depth never changes an agent's core traits.
Big Five and platform use are drawn independently of age, income and cohort by default,
so no demographic stereotype is baked in unless a config adds one.
"""

from __future__ import annotations

import random

from . import pools
from .config import BIG_FIVE, PopulationConfig
from .models import Agent, Population


def personality_type(extraversion: float) -> str:
    if extraversion < 0.36:
        return "introvert"
    if extraversion > 0.64:
        return "extrovert"
    return "ambivert"


def _temperament(b5: dict[str, float]) -> str:
    # The two most pronounced poles describe how this person comes across.
    poles = sorted(((abs(v - 0.5), t, int(v >= 0.5)) for t, v in b5.items()), reverse=True)[:2]
    return "; ".join(pools.TEMPERAMENT[(t, hi)] for _, t, hi in poles)


def _platforms(rng: random.Random, cfg: PopulationConfig) -> list[str]:
    sm = cfg.social_media
    counts = list(sm.platform_counts)
    n = rng.choices(counts, weights=[sm.platform_counts[c] for c in counts], k=1)[0]
    ids = sorted(sm.platforms)
    return sorted(rng.sample(ids, min(n, len(ids))))


def deepen(agent: Agent, cfg: PopulationConfig, rng: random.Random) -> None:
    b5 = {}
    for t in BIG_FIVE:
        dist = cfg.big_five.get(t)
        a, b = dist.beta if dist else (2.0, 2.0)
        b5[t] = round(min(0.98, max(0.02, rng.betavariate(a, b))), 3)
    agent.big_five = b5
    agent.personality_type = personality_type(b5["extraversion"])
    agent.chronotype = rng.choices(["early bird", "night owl", "in between"], weights=[0.3, 0.35, 0.35])[0]
    agent.living = rng.choice(pools.MINOR_LIVING if agent.age < 18
                              else pools.LIVING.get(agent.life_stage, pools.LIVING["mid career"]))
    agent.goal_short = rng.choice(pools.GOALS_SHORT.get(agent.life_stage, pools.GOALS_SHORT["_"]))
    agent.goal_long = rng.choice(pools.GOALS_LONG)
    agent.worries = rng.sample(pools.WORRIES, 2)
    student_only = {"exam week is coming up"}
    contexts = [c for c in pools.LIFE_CONTEXT if agent.life_stage == "student" or c[0] not in student_only]
    situation, stress, mood_shift = rng.choice(contexts)
    agent.life_context = situation
    agent.stress_baseline = round(min(0.9, stress * (0.6 + 0.8 * b5["neuroticism"])), 3)
    agent.mood_baseline = round(max(-0.8, min(0.8, 0.35 * (b5["extraversion"] - 0.5) - 0.45 * (b5["neuroticism"] - 0.5)
                                              + mood_shift + rng.uniform(-0.1, 0.1))), 3)
    agent.music = rng.choice(pools.MUSIC)
    agent.food = rng.choice(pools.FOODS)
    agent.temperament = _temperament(b5)
    agent.platforms = _platforms(rng, cfg)
    propensity = 0.6 * b5["extraversion"] + 0.4 * agent.traits["social_influence"]
    agent.posting = ("never" if not agent.platforms else "often" if propensity > 0.62
                     else "sometimes" if propensity > 0.4 else "rarely")
    agent.susceptibility = round(0.5 * agent.traits["trend_following"] + 0.3 * b5["agreeableness"]
                                 + 0.2 * b5["neuroticism"], 3)


def render_profile(agent: Agent, population: Population) -> str:
    """The long persona: who they are, how they live, what's on their mind, who they're close to."""
    cfg = population.config
    close = [(population.agent(o).name, t.label) for o, t in population.neighbors(agent.id) if t.kind == "strong"]
    close_txt = ", ".join(f"{n} ({lbl})" for n, lbl in close[:6]) or "nobody in particular"
    labels = {k: v.label for k, v in cfg.social_media.platforms.items()}
    online = (f"Uses {', '.join(labels[p] for p in agent.platforms)}; posts {agent.posting}."
              if agent.platforms else "Isn't on social media.")
    return (
        f"{agent.persona} "
        f"Personality: {agent.personality_type}; {agent.temperament}. {agent.chronotype.capitalize()}. "
        f"Home: {agent.living}. Right now: {agent.life_context}. "
        f"Goal right now: {agent.goal_short}. Dream: {agent.goal_long}. "
        f"Worries about {agent.worries[0]} and {agent.worries[1]}. "
        f"Listens to {agent.music}; loves {agent.food}. {online} Close to: {close_txt}."
    )


def deepen_population(population: Population) -> None:
    rng = random.Random(f"bellwether-depth:{population.name}:{population.size}:{population.seed}")
    for agent in population.agents:
        deepen(agent, population.config, rng)
    for agent in population.agents:
        agent.profile = render_profile(agent, population)
