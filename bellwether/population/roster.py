"""docs/all-agents.md: every written person in one readable file, grouped by community and laid out by
the 10 description groups. Rebuilt with `python -m bellwether roster`; a test fails if it's out of date.
"""

from __future__ import annotations

from ..settings import POPULATION_CONFIG_DIR, ROOT
from .categories import CATEGORY_GROUPS
from .config import load_population_config
from .handmade import build_handmade
from .models import Agent, Population

ROSTER_PATH = ROOT / "docs" / "all-agents.md"


def _value(v) -> str:
    if isinstance(v, dict):
        return ", ".join(f"{k.replace('_', ' ')} {x:.2f}" for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(map(str, v)) if v else "none"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _person(a: Agent, pop: Population) -> list[str]:
    head = f"### {a.name}, {a.age} - {a.occupation}" + (f" ({a.cohort_label})" if a.cohort_label else "")
    lines = [head, ""]
    for group, cats in CATEGORY_GROUPS.items():
        parts = [f"{label}: {_value(getattr(a, field))}" for label, field in cats.items() if field != "name"]
        lines.append(f"- **{group}** - " + " · ".join(parts))
    ties: dict[str, list[str]] = {}
    for other, t in pop.neighbors(a.id):
        ties.setdefault(t.label, []).append(pop.agent(other).name)
    who = "; ".join(f"{label}: {', '.join(sorted(names))}" for label, names in sorted(ties.items()))
    lines += [f"- **Knows** - {who or 'nobody yet'}", ""]
    return lines


def render_roster() -> tuple[str, int]:
    pops = []
    for path in sorted(POPULATION_CONFIG_DIR.glob("*.yaml")):
        cfg = load_population_config(path)
        if cfg.agents and not cfg.include:
            pops.append(build_handmade(cfg))
    total = sum(p.size for p in pops)
    out = ["# All agents", "",
           f"Every written person ({total}), generated from `configs/populations/*.yaml` by "
           "`python -m bellwether roster`. Don't edit this file; edit the YAML and rebuild it.", ""]
    out += [f"- [{p.name}](#{p.name}) - {p.size} people: {p.config.description}" for p in pops] + [""]
    for p in pops:
        out += [f"## {p.name}", "", p.config.description, ""]
        for a in p.agents:
            out += _person(a, p)
    return "\n".join(out).rstrip() + "\n", total


def write_roster() -> int:
    text, total = render_roster()
    ROSTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROSTER_PATH.write_text(text)
    return total
