"""Render an agent's fixed persona and trait descriptions as compact text."""

from __future__ import annotations

from .config import PopulationConfig
from .models import Agent
from .pools import TRAIT_LADDERS


def trait_level(value: float) -> int:
    """Map a 0-1 trait value to one of 5 levels."""
    return min(4, int(value * 5))


def describe_trait(name: str, value: float, cfg: PopulationConfig) -> str:
    ladder = cfg.trait_words.get(name) or TRAIT_LADDERS.get(name)
    if ladder:
        return ladder[trait_level(value)]
    word = ["very low", "low", "moderate", "high", "very high"][trait_level(value)]
    return f"{word} {name.replace('_', ' ')}"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def render_persona(agent: Agent, cfg: PopulationConfig) -> str:
    role = agent.occupation
    if agent.cohort_label:
        role = f"{role} ({agent.cohort_label})"
    money = f"{cfg.currency_symbol}{agent.budget:.0f}"
    return (
        f"{agent.name}, {agent.age}, {role}, {agent.location}. "
        f"{agent.income.capitalize()} income, about {money} {cfg.budget_label}. "
        f"Into {_join(agent.interests)}. Values {_join(agent.values)}. "
        f"{agent.shopping_style.capitalize()}; {agent.media_habit}; {agent.decision_style}. "
        f"Quirk: {agent.quirk}."
    )
