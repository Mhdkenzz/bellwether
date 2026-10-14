"""Seeded population sampling. Same config + size + seed always gives the same people."""

from __future__ import annotations

import math
import random
from collections import Counter
from typing import Sequence, TypeVar

from ..expr import evaluate
from . import pools
from .config import Cohort, PopulationConfig
from .depth import deepen_population
from .graph import build_ties
from .models import Agent, Population
from .persona import render_persona

T = TypeVar("T")


def allocate(total: int, shares: Sequence[float]) -> list[int]:
    """Largest-remainder allocation of `total` items by `shares`."""
    raw = [total * s for s in shares]
    counts = [math.floor(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[: total - sum(counts)]:
        counts[i] += 1
    return counts


def weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


class _Spreader:
    """Picks from a pool while favouring rarely-used items, so agents don't repeat each other."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.uses: Counter[str] = Counter()

    def pick(
        self,
        pool: Sequence[str],
        k: int = 1,
        exclude: set[str] | None = None,
        fit: dict[str, float] | None = None,
    ) -> list[str]:
        """Pick k items, favouring unused ones and, when `fit` is given, ones that fit the traits."""
        chosen: list[str] = []
        exclude = set(exclude or ())
        for _ in range(k):
            candidates = [p for p in pool if p not in exclude and p not in chosen]
            if not candidates:
                break
            if fit:
                # Do not spend a scarce persona slot on a clear contradiction when
                # at least one compatible option remains. This keeps traits and the
                # rendered habits coherent without forcing every detail to match.
                compatible = [c for c in candidates if fit.get(c, 1.0) >= 1.0]
                if compatible:
                    candidates = compatible
            low = min(self.uses[c] for c in candidates)
            weights = [2.0 if self.uses[c] == low else 1.0 / (1 + self.uses[c] - low) for c in candidates]
            if fit:
                weights = [w * fit.get(c, 1.0) for w, c in zip(weights, candidates)]
            item = self.rng.choices(candidates, weights=weights, k=1)[0]
            chosen.append(item)
            self.uses[item] += 1
        return chosen


def trait_fit(affinities: dict[str, dict[str, float]], traits: dict[str, float], strength: float = 3.0) -> dict[str, float]:
    """Weight multiplier per pool item: high when its affinities agree with the agent's traits."""
    out = {}
    for item, aff in affinities.items():
        x = sum(sign * (2 * traits.get(t, 0.5) - 1) for t, sign in aff.items())
        out[item] = math.exp(strength * x)
    return out


def _income_weights(cfg: PopulationConfig, cohort: Cohort | None, life_stage: str) -> dict[str, float]:
    if cohort and cohort.income:
        return cohort.income
    mult = pools.INCOME_BY_LIFE_STAGE.get(life_stage, {})
    return {k: w * mult.get(k, 1.0) for k, w in cfg.income.items()}


def _life_stage_for_age(age: int) -> str:
    stage = pools.LIFE_STAGES_BY_AGE[0][1]
    for min_age, name in pools.LIFE_STAGES_BY_AGE:
        if age >= min_age:
            stage = name
    return stage


def _trait_vector(
    rng: random.Random, cfg: PopulationConfig, cohort: Cohort | None, attrs: dict[str, str]
) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, dist in cfg.traits.items():
        value = rng.betavariate(*dist.beta)
        for key, delta in dist.shift.items():
            field, _, wanted = key.partition(".")
            if attrs.get(field) == wanted:
                value += delta
        if cohort:
            value += cohort.trait_shift.get(name, 0.0)
        out[name] = round(min(0.98, max(0.02, value)), 3)
    return out


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.sqrt(sum((a[k] - b[k]) ** 2 for k in a))


def _distinct_traits(
    rng: random.Random,
    cfg: PopulationConfig,
    cohort: Cohort | None,
    attrs: dict[str, str],
    existing: list[dict[str, float]],
    tries: int = 80,
) -> dict[str, float]:
    """Rejection-sample a trait vector at least `min_trait_distance` from everyone so far."""
    best, best_gap = None, -1.0
    for _ in range(tries):
        cand = _trait_vector(rng, cfg, cohort, attrs)
        gap = min((_distance(cand, e) for e in existing), default=math.inf)
        if gap >= cfg.min_trait_distance:
            return cand
        if gap > best_gap:
            best, best_gap = cand, gap
    assert best is not None
    return best


def segments_for(agent_fields: dict, traits: dict[str, float], cfg: PopulationConfig) -> list[str]:
    env = {**agent_fields, **traits}
    return [name for name, rule in cfg.segments.items() if evaluate(rule, env)]


def sample_population(cfg: PopulationConfig, size: int | None = None, seed: int | None = None,
                      mix: dict[str, float] | None = None) -> Population:
    """The people a run uses: everyone written in the file (or a share of them), several communities
    combined (`include:`), or, for a config with no written people, a freshly generated population.

    `mix` sets the proportion of each part: communities for a combined config, cohorts otherwise.
    """
    if cfg.include:
        from .combine import combine
        return combine(cfg, size=size, seed=seed, mix=mix)
    if cfg.agents:
        from .handmade import build_handmade
        return build_handmade(cfg, size=size, seed=seed, mix=mix)
    if mix:
        unknown = set(mix) - {c.name for c in cfg.cohorts}
        if unknown:
            raise ValueError(f"unknown cohorts in mix: {sorted(unknown)}")
        total = sum(mix.values())
        cfg = cfg.model_copy(update={"cohorts": [c.model_copy(update={"share": mix.get(c.name, 0) / total})
                                                 for c in cfg.cohorts]})
    return generate_population(cfg, size=size, seed=seed)


def generate_population(cfg: PopulationConfig, size: int | None = None, seed: int | None = None) -> Population:
    """Draw new people from the config's distributions and option pools (ignores written people)."""
    size = size or cfg.size
    seed = cfg.seed if seed is None else seed
    rng = random.Random(f"bellwether-population:{cfg.name}:{size}:{seed}")
    spread = _Spreader(rng)

    cohorts: list[Cohort | None] = []
    if cfg.cohorts:
        for cohort, n in zip(cfg.cohorts, allocate(size, [c.share for c in cfg.cohorts])):
            cohorts += [cohort] * n
        rng.shuffle(cohorts)
    else:
        cohorts = [None] * size

    names = list(pools.FIRST_NAMES)
    rng.shuffle(names)
    quirk_pool = list(pools.QUIRKS)
    quirk_affinity = {q: pools.QUIRK_AFFINITY.get(q, {}) for q in quirk_pool}

    agents: list[Agent] = []
    trait_vectors: list[dict[str, float]] = []
    signatures: set[tuple] = set()

    for i, cohort in enumerate(cohorts):
        age_range = (cohort.age if cohort and cohort.age else None) or cfg.age
        age = rng.randint(*age_range)
        if cohort and cohort.life_stage:
            # minors in a mixed cohort are students, not early-career workers
            stages = ["student"] if age < 18 and "student" in cohort.life_stage else cohort.life_stage
            life_stage = rng.choice(stages)
        else:
            life_stage = _life_stage_for_age(age)
        income = weighted_choice(rng, _income_weights(cfg, cohort, life_stage))
        location = weighted_choice(rng, (cohort.location if cohort and cohort.location else None) or cfg.location)
        attrs = {
            "income": income,
            "location": location,
            "life_stage": life_stage,
            "cohort": cohort.name if cohort else "",
        }
        traits = _distinct_traits(rng, cfg, cohort, attrs, trait_vectors)
        trait_vectors.append(traits)

        occupation_pool = (cohort.occupations if cohort and cohort.occupations else None) or pools.OCCUPATIONS.get(
            life_stage, pools.OCCUPATIONS["mid career"]
        )
        occupation = spread.pick(occupation_pool)[0]

        signature = None
        for _ in range(200):
            interests = spread.pick(pools.INTERESTS, 3, exclude=pools.ADULT_INTERESTS if age < 18 else None)
            candidate_signature = (occupation, tuple(sorted(interests)))
            if candidate_signature not in signatures:
                signature = candidate_signature
                break
        if signature is None:
            raise ValueError(
                f"could not create a unique occupation/interest signature for agent {i + 1}; "
                "increase the available pools or reduce population size"
            )
        signatures.add(signature)

        values = spread.pick(pools.VALUES, 2)
        quirk = spread.pick(quirk_pool, fit=trait_fit(quirk_affinity, traits))[0]

        lo, hi = cfg.budget.get(income, (50, 150))
        budget = round(rng.uniform(lo, hi) / 5) * 5

        name = names[i % len(names)]
        if i >= len(names):
            name = f"{name} {chr(ord('A') + (i // len(names)) - 1)}."

        fields = {"age": age, "income": income, "location": location, "life_stage": life_stage,
                  "cohort": attrs["cohort"], "budget": budget}
        agent = Agent(
            id=f"a{i + 1:03d}",
            name=name,
            age=age,
            cohort=cohort.name if cohort else None,
            cohort_label=(cohort.label or cohort.name) if cohort else None,
            life_stage=life_stage,
            occupation=occupation,
            location=location,
            income=income,
            budget=budget,
            interests=interests,
            values=values,
            shopping_style=spread.pick(list(pools.SHOPPING_STYLES), fit=trait_fit(pools.SHOPPING_STYLES, traits))[0],
            media_habit=spread.pick(list(pools.MEDIA_HABITS), fit=trait_fit(pools.MEDIA_HABITS, traits))[0],
            decision_style=spread.pick(list(pools.DECISION_STYLES), fit=trait_fit(pools.DECISION_STYLES, traits))[0],
            quirk=quirk,
            traits=traits,
            segments=segments_for(fields, traits, cfg),
        )
        agents.append(agent)

    ties = build_ties(agents, cfg, rng)
    for agent in agents:
        agent.persona = render_persona(agent, cfg)
    for agent in agents:
        agent.community = cfg.name
    population = Population(name=cfg.name, seed=seed, config=cfg, agents=agents, ties=ties)
    deepen_population(population)
    return population
