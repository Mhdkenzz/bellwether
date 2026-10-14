"""Written populations: every person written out in YAML, all 10 description groups filled.

See guide.md for how to write one. A config with an `agents:` list is built here instead of
being sampled. Typos and missing categories are errors, so a hand-written person is always
as complete as a sampled one. Derived fields (persona text, segments, introvert/extrovert,
temperament, how easily swayed) are computed the same way as for sampled people.
"""

from __future__ import annotations

import math
import random
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..expr import evaluate
from .config import BIG_FIVE, CORE_TRAITS, PopulationConfig
from .depth import _temperament, personality_type, render_profile
from .graph import STRONG_WEIGHT, WEAK_WEIGHT, _label
from .mix import plan_counts
from .models import Agent, Population, Tie
from .persona import render_persona

LIFE_STAGES = Literal["student", "early career", "settling down", "mid career", "late career", "retired"]


def _unit(v: float) -> float:
    if not 0 <= v <= 1:
        raise ValueError("must be between 0 and 1")
    return v


class HandAgent(BaseModel):
    """One hand-written person. Every field below is required unless it has a default."""

    model_config = ConfigDict(extra="forbid")

    # 1. identity
    name: str
    age: int = Field(ge=10, le=100)
    cohort: str | None = None
    life_stage: LIFE_STAGES
    occupation: str
    location: str
    # 2. money
    income: Literal["low", "mid", "high"]
    budget: float = Field(ge=0)
    # 3. personality
    traits: dict[str, float]
    big_five: dict[str, float]
    chronotype: Literal["early bird", "night owl", "in between"]
    temperament: str | None = None  # derived from Big Five when left out
    # 4. habits and tastes
    interests: list[str] = Field(min_length=3, max_length=3)
    values: list[str] = Field(min_length=2, max_length=2)
    shopping_style: str
    media_habit: str
    decision_style: str
    quirk: str
    music: str
    food: str
    # 5. life situation
    living: str
    goal_short: str
    goal_long: str
    worries: list[str] = Field(min_length=2, max_length=2)
    life_context: str
    stress: float = 0.3  # how stressful their current situation is, 0..1
    mood: float = 0.0  # how their current situation lifts or drags their mood, -1..1
    # 6. social life
    platforms: list[str] = Field(default_factory=list)
    posting: Literal["often", "sometimes", "rarely", "never"]
    # 7. health and wellbeing
    health: str
    sleep: str
    fitness: str
    # 8. relationships and home
    relationship: str
    pets: str
    family_closeness: str
    # 9. background
    hometown: str
    family_money: str
    formative: str
    # 10. attitudes and beliefs
    money_mindset: str
    brand_attitude: str
    tech_attitude: str
    cause: str
    # social graph
    group: str
    family: list[str] = Field(default_factory=list)  # names of relatives in this population
    close_to: list[str] = Field(default_factory=list)  # extra close friends outside their group
    knows: list[str] = Field(default_factory=list)  # acquaintances (weak ties); write each pair once

    @field_validator("traits")
    @classmethod
    def _traits(cls, v: dict[str, float]) -> dict[str, float]:
        missing = set(CORE_TRAITS) - set(v)
        if missing:
            raise ValueError(f"traits missing {sorted(missing)}")
        return {k: _unit(x) for k, x in v.items()}

    @field_validator("big_five")
    @classmethod
    def _big_five(cls, v: dict[str, float]) -> dict[str, float]:
        if set(v) != set(BIG_FIVE):
            raise ValueError(f"big_five needs exactly {list(BIG_FIVE)}")
        return {k: _unit(x) for k, x in v.items()}

    @model_validator(mode="after")
    def _consistent(self) -> "HandAgent":
        if (self.posting == "never") != (not self.platforms):
            raise ValueError(f"{self.name}: posting 'never' if and only if they use no platforms")
        if self.age < 18 and self.life_stage != "student":
            raise ValueError(f"{self.name}: under-18s are students")
        if not -1 <= self.mood <= 1 or not 0 <= self.stress <= 1:
            raise ValueError(f"{self.name}: stress is 0..1 and mood is -1..1")
        return self


def _pick(people: list[HandAgent], size: int | None, mix: dict[str, float] | None) -> list[HandAgent]:
    """Everyone, or `size` people keeping each cohort's share (or the `mix` shares), in file order."""
    by_cohort: dict[str, list[HandAgent]] = {}
    for h in people:
        by_cohort.setdefault(h.cohort or "", []).append(h)
    if size is not None and size > len(people) and mix is None:
        raise ValueError(f"only {len(people)} people are written; asked for {size}")
    counts = plan_counts({k: len(v) for k, v in by_cohort.items()}, size, mix)
    keep = {id(h) for k, group in by_cohort.items() for h in group[: counts[k]]}
    return [h for h in people if id(h) in keep]


def build_handmade(cfg: PopulationConfig, size: int | None = None, seed: int | None = None,
                   mix: dict[str, float] | None = None) -> Population:
    seed = cfg.seed if seed is None else seed
    people = [HandAgent.model_validate(a) for a in cfg.agents or []]
    names = [h.name for h in people]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"names must be unique; repeated: {dupes}")
    written = set(names)
    for h in people:  # check links against everyone written, before any size cut
        for kind, names in (("family member", h.family), ("close_to", h.close_to), ("knows", h.knows)):
            for other in names:
                if other not in written:
                    raise ValueError(f"{h.name}: {kind} {other!r} is not in this population")
    people = _pick(people, size, mix)
    labels = {c.name: (c.label or c.name) for c in cfg.cohorts}
    platforms = set(cfg.social_media.platforms)
    for h in people:  # same trait order for everyone, so distances compare like with like
        missing = set(cfg.traits) - set(h.traits)
        if missing:
            raise ValueError(f"{h.name}: traits missing {sorted(missing)} (this config uses {list(cfg.traits)})")
        h.traits = {t: h.traits[t] for t in cfg.traits} | {t: v for t, v in h.traits.items() if t not in cfg.traits}
    for i, left in enumerate(people):
        for right in people[i + 1:]:
            gap = math.dist(list(left.traits.values()), list(right.traits.values()))
            if gap < cfg.min_trait_distance:
                raise ValueError(f"{left.name} and {right.name} have near-identical traits (distance {gap:.2f}, "
                                 f"need {cfg.min_trait_distance}); make them differ more")
    agents: list[Agent] = []
    for i, h in enumerate(people):
        bad = set(h.platforms) - platforms
        if bad:
            raise ValueError(f"{h.name}: unknown platforms {sorted(bad)}; config has {sorted(platforms)}")
        if h.cohort is not None and h.cohort not in labels:
            raise ValueError(f"{h.name}: unknown cohort {h.cohort!r}")
        b5 = {k: h.big_five[k] for k in BIG_FIVE}
        fields = {"age": h.age, "income": h.income, "location": h.location, "life_stage": h.life_stage,
                  "cohort": h.cohort or "", "budget": h.budget}
        a = Agent(
            id=f"a{i + 1:03d}", name=h.name, age=h.age, cohort=h.cohort,
            cohort_label=labels.get(h.cohort) if h.cohort else None, community=cfg.name, life_stage=h.life_stage,
            occupation=h.occupation, location=h.location, income=h.income, budget=h.budget,
            interests=h.interests, values=h.values, shopping_style=h.shopping_style, media_habit=h.media_habit,
            decision_style=h.decision_style, quirk=h.quirk, traits=h.traits,
            segments=[s for s, rule in cfg.segments.items() if evaluate(rule, {**fields, **h.traits})],
            group=h.group, big_five=b5, personality_type=personality_type(b5["extraversion"]),
            chronotype=h.chronotype, living=h.living, goal_short=h.goal_short, goal_long=h.goal_long,
            worries=h.worries, life_context=h.life_context,
            stress_baseline=round(min(0.9, h.stress * (0.6 + 0.8 * b5["neuroticism"])), 3),
            mood_baseline=round(max(-0.8, min(0.8, 0.35 * (b5["extraversion"] - 0.5) - 0.45 * (b5["neuroticism"] - 0.5)
                                              + h.mood)), 3),
            music=h.music, food=h.food, temperament=h.temperament or _temperament(b5), platforms=sorted(h.platforms),
            posting=h.posting,
            susceptibility=round(0.5 * h.traits["trend_following"] + 0.3 * b5["agreeableness"] + 0.2 * b5["neuroticism"], 3),
            health=h.health, sleep=h.sleep, fitness=h.fitness, relationship=h.relationship, pets=h.pets,
            family_closeness=h.family_closeness, hometown=h.hometown, family_money=h.family_money,
            formative=h.formative, money_mindset=h.money_mindset, brand_attitude=h.brand_attitude,
            tech_attitude=h.tech_attitude, cause=h.cause,
        )
        a.persona = render_persona(a, cfg)
        agents.append(a)

    by_name = {a.name: a for a in agents}
    ties: list[Tie] = []
    seen: set[tuple[str, str]] = set()

    def tie(x: Agent, y: Agent, kind: str, label: str | None = None, explicit: bool = False) -> None:
        a, b = sorted((x.id, y.id))
        if a == b or (a, b) in seen:
            return
        seen.add((a, b))
        default = cfg.groups.strong_label if kind == "strong" else cfg.groups.weak_label
        label = label or _label(x, y, default, cfg)
        if label == "family" and not explicit:  # here family is only who you list under `family:`
            label = "family friend"
        ties.append(Tie(a=a, b=b, kind=kind, weight=STRONG_WEIGHT if kind == "strong" else WEAK_WEIGHT, label=label))

    for h, a in zip(people, agents):
        for rel in h.family:  # family first, so the label is "family" even inside a friend group
            if rel in by_name:  # may be missing when only the first `size` people are used
                tie(a, by_name[rel], "strong", "family", explicit=True)
    for x in agents:
        for y in agents:
            if x.id < y.id and x.group == y.group:
                tie(x, y, "strong")
    for h, a in zip(people, agents):
        for friend in h.close_to:
            if friend in by_name:
                tie(a, by_name[friend], "strong")
    for h, a in zip(people, agents):
        for other in h.knows:
            if other in by_name:
                tie(a, by_name[other], "weak")
    if not any(h.knows for h in people):  # no acquaintances written: add seeded random ones
        rng = random.Random(f"bellwether-handmade:{cfg.name}:{seed}")
        for a in agents:
            others = [o for o in agents if o.group != a.group]
            rng.shuffle(others)
            for o in others[: cfg.groups.weak_ties_per_agent]:
                tie(a, o, "weak")

    population = Population(name=cfg.name, seed=seed, config=cfg, agents=agents, ties=ties)
    for a in population.agents:
        a.profile = render_profile(a, population)
    return population
