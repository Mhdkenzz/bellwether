"""Resolve a scenario Selector to a set of agent ids."""

from __future__ import annotations

import random

from ..expr import evaluate
from ..population import Agent, Population
from ..scenario import Selector


def agent_env(agent: Agent, flags: set[str]) -> dict:
    return {
        **agent.traits,
        "age": agent.age,
        "income": agent.income,
        "cohort": agent.cohort or "",
        "community": agent.community,
        "life_stage": agent.life_stage,
        "budget": agent.budget,
        "flags": sorted(flags),
    }


def select(
    selector: Selector,
    population: Population,
    flags: dict[str, set[str]],
    rng: random.Random,
    count: int | None = None,
) -> set[str]:
    """Agents matching every condition; then `fraction`/`count` sampling; then widening."""
    matched: list[str] = []
    cohorts = [selector.cohort] if isinstance(selector.cohort, str) else selector.cohort
    communities = [selector.community] if isinstance(selector.community, str) else selector.community
    for a in population.agents:
        f = flags.get(a.id, set())
        if selector.flag and selector.flag not in f:
            continue
        if selector.not_flag and selector.not_flag in f:
            continue
        if cohorts and a.cohort not in cohorts:
            continue
        if communities and a.community not in communities:
            continue
        if selector.segment and selector.segment not in a.segments:
            continue
        if selector.ids is not None and a.id not in selector.ids:
            continue
        if selector.where and not evaluate(selector.where, agent_env(a, f)):
            continue
        if selector.platform and selector.platform not in a.platforms:
            continue
        matched.append(a.id)

    if count is not None:
        matched = rng.sample(matched, min(count, len(matched)))
    elif selector.fraction is not None:
        k = round(len(matched) * selector.fraction)
        matched = rng.sample(matched, min(k, len(matched)))

    result = set(matched)
    if selector.include_groups:
        groups = {population.agent(aid).group for aid in matched}
        result |= {a.id for a in population.agents if a.group in groups}
    if selector.include_ties:
        for aid in matched:
            for other, tie in population.neighbors(aid):
                if selector.include_ties == "all" or tie.kind == "strong":
                    result.add(other)
    return result
