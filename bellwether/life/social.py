"""Meeting people and being online: gatherings, conversations, posts and feeds.

Everything here is deterministic given the run's seed. Influence is explicit:
strength = speaker sway (social influence) x closeness (affinity) x listener susceptibility
x channel weight (face to face 1.0; platforms per config).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from ..population import Population
from .config import Activity


@dataclass
class Gathering:
    id: str
    kind: str  # friends | household | colleagues | online_friends | alone
    place: str
    members: list[str]
    topic: str = "everyday life"
    influences: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "place": self.place, "members": self.members,
                "topic": self.topic, "influences": self.influences}


@dataclass
class Post:
    id: str
    author: str
    platform: str
    day: int
    slot: str
    stance: str | None  # positive | neutral | negative | None (life update)


def _components(members: list[str], population: Population, allow_weak: bool) -> list[list[str]]:
    pool = set(members)
    seen: set[str] = set()
    comps = []
    for m in sorted(members):
        if m in seen:
            continue
        comp, stack = [], [m]
        seen.add(m)
        while stack:
            x = stack.pop()
            comp.append(x)
            for other, tie in population.neighbors(x):
                if other in pool and other not in seen and (allow_weak or tie.kind == "strong"):
                    seen.add(other)
                    stack.append(other)
        comps.append(sorted(comp))
    return comps


def _split(group: list[str], rng: random.Random, max_size: int = 6) -> list[list[str]]:
    if len(group) <= max_size:
        return [group]
    g = group[:]
    rng.shuffle(g)
    n = -(-len(g) // max_size)
    return [sorted(g[i::n]) for i in range(n)]


def form_gatherings(choices: dict[str, Activity], population: Population, rng: random.Random,
                    slot: str, day: int) -> list[Gathering]:
    """Who ends up together this slot, given everyone's chosen activity."""
    out: list[Gathering] = []
    by_kind: dict[str, list[str]] = {}
    for aid, act in sorted(choices.items()):
        by_kind.setdefault(act.social or "alone", []).append(aid)

    def add(kind: str, place: str, members: list[str]) -> None:
        out.append(Gathering(id=f"d{day}-{slot}-{len(out) + 1}", kind=kind, place=place, members=members))

    for kind in ("friends", "online_friends"):
        members = by_kind.get(kind, [])
        for comp in _components(members, population, allow_weak=True):
            for g in _split(comp, rng):
                place = "online" if kind == "online_friends" else choices[g[0]].place
                add(kind, place, g)
    # family: only family-labelled ties who both chose family time meet each other
    hh = by_kind.get("household", [])
    hh_set, used = set(hh), set()
    for aid in hh:
        if aid in used:
            continue
        fam = [o for o, t in population.neighbors(aid) if o in hh_set and o not in used and t.label == "family"]
        group = sorted({aid, *fam})
        used.update(group)
        add("household", "home", group)
    # colleagues/classmates: grouped by place, friends first, leftovers paired with whoever is there
    col = by_kind.get("colleagues", [])
    by_place: dict[str, list[str]] = {}
    for aid in col:
        by_place.setdefault(choices[aid].place, []).append(aid)
    for place, members in sorted(by_place.items()):
        comps = _components(members, population, allow_weak=True)
        singles = [c[0] for c in comps if len(c) == 1]
        for comp in comps:
            if len(comp) > 1:
                for g in _split(comp, rng):
                    add("colleagues", place, g)
        rng.shuffle(singles)
        for i in range(0, len(singles) - 1, 2):
            add("colleagues", place, sorted(singles[i:i + 2]))
        if len(singles) % 2:
            add("alone", place, [singles[-1]])
    for aid in by_kind.get("alone", []):
        add("alone", choices[aid].place, [aid])
    return out


def influence_strength(population: Population, speaker: str, listener: str, affinity: float,
                       channel_weight: float = 1.0) -> float:
    s, li = population.agent(speaker), population.agent(listener)
    return round((0.4 + 0.6 * s.traits["social_influence"]) * (0.5 + 0.5 * affinity)
                 * (0.5 + li.susceptibility) * channel_weight, 3)


def talkativeness(population: Population, aid: str) -> float:
    return 0.3 + 0.6 * population.agent(aid).big_five.get("extraversion", 0.5)


def feed_for(viewer: str, posts: list[Post], population: Population, rng: random.Random,
             limit: int = 4) -> list[Post]:
    """Posts a viewer sees: followers (ties), group chats (close ties) or the algorithm (anyone)."""
    me = population.agent(viewer)
    platforms = population.config.social_media.platforms
    ties = {o: t for o, t in population.neighbors(viewer)}
    seen = []
    for p in posts:
        if p.author == viewer or p.platform not in me.platforms:
            continue
        spec = platforms[p.platform]
        author = population.agent(p.author)
        if spec.reach == "followers" and p.author in ties:
            seen.append(p)
        elif spec.reach == "group" and p.author in ties and ties[p.author].kind == "strong":
            seen.append(p)
        elif spec.reach == "algorithmic" and rng.random() < 0.25 + 0.6 * author.traits["social_influence"]:
            seen.append(p)
    rng.shuffle(seen)
    return seen[:limit]
