"""Built-in and scenario-declared metrics for one finished run."""

from __future__ import annotations

from typing import Any

from ..expr import evaluate
from ..population import Population
from ..scenario import Scenario
from .runstate import AgentState, World


def latest(ast: AgentState, decision: str, kind: str = "choices") -> Any:
    table = ast.choices if kind == "choices" else ast.scores
    for r in sorted(table, reverse=True):
        if decision in table[r]:
            return table[r][decision]
    return None


def compute_metrics(
    population: Population, scenario: Scenario, world: World, states: dict[str, AgentState], weight: float
) -> dict[str, Any]:
    ids = [a.id for a in population.agents]

    def answered(decision: str, round_: int | None) -> list[tuple[str, Any]]:
        out = []
        for aid in ids:
            st = states[aid]
            if round_ is None:
                v = latest(st, decision)
            else:
                v = st.choices.get(round_, {}).get(decision)
            if v is not None:
                out.append((aid, v))
        return out

    def count(decision: str, option: str, round: int | None = None) -> float:
        return weight * sum(1 for _, v in answered(decision, round) if v == option)

    def share(decision: str, option: str, round: int | None = None) -> float:
        rows = answered(decision, round)
        return sum(1 for _, v in rows if v == option) / len(rows) if rows else 0.0

    def ever(decision: str, option: str) -> float:
        return weight * sum(1 for aid in ids if any(c.get(decision) == option for c in states[aid].choices.values()))

    def mean_score(decision: str, round: int | None = None) -> float:
        vals = []
        for aid in ids:
            st = states[aid]
            v = latest(st, decision, "scores") if round is None else st.scores.get(round, {}).get(decision)
            if v is not None:
                vals.append(v)
        return sum(vals) / len(vals) if vals else 0.0

    def flag_count(flag: str) -> float:
        return weight * sum(1 for aid in ids if flag in states[aid].flags)

    items = {}
    for name, it in world.items.items():
        items[name] = {
            "price": it.price,
            "initial_price": it.initial_price,
            "stock_left": it.stock,
            "initial_stock": it.initial_stock,
            "sold": round(it.sold, 3),
            "sold_out": bool(it.initial_stock is not None and it.stock is not None and it.stock <= 1e-9),
            "missed_out": round(it.missed_out, 3),
            "priced_out": round(it.priced_out, 3),
            "demand": round(it.sold + it.missed_out, 3),
            "sell_through": round(it.sold / it.initial_stock, 4) if it.initial_stock else None,
        }

    metrics: dict[str, Any] = {}
    for name, m in items.items():
        for k in ("sold", "sell_through", "sold_out", "missed_out", "priced_out", "demand"):
            metrics[f"{name}.{k}"] = m[k]
    for dname, spec in scenario.decisions.items():
        if spec.type == "choice":
            for opt in spec.options:
                metrics[f"{dname}.{opt}.share"] = round(share(dname, opt), 4)
        else:
            metrics[f"{dname}.mean"] = round(mean_score(dname), 4)

    env = {"items": items, "market_size": weight * len(ids), "agents": len(ids), "weight": weight,
           "rounds": scenario.rounds}
    funcs = {"count": count, "share": share, "ever": ever, "mean_score": mean_score, "flag_count": flag_count}
    for name, expr in scenario.metrics.items():
        try:
            v = evaluate(expr, env, funcs)
            metrics[name] = round(v, 4) if isinstance(v, float) else v
        except Exception as e:  # a bad metric should not lose the run
            metrics[name] = f"error: {e}"
    return metrics
