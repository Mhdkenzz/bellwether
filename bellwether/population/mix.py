"""How many people to take from each part of a population (a community or a cohort) for a run.

The natural mix keeps every part at its real size, so running everyone is the most accurate choice:
the biggest sample with nothing over- or under-represented. A custom mix (e.g. more students, fewer
parents) is allowed, but it can never ask for more people than are written for a part.
"""

from __future__ import annotations

import math

from .sampler import allocate


def parse_mix(text: str | None, parts: list[str]) -> dict[str, float] | None:
    """'25:27:38' (in the order of `parts`) or 'school-circle=50,general-panel=50'; blank means natural."""
    text = (text or "").strip().replace("%", "")
    if not text:
        return None
    if "=" in text:
        out: dict[str, float] = {}
        for item in text.split(","):
            name, _, value = item.partition("=")
            out[name.strip()] = float(value)
        return out
    values = [float(v) for v in text.replace(",", ":").split(":") if v.strip()]
    if len(values) != len(parts):
        raise ValueError(f"give {len(parts)} numbers ({':'.join(parts)}), got {len(values)}")
    return dict(zip(parts, values))


def plan_counts(available: dict[str, int], size: int | None = None,
                mix: dict[str, float] | None = None) -> dict[str, int]:
    """People per part. No size means everyone (natural mix) or the most the mix allows."""
    if mix is None:
        weights = {k: float(v) for k, v in available.items()}
    else:
        unknown = set(mix) - set(available)
        if unknown:
            raise ValueError(f"unknown parts in mix: {sorted(unknown)}; choose from {sorted(available)}")
        if any(v < 0 for v in mix.values()) or not sum(mix.values()):
            raise ValueError("mix values must be positive")
        weights = {k: float(mix.get(k, 0)) for k in available}
    total = sum(weights.values())
    if not total:
        raise ValueError("there are no people to run")
    shares = {k: w / total for k, w in weights.items()}
    most = min(math.floor(available[k] / s + 1e-9) for k, s in shares.items() if s > 0)
    if size is None:
        size = most if mix is not None else sum(available.values())
    if size > sum(available.values()):
        raise ValueError(f"asked for {size} people but only {sum(available.values())} are written")
    counts = dict(zip(shares, allocate(size, list(shares.values()))))
    short = [f"{k} needs {counts[k]} but has {available[k]}" for k in counts if counts[k] > available[k]]
    if short:
        raise ValueError(f"not enough people for that mix ({'; '.join(short)}); "
                         f"at this mix the most you can run is {most}")
    return counts
