"""Trait sensitivity probe: does a model's decision move when only one trait changes?

Builds one agent's round-1 state for a scenario, then sweeps each trait (number and
its words) across low/mid/high while everything else stays fixed, and reports how the
model's probabilities for every choice option respond.
"""

from __future__ import annotations

import copy
from typing import Any

from .backends import DecisionBackend
from .engine import rules as engine_rules
from .engine.decide import shift, wire_question
from .engine.run import Runner, RunConfig
from .engine.events import EventBus
from .engine.state import build_state
from .population import Population
from .scenario import Scenario

LEVELS = (0.1, 0.5, 0.9)


async def probe_traits(
    population: Population,
    scenario: Scenario,
    backend: DecisionBackend,
    agent_ids: list[str],
    arm: str = "baseline",
    traits: list[str] | None = None,
    extra_circle: list[str] | None = None,
) -> list[dict[str, Any]]:
    runner = Runner(population, scenario, backend, EventBus(), RunConfig("probe", arm, 0, 1, sigma=0))
    runner._init_state()
    seen = {a.id: [] for a in population.agents}
    for j, ev in enumerate(scenario.events_for(arm, 1)):
        runner.world.apply(ev.effects)
        for a in population.agents:
            seen[a.id].append(ev.text)  # probe: everyone sees round-1 events
    questions = {q: wire_question(s) for q, s in scenario.decisions.items() if s.type == "choice"}
    rows = []
    for aid in agent_ids:
        base_agent = population.agent(aid)
        for trait in traits or list(base_agent.traits):
            for level in LEVELS:
                agent = copy.deepcopy(base_agent)
                agent.traits[trait] = level
                state, _ = build_state(agent, runner.states[aid], population, scenario, runner.world, 1, seen[aid],
                                       runner.states, backend.state_char_budget)
                if extra_circle:
                    state["your_circle"] = extra_circle
                resp = await backend.decide(state, questions)
                raw = {q: a.probabilities for q, a in resp.answers.items()}
                ctx = engine_rules.context(agent, runner.states[aid], 1)
                ruled = {}
                for q, probs in raw.items():
                    parts = engine_rules.trait_shifts(scenario.decisions[q], ctx, runner.world)
                    ruled[q] = shift(probs, engine_rules.summarize_shifts(parts), scenario.trait_rules.strength)
                rows.append({"agent": aid, "trait": trait, "level": level, "probs": raw, "probs_rules": ruled})
    return rows


def sensitivity(rows: list[dict[str, Any]], key: str = "probs") -> dict[str, dict[str, dict[str, float]]]:
    """For each trait, question and option: mean change in probability from trait 0.1 to 0.9.
    key="probs" is the raw model; key="probs_rules" includes the engine's trait rules."""
    out: dict[str, dict[str, dict[str, list[float]]]] = {}
    by_key = {(r["agent"], r["trait"], r["level"]): r for r in rows}
    for (aid, trait, level), r in by_key.items():
        if level != LEVELS[0]:
            continue
        hi = by_key[(aid, trait, LEVELS[-1])]
        for q, probs in r[key].items():
            for opt, p in probs.items():
                out.setdefault(trait, {}).setdefault(q, {}).setdefault(opt, []).append(hi[key][q][opt] - p)
    return {t: {q: {o: round(sum(v) / len(v), 4) for o, v in opts.items()} for q, opts in qs.items()}
            for t, qs in out.items()}
