"""Deeper personhood: personality, daily rhythm, home life, inner life and online life.

Agents are built from the 10 description groups in `categories.py`; fill every one of them.
Sampled from its own seeded stream so adding depth never changes an agent's core traits.
Big Five and platform use are drawn independently of age, income and cohort by default,
so no demographic stereotype is baked in unless a config adds one.
"""

from __future__ import annotations

import math
import random
from collections import Counter

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


def _platforms(rng: random.Random, cfg: PopulationConfig, media_habit: str) -> list[str]:
    """Platform use, kept consistent with the person's media habit."""
    sm = cfg.social_media
    counts = list(sm.platform_counts)
    n = rng.choices(counts, weights=[sm.platform_counts[c] for c in counts], k=1)[0]
    ids = sorted(sm.platforms)
    chosen = set(rng.sample(ids, min(n, len(ids))))
    need = pools.MEDIA_NEEDS_PLATFORM.get(media_habit)
    if need in sm.platforms:
        chosen.add(need)
    if media_habit == "posts regularly and has a following" and not chosen:
        chosen.add(rng.choice(ids))
    if media_habit == "barely uses social media" and len(chosen) > 1:
        chosen = {sorted(chosen)[0]}
    return sorted(chosen)


class _Spread:
    """Prefer options few people have yet, so a population doesn't all share one dream or song."""

    def __init__(self, rng: random.Random):
        self.rng, self.used = rng, Counter()

    def pick(self, pool: list[str], k: int = 1) -> list[str]:
        out: list[str] = []
        for _ in range(k):
            options = [p for p in pool if p not in out]
            weights = [1.0 / (1 + self.used[p]) ** 2 for p in options]
            choice = self.rng.choices(options, weights=weights, k=1)[0]
            self.used[choice] += 1
            out.append(choice)
        return out


def deepen(agent: Agent, cfg: PopulationConfig, rng: random.Random, spread: "_Spread | None" = None) -> None:
    spread = spread or _Spread(rng)
    cohort = next((c for c in cfg.cohorts if c.name == agent.cohort), None)
    minor_home = agent.age < 18 or "high school" in agent.occupation.lower()
    b5 = {}
    for t in BIG_FIVE:
        dist = cfg.big_five.get(t)
        a, b = dist.beta if dist else (2.0, 2.0)
        b5[t] = round(min(0.98, max(0.02, rng.betavariate(a, b))), 3)
    agent.big_five = b5
    agent.personality_type = personality_type(b5["extraversion"])
    agent.chronotype = rng.choices(["early bird", "night owl", "in between"], weights=[0.3, 0.35, 0.35])[0]
    if cohort and cohort.living:
        agent.living = spread.pick(cohort.living)[0]
    else:
        agent.living = rng.choice(pools.MINOR_LIVING if minor_home
                                  else pools.LIVING.get(agent.life_stage, pools.LIVING["mid career"]))
    agent.goal_short = spread.pick(pools.GOALS_SHORT.get(agent.life_stage, pools.GOALS_SHORT["_"]))[0]
    agent.goal_long = spread.pick([g for g in pools.GOALS_LONG if pools.fits_age(pools.DREAM_AGES, g, agent.age)])[0]
    agent.platforms = _platforms(rng, cfg, agent.media_habit)
    worries = [w for w in pools.WORRIES
               if (agent.life_stage == "student" or w != "exams and grades")
               and (not minor_home or w not in pools.ADULT_ONLY_WORRIES)
               and (agent.platforms or w != "being judged online")
               and pools.fits_age(pools.WORRY_AGES, w, agent.age)
               and (agent.life_stage != "retired" or w not in ("job security", "rent going up"))]
    agent.worries = spread.pick(worries, 2)
    student_only = {"exam week is coming up"}
    contexts = [c for c in pools.LIFE_CONTEXT if agent.life_stage == "student" or c[0] not in student_only]
    situation, stress, mood_shift = rng.choice(contexts)
    agent.life_context = situation
    agent.stress_baseline = round(min(0.9, stress * (0.6 + 0.8 * b5["neuroticism"])), 3)
    agent.mood_baseline = round(max(-0.8, min(0.8, 0.35 * (b5["extraversion"] - 0.5) - 0.45 * (b5["neuroticism"] - 0.5)
                                              + mood_shift + rng.uniform(-0.1, 0.1))), 3)
    agent.music = spread.pick(pools.MUSIC)[0]
    agent.food = spread.pick(pools.FOODS)[0]
    agent.temperament = _temperament(b5)
    propensity = 0.6 * b5["extraversion"] + 0.4 * agent.traits["social_influence"]
    agent.posting = ("never" if not agent.platforms else "often" if propensity > 0.62
                     else "sometimes" if propensity > 0.4 else "rarely")
    if agent.platforms and agent.quirk == "never posts but reads everything":
        agent.posting = "rarely"
    if agent.platforms and agent.media_habit == "posts regularly and has a following":
        agent.posting = "often"
    agent.susceptibility = round(0.5 * agent.traits["trend_following"] + 0.3 * b5["agreeableness"]
                                 + 0.2 * b5["neuroticism"], 3)


def _fit_pick(rng: random.Random, table: dict[str, dict[str, float]], profile: dict[str, float]) -> str:
    """Pick from a table of options with trait affinities, favouring options that fit the person."""
    keys = list(table)
    weights = [math.exp(2.5 * sum(sign * (2 * profile.get(t, 0.5) - 1) for t, sign in table[k].items())) for k in keys]
    return rng.choices(keys, weights=weights, k=1)[0]


def round_out(agent: Agent, rng: random.Random, spread: "_Spread | None" = None) -> None:
    """Groups 7-10: health, relationships and home, background, attitudes and beliefs."""
    profile = {**agent.traits, **agent.big_five}
    adult = agent.age >= 18
    # 7. health and wellbeing
    health = [h for h in pools.HEALTH if adult or h not in ("has a bad back", "managing a long-term condition")]
    agent.health = rng.choice(health)
    agent.sleep = _fit_pick(rng, pools.SLEEP, profile)
    fitness = pools.FITNESS
    if agent.health in ("recovering from a sports injury", "fit and healthy but eats badly"):
        fitness = {k: v for k, v in pools.FITNESS.items() if k in ("very active, works out most days", "fairly active")}
    agent.fitness = _fit_pick(rng, fitness, profile)
    # 8. relationships and home (consistent with age and living situation)
    living = agent.living.lower()
    if not adult:
        agent.relationship = rng.choice(pools.RELATIONSHIP_MINOR)
    elif "widowed" in living:
        agent.relationship = "widowed"
    elif "divorce" in living:
        agent.relationship = rng.choice(["divorced", "divorced and dating again"])
    elif "partner" in living:
        agent.relationship = rng.choice(["in a long-term relationship", "married"])
    elif "single parent" in living:
        agent.relationship = rng.choice(["single", "dating casually", "recently separated"])
    else:
        # married people live with their partner; nobody here does, so no "married"
        agent.relationship = rng.choice([r for r in pools.RELATIONSHIP_ADULT if r != "married"])
    dog_person = "dog" in agent.quirk
    agent.pets = rng.choice([p for p in pools.PETS if "dog" in p] if dog_person else pools.PETS)
    agent.family_closeness = _fit_pick(rng, pools.FAMILY_CLOSENESS, profile)
    # 9. background (money growing up leans towards today's income, but not strictly)
    agent.hometown = rng.choice(pools.HOMETOWN)
    lean = {"low": [4, 3, 1.5, 0.5], "mid": [1.5, 3, 3, 1], "high": [0.7, 2, 3, 3]}.get(agent.income, [1, 1, 1, 1])
    agent.family_money = rng.choices(pools.FAMILY_MONEY, weights=lean, k=1)[0]
    agent.formative = spread.pick(pools.FORMATIVE)[0] if spread else rng.choice(pools.FORMATIVE)
    # 10. attitudes and beliefs
    agent.money_mindset = _fit_pick(rng, pools.MONEY_MINDSET, profile)
    agent.brand_attitude = _fit_pick(rng, pools.BRAND_ATTITUDE, profile)
    agent.tech_attitude = _fit_pick(rng, pools.TECH_ATTITUDE, profile)
    agent.cause = rng.choice(pools.CAUSES)


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
        f"Listens to {agent.music}; loves {agent.food}. {online} Close to: {close_txt}. "
        f"Health: {agent.health}; {agent.sleep}; {agent.fitness}. "
        f"Relationships: {agent.relationship}; {agent.family_closeness}; pets: {agent.pets}. "
        f"Background: {agent.hometown}; {agent.family_money}; {agent.formative}. "
        f"Attitudes: {agent.money_mindset}; {agent.brand_attitude}; {agent.tech_attitude}; {agent.cause}."
    )


def deepen_population(population: Population) -> None:
    rng = random.Random(f"bellwether-depth:{population.name}:{population.size}:{population.seed}")
    spread = _Spread(rng)
    for agent in population.agents:
        deepen(agent, population.config, rng, spread)
    rest = random.Random(f"bellwether-depth-2:{population.name}:{population.size}:{population.seed}")
    spread2 = _Spread(rest)
    for agent in population.agents:
        round_out(agent, rest, spread2)
    for agent in population.agents:
        agent.profile = render_profile(agent, population)
