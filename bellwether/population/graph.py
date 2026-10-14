"""Social graph: tight groups (strong ties) plus a few weak ties between groups."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import TYPE_CHECKING

from .models import Agent, Tie

if TYPE_CHECKING:
    from .config import PopulationConfig

STRONG_WEIGHT = 1.0
WEAK_WEIGHT = 0.4


def group_sizes(n: int, lo: int, hi: int, rng: random.Random) -> list[int]:
    """Random group sizes within [lo, hi] that sum to n (one smaller group only if n < lo)."""
    sizes: list[int] = []
    remaining = n
    while remaining > hi:
        upper = min(hi, remaining - lo)
        if upper < lo:  # can't leave a valid remainder; split what's left in two
            half = remaining // 2
            sizes += [half, remaining - half]
            return sizes
        k = rng.randint(lo, upper)
        sizes.append(k)
        remaining -= k
    if remaining:
        sizes.append(remaining)
    return sizes


def _chunk(ids: list[str], lo: int, hi: int, rng: random.Random) -> list[list[str]]:
    groups, i = [], 0
    for k in group_sizes(len(ids), lo, hi, rng):
        groups.append(ids[i : i + k])
        i += k
    return groups


def _label(a: Agent, b: Agent, default: str, cfg: "PopulationConfig") -> str:
    if a.cohort and b.cohort and a.cohort != b.cohort:
        key = "|".join(sorted((a.cohort, b.cohort)))
        return cfg.groups.cross_cohort_labels.get(key, default)
    return default


def build_ties(agents: list[Agent], cfg: "PopulationConfig", rng: random.Random) -> list[Tie]:
    gcfg = cfg.groups
    lo, hi = gcfg.size
    by_cohort: dict[str, list[str]] = defaultdict(list)
    for a in agents:
        by_cohort[a.cohort or ""].append(a.id)

    groups: list[list[str]] = []
    for cohort in sorted(by_cohort):
        ids = by_cohort[cohort][:]
        rng.shuffle(ids)
        groups += _chunk(ids, lo, hi, rng)

    # Mix cohorts: each agent has a (1 - same_cohort) chance of swapping into another group.
    if len(groups) > 1 and gcfg.same_cohort < 1:
        where = {aid: gi for gi, g in enumerate(groups) for aid in g}
        for aid in sorted(where):
            if rng.random() >= gcfg.same_cohort:
                gi = where[aid]
                gj = rng.choice([j for j in range(len(groups)) if j != gi])
                other = rng.choice(groups[gj])
                groups[gi][groups[gi].index(aid)] = other
                groups[gj][groups[gj].index(other)] = aid
                where[aid], where[other] = gj, gi

    by_id = {a.id: a for a in agents}
    ties: list[Tie] = []
    seen: set[tuple[str, str]] = set()
    for gi, group in enumerate(groups):
        name = f"g{gi + 1:02d}"
        for aid in group:
            by_id[aid].group = name
        for x in range(len(group)):
            for y in range(x + 1, len(group)):
                a, b = sorted((group[x], group[y]))
                seen.add((a, b))
                ties.append(Tie(a=a, b=b, kind="strong", label=_label(by_id[a], by_id[b], gcfg.strong_label, cfg),
                                weight=STRONG_WEIGHT))

    ids = [a.id for a in agents]
    for aid in ids:
        candidates = [o for o in ids if o != aid and by_id[o].group != by_id[aid].group]
        rng.shuffle(candidates)
        added = 0
        for other in candidates:
            if added >= gcfg.weak_ties_per_agent:
                break
            a, b = sorted((aid, other))
            if (a, b) in seen:
                continue
            seen.add((a, b))
            ties.append(Tie(a=a, b=b, kind="weak", label=_label(by_id[a], by_id[b], gcfg.weak_label, cfg),
                            weight=WEAK_WEIGHT))
            added += 1
    return ties
