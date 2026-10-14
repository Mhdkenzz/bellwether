"""Write a generated population into its YAML file as written people (`agents:`), so every person,
friend group, family link and acquaintance is in the file and can be read and edited by hand.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from . import pools
from .handmade import HandAgent
from .models import Agent, Population

STUDENT_COHORTS = ("junior", "senior")


def _inputs(a: Agent) -> tuple[float, float]:
    """The situation's stress and mood that, with their Big Five, give the agent's baselines."""
    b5 = a.big_five
    stress = next((s for c, s, _ in pools.LIFE_CONTEXT if c == a.life_context), None)
    if stress is None:
        stress = min(1.0, a.stress_baseline / (0.6 + 0.8 * b5["neuroticism"]))
    mood = a.mood_baseline - (0.35 * (b5["extraversion"] - 0.5) - 0.45 * (b5["neuroticism"] - 0.5))
    return round(stress, 3), round(max(-1.0, min(1.0, mood)), 3)


def to_written(pop: Population) -> list[dict]:
    """One dict per person in HandAgent field order. Ties become group / family / close_to / knows."""
    by_id = {a.id: a for a in pop.agents}
    family: dict[str, list[str]] = {a.id: [] for a in pop.agents}
    close: dict[str, list[str]] = {a.id: [] for a in pop.agents}
    knows: dict[str, list[str]] = {a.id: [] for a in pop.agents}

    # a relative is linked to one student: the first they share a "family" tie with, strong ties first
    linked: set[tuple[str, str]] = set()
    for a in pop.agents:
        if a.cohort != "family":
            continue
        options = sorted(((t.kind != "strong", o) for o, t in pop.neighbors(a.id)
                          if t.label == "family" and by_id[o].cohort in STUDENT_COHORTS))
        if options:
            other = options[0][1]
            family[a.id].append(by_id[other].name)
            linked.add(tuple(sorted((a.id, other))))
    for t in pop.ties:
        if tuple(sorted((t.a, t.b))) in linked:
            continue
        x, y = by_id[t.a], by_id[t.b]
        if t.kind == "strong" and x.group != y.group:
            close[t.a].append(y.name)
        elif t.kind == "weak":
            knows[t.a].append(y.name)

    out = []
    for a in pop.agents:
        stress, mood = _inputs(a)
        d = {
            "name": a.name, "age": a.age, "cohort": a.cohort, "life_stage": a.life_stage,
            "occupation": a.occupation, "location": a.location, "income": a.income, "budget": a.budget,
            "traits": dict(a.traits), "big_five": dict(a.big_five), "chronotype": a.chronotype,
            "temperament": a.temperament, "stress": stress, "mood": mood,
            "group": a.group, "family": family[a.id], "close_to": close[a.id], "knows": knows[a.id],
        }
        for field in HandAgent.model_fields:
            if field not in d:
                d[field] = getattr(a, field)
        ordered = {f: d[f] for f in HandAgent.model_fields if f in d}
        if ordered["cohort"] is None:
            del ordered["cohort"]
        for key in ("family", "close_to", "knows"):
            if not ordered[key]:
                del ordered[key]
        HandAgent.model_validate(ordered)  # what gets written must load back
        out.append(ordered)
    return out


class _Dumper(yaml.SafeDumper):
    pass


def _dump(people: list[dict]) -> str:
    text = yaml.dump(people, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=110,
                     default_flow_style=None)
    return "".join("    " + line if line.strip() else line for line in text.splitlines(keepends=True))


def write_agents(path: Path, people: list[dict], note: str) -> None:
    """Append an `agents:` list to a population file (its sampling settings stay as they are)."""
    text = path.read_text()
    if "\n  agents:" in text:
        raise ValueError(f"{path.name} already has written people")
    block = (f"\n  # {note} ({date.today().isoformat()}). These people are what runs use;\n"
             "  # the settings above only matter when generating new people. Edit freely; see guide.md.\n"
             "  agents:\n" + _dump(people))
    path.write_text(text.rstrip("\n") + "\n" + block)
