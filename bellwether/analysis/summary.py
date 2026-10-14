"""Aggregate runs across seeds: per-arm spreads, paired deltas vs baseline, segment breakdowns."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from ..engine.metrics import latest
from ..engine.run import RunResult
from ..engine.runstate import AgentState
from ..population import Population
from ..scenario import Scenario


def _quantile(xs: list[float], q: float) -> float:
    if len(xs) == 1:
        return xs[0]
    s = sorted(xs)
    pos = q * (len(s) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def describe(values: list[Any]) -> dict[str, Any]:
    vals = [v for v in values if v is not None and not isinstance(v, str)]
    if not vals:
        return {"n": 0}
    if all(isinstance(v, bool) for v in vals):
        hits = sum(vals)
        return {"kind": "bool", "n": len(vals), "true": hits, "frequency": round(hits / len(vals), 4)}
    nums = [float(v) for v in vals]
    return {
        "kind": "number",
        "n": len(nums),
        "mean": round(statistics.fmean(nums), 4),
        "p10": round(_quantile(nums, 0.1), 4),
        "p90": round(_quantile(nums, 0.9), 4),
        "min": round(min(nums), 4),
        "max": round(max(nums), 4),
    }


def segment_breakdown(result: RunResult, population: Population, scenario: Scenario) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for a in population.agents:
        groups["all"].append(a.id)
        for s in a.segments:
            groups[f"segment:{s}"].append(a.id)
        if a.cohort:
            groups[f"cohort:{a.cohort}"].append(a.id)
    out = {}
    for name, ids in groups.items():
        row: dict[str, Any] = {"agents": len(ids)}
        row["acquired_share"] = round(sum(1 for i in ids if any(result.agents[i]["holdings"].values())) / len(ids), 4)
        sents = [result.agents[i]["sentiment"] for i in ids if result.agents[i]["sentiment"] is not None]
        row["mean_sentiment"] = round(statistics.fmean(sents), 4) if sents else None
        for qid, spec in scenario.decisions.items():
            if spec.type != "choice":
                continue
            finals = []
            for i in ids:
                st = AgentState(choices={int(k): v for k, v in result.agents[i]["choices"].items()})
                c = latest(st, qid)
                if c:
                    finals.append(c)
            if finals:
                row[qid] = {o: round(finals.count(o) / len(finals), 4) for o in spec.options}
        out[name] = row
    return out


def summarize(results: list[RunResult], population: Population, scenario: Scenario) -> dict[str, Any]:
    by_arm: dict[str, list[RunResult]] = defaultdict(list)
    for r in results:
        by_arm[r.arm].append(r)

    arms: dict[str, Any] = {}
    for arm, runs in by_arm.items():
        keys = sorted({k for r in runs for k in r.metrics})
        arms[arm] = {
            "runs": len(runs),
            "metrics": {k: describe([r.metrics.get(k) for r in runs]) for k in keys},
            "segments": _mean_segments([segment_breakdown(r, population, scenario) for r in runs]),
            "calls": sum(r.calls for r in runs),
            "cached": sum(r.cached for r in runs),
            "errors": sum(r.errors for r in runs),
            "cost": round(sum(r.cost for r in runs), 6),
        }

    deltas: dict[str, Any] = {}
    base = {r.run_index: r for r in by_arm.get("baseline", [])}
    for arm, runs in by_arm.items():
        if arm == "baseline" or not base:
            continue
        paired = [(r, base[r.run_index]) for r in runs if r.run_index in base]
        out = {}
        for k in sorted({k for r, _ in paired for k in r.metrics}):
            vals = [(r.metrics.get(k), b.metrics.get(k)) for r, b in paired]
            if all(isinstance(v, bool) and isinstance(w, bool) for v, w in vals):
                out[k] = {"kind": "bool", "variant": sum(v for v, _ in vals), "baseline": sum(w for _, w in vals),
                          "n": len(vals)}
            elif all(isinstance(v, (int, float)) and isinstance(w, (int, float)) for v, w in vals):
                out[k] = describe([float(v) - float(w) for v, w in vals])
        deltas[arm] = out
    return {"arms": arms, "deltas": deltas}


def _mean_segments(per_run: list[dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    if len(per_run) == 1:
        return per_run[0]
    out: dict[str, dict[str, Any]] = {}
    for seg in per_run[0]:
        rows = [r[seg] for r in per_run if seg in r]
        merged: dict[str, Any] = {"agents": rows[0]["agents"]}
        for key in ("acquired_share", "mean_sentiment"):
            vals = [r[key] for r in rows if r.get(key) is not None]
            merged[key] = round(statistics.fmean(vals), 4) if vals else None
        for key, val in rows[0].items():
            if isinstance(val, dict):
                merged[key] = {o: round(statistics.fmean(r[key][o] for r in rows if key in r), 4) for o in val}
        out[seg] = merged
    return out
