"""Build the state one agent sees in one round, trimmed to the backend's size budget."""

from __future__ import annotations

import json
from typing import Any

from ..population import Agent, Population, describe_trait
from ..scenario import Scenario
from .runstate import AgentState, World
from .social import render_memory, select_inbox


def _money(symbol: str, x: float) -> str:
    return f"{symbol}{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{symbol}{x:,.2f}"


def describe_traits(agent: Agent, population: Population, scenario: Scenario) -> dict[str, str]:
    out = {}
    for name, value in agent.traits.items():
        line = f"{value:.2f}: {describe_trait(name, value, population.config)}"
        if name in scenario.trait_context:
            line += f". Here: {scenario.trait_context[name]}"
        out[name] = line
    return out


def world_lines(agent: Agent, ast: AgentState, world: World, scenario: Scenario, round_: int) -> list[str]:
    sym = scenario.currency_symbol
    lines = [f"{'Day' if scenario.life else 'Round'} {round_} of {scenario.rounds}."]
    for name, item in world.items.items():
        price = _money(sym, item.price)
        if item.price != item.initial_price:
            price += f" (was {_money(sym, item.initial_price)})"
        line = f"{item.label}: {price}"
        if scenario.show_stock and item.stock is not None and item.initial_stock:
            left = max(0, round(item.stock))
            line += f"; {left} of {round(item.initial_stock)} left" if left else "; sold out"
        if ast.holdings.get(name):
            line += "; they already have one"
        lines.append(line + ".")
    if world.items:
        lines.append(f"They have about {_money(sym, ast.budget_left)} to spare.")
    return lines


def hard_facts(ast: AgentState, world: World, scenario: Scenario) -> list[str]:
    """Plain, unmissable constraints. Models must never contradict these."""
    sym = scenario.currency_symbol
    facts = []
    for name, item in world.items.items():
        if ast.holdings.get(name):
            facts.append(f"They already own the {item.label}; they would not buy another.")
        elif item.stock is not None and item.stock <= 1e-9:
            facts.append(f"The {item.label} is SOLD OUT. Nobody can buy it any more.")
        elif item.price > ast.budget_left + 1e-9:
            facts.append(f"They CANNOT afford the {item.label}: it costs {_money(sym, item.price)} and they only have "
                         f"{_money(sym, ast.budget_left)}. Buying it is impossible.")
        else:
            share = item.price / ast.budget_left if ast.budget_left else 1.0
            facts.append(f"They can afford the {item.label} ({_money(sym, item.price)}), but it would use "
                         f"{share:.0%} of the {_money(sym, ast.budget_left)} they have left.")
    return facts


def crowd_line(agent_id: str, population: Population, states: dict[str, AgentState]) -> str | None:
    """Share of the agent's direct ties who own any scenario item."""
    ties = population.neighbors(agent_id)
    if not ties:
        return None
    owners = sum(1 for other, _ in ties if any(states[other].holdings.values()))
    return f"{owners} of the {len(ties)} people they know already got one."


def build_state(
    agent: Agent,
    ast: AgentState,
    population: Population,
    scenario: Scenario,
    world: World,
    round_: int,
    events_seen: list[str],
    states: dict[str, AgentState],
    char_budget: int,
    extra: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (state, meta). Trims memory first, then circle signals, to fit `char_budget`."""
    circle, tally, shown = select_inbox(ast.inbox, agent.traits["trend_following"], population, scenario.signal_text)
    memory = render_memory(ast.memory, unit="Day" if scenario.life else "Round")

    def assemble() -> dict[str, Any]:
        state: dict[str, Any] = {
            "person": agent.profile if agent.profile and char_budget >= 4000 else agent.persona,
            "traits": describe_traits(agent, population, scenario),
            "situation": scenario.context,
            "now": world_lines(agent, ast, world, scenario, round_),
        }
        if extra:
            state.update(extra)
        facts = hard_facts(ast, world, scenario) + list((extra or {}).get("hard_facts", []))
        if facts:
            state["hard_facts"] = facts
        if events_seen:
            state["just_happened"] = events_seen
        if circle or tally:
            state["your_circle"] = circle + ([tally] if tally else [])
        if scenario.crowd_stats:
            line = crowd_line(agent.id, population, states)
            if line:
                state["crowd"] = line
        if memory:
            state["your_memory"] = memory
        return state

    trimmed = {"memory": 0, "circle": 0}
    state = assemble()
    while len(json.dumps(state, ensure_ascii=False)) > char_budget:
        if memory:
            memory.pop(0)
            trimmed["memory"] += 1
        elif circle:
            circle.pop()
            trimmed["circle"] += 1
        else:
            break
        state = assemble()
    meta = {
        "chars": len(json.dumps(state, ensure_ascii=False)),
        "trimmed": trimmed,
        "signals_shown": [s.sender for s in shown],
        "signals_received": len(ast.inbox),
    }
    return state, meta
