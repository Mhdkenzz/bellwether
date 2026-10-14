"""Several communities run as one society (`include:` in a population config, e.g. `all.yaml`).

Each community keeps its own people, friend groups and family exactly as written. Communities are not
linked to each other (different schools, a general panel), so they only meet through public posts.
"""

from __future__ import annotations

from ..settings import POPULATION_CONFIG_DIR
from .config import PopulationConfig, load_population_config
from .handmade import build_handmade
from .mix import plan_counts
from .models import Population, Tie


def communities(cfg: PopulationConfig) -> list[PopulationConfig]:
    """The population configs a combined config includes, in order. "*" = every file with written people."""
    names = cfg.include or []
    if names == ["*"]:
        names = []
        for path in sorted(POPULATION_CONFIG_DIR.glob("*.yaml")):
            other = load_population_config(path)
            if other.agents and not other.include and other.name != cfg.name:
                names.append(path.stem)
    out = []
    for name in names:
        path = POPULATION_CONFIG_DIR / f"{name}.yaml"
        if not path.exists():
            raise ValueError(f"{cfg.name}: no population file {name!r}")
        part = load_population_config(path)
        if not part.agents:
            raise ValueError(f"{name} has no written people; write them first (python -m bellwether export {name})")
        out.append(part)
    if not out:
        raise ValueError(f"{cfg.name}: nothing to include")
    return out


def available(cfg: PopulationConfig) -> dict[str, int]:
    """Written people per community."""
    return {part.name: len(part.agents or []) for part in communities(cfg)}


def combine(cfg: PopulationConfig, size: int | None = None, seed: int | None = None,
            mix: dict[str, float] | None = None) -> Population:
    seed = cfg.seed if seed is None else seed
    parts = communities(cfg)
    counts = plan_counts({p.name: len(p.agents or []) for p in parts}, size, mix)
    built = [build_handmade(p, size=counts[p.name]) for p in parts if counts[p.name]]
    platforms = {p.name: p.social_media for p in parts}
    if len({m.model_dump_json() for m in platforms.values()}) > 1:
        raise ValueError("communities run together must use the same social platforms")

    seen: dict[str, str] = {}
    for pop in built:
        for a in pop.agents:
            if a.name in seen:
                raise ValueError(f"{a.name} is in both {seen[a.name]} and {pop.name}; names must be unique "
                                 "across communities that run together")
            seen[a.name] = pop.name

    agents, ties = [], []
    for pop in built:  # renumber so ids stay unique, keeping every tie
        new_id = {a.id: f"a{len(agents) + i + 1:03d}" for i, a in enumerate(pop.agents)}
        for a in pop.agents:
            agents.append(a.model_copy(update={"id": new_id[a.id], "group": f"{pop.name}:{a.group}"}))
        ties += [Tie(a=new_id[t.a], b=new_id[t.b], kind=t.kind, label=t.label, weight=t.weight) for t in pop.ties]

    natural = mix is None and size in (None, sum(len(p.agents or []) for p in parts))
    name = cfg.name if natural else f"{cfg.name}-" + "-".join(f"{p.name}{len(p.agents)}" for p in built)
    merged = cfg.model_copy(update={
        "size": len(agents), "seed": seed, "social_media": parts[0].social_media,
        "min_trait_distance": 0.0,  # each community is already checked; strangers may happen to be alike
    })
    return Population(name=name, seed=seed, config=merged, agents=agents, ties=ties)
