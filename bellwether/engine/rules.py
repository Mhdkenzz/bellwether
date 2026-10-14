"""Deterministic decision rules applied on top of the model's probabilities.

The model gives a prior over options; these rules make traits, money, stock and the
social circle move that prior in a known, testable way (log-space shifts), and remove
options the agent cannot actually take. Rules are domain-agnostic: they only use
option stances (act / delay / decline), signal polarities, prices and budgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..population import Agent
from ..scenario import DecisionSpec, Scenario
from .runstate import AgentState, World

# Logit-shift coefficients. A fully price-sensitive agent facing a price equal to all
# their spare money gets about -2.5 on "act", enough to overturn a 0.9 model prior.
PRICE_PRESSURE = 2.5
DISCOUNT_PULL = 4.0
SOCIAL_PULL = 2.0
OWNERSHIP_PULL = 1.0
RISK_PULL = 1.0
DELAY_CAUTION = 1.0
DELAY_UNCERTAINTY = 0.5
DECLINE_PRESSURE = 1.5
DECLINE_SOCIAL = 1.5
SIGNAL_SOCIAL = 1.0
DISAPPOINTMENT = 1.5
QUIET = 2.0


@dataclass
class Context:
    """What the rules know about one agent at decision time."""

    traits: dict[str, float]
    budget_left: float
    n_signals: int
    n_positive: int
    n_negative: int
    n_acquired: int
    disappointed: bool  # missed out or priced out last round
    sway: dict[str, float] = field(default_factory=dict)  # event nudges by stance / polarity

    @property
    def social(self) -> float:
        """Net tone of the circle, -1 (all warnings) .. +1 (all praise)."""
        return (self.n_positive - self.n_negative) / self.n_signals if self.n_signals else 0.0

    @property
    def volume(self) -> float:
        """How much the circle is talking, 0 .. 1 (saturates at 6 messages)."""
        return min(self.n_signals, 6) / 6


def context(agent: Agent, st: AgentState, round_: int) -> Context:
    last = st.outcome.get(round_ - 1, {})
    return Context(
        traits=agent.traits,
        budget_left=st.budget_left,
        n_signals=len(st.inbox),
        n_positive=sum(s.polarity == "positive" for s in st.inbox),
        n_negative=sum(s.polarity == "negative" for s in st.inbox),
        n_acquired=sum(s.acquired for s in st.inbox),
        disappointed=last.get("result") in ("missed_out", "priced_out"),
        sway=st.sway_now(round_),
    )


def option_stance(spec: DecisionSpec, option: str) -> str | None:
    opt = spec.options[option]
    if opt.stance:
        return opt.stance
    return "act" if opt.consume else None


def trait_shifts(spec: DecisionSpec, ctx: Context, world: World) -> dict[str, dict[str, float]]:
    """Per option, the named log-space shifts (kept separate so traces can explain them)."""
    t = ctx.traits
    ps, tf = t.get("price_sensitivity", 0.5), t.get("trend_following", 0.5)
    rt, si = t.get("risk_tolerance", 0.5), t.get("social_influence", 0.5)
    social = ctx.social * ctx.volume
    out: dict[str, dict[str, float]] = {}
    for key, opt in spec.options.items():
        parts: dict[str, float] = {}
        stance = option_stance(spec, key)
        item = world.items.get(opt.consume.item) if opt.consume else None
        pressure = min(item.price / max(ctx.budget_left, 1.0), 2.0) if item else 0.0
        discount = max(0.0, (item.initial_price - item.price) / item.initial_price) if item and item.initial_price else 0.0
        if stance == "act":
            parts["price"] = -PRICE_PRESSURE * ps * pressure
            parts["discount"] = DISCOUNT_PULL * ps * discount
            parts["social"] = SOCIAL_PULL * tf * social
            parts["owners"] = OWNERSHIP_PULL * tf * (ctx.n_acquired / ctx.n_signals if ctx.n_signals else 0.0)
            parts["risk"] = RISK_PULL * (rt - 0.5)
        elif stance == "delay":
            parts["caution"] = DELAY_CAUTION * (0.5 - rt)
            parts["uncertainty"] = DELAY_UNCERTAINTY * tf * (1 - ctx.volume)
        elif stance == "decline":
            # price pressure of the act options in the same decision
            acts = [world.items[o.consume.item] for o in spec.options.values() if o.consume and o.consume.item in world.items]
            if acts:
                parts["price"] = DECLINE_PRESSURE * ps * min(acts[0].price / max(ctx.budget_left, 1.0), 2.0)
            parts["social"] = -DECLINE_SOCIAL * tf * social
        if spec.role == "signal":
            pol = opt.signal
            if pol == "positive":
                parts["social"] = SIGNAL_SOCIAL * tf * social
                parts["disappointed"] = -DISAPPOINTMENT * ctx.disappointed
            elif pol == "negative":
                parts["social"] = -SIGNAL_SOCIAL * tf * social
                parts["disappointed"] = DISAPPOINTMENT * ctx.disappointed
            elif pol == "none":
                parts["quiet"] = QUIET * (0.5 - si)
        nudge = ctx.sway.get(opt.signal) if spec.role == "signal" else ctx.sway.get(stance or "")
        if nudge:
            parts["event"] = nudge
        out[key] = {k: round(v, 4) for k, v in parts.items() if abs(v) > 1e-9}
    return out


def blocked_options(spec: DecisionSpec, scenario: Scenario, world: World, st: AgentState) -> dict[str, str]:
    """Options the agent cannot take, with the reason ('sold_out', 'priced_out', 'already_owned')."""
    out = {}
    for key, opt in spec.options.items():
        if not opt.consume:
            continue
        item = world.items.get(opt.consume.item)
        if item is None:
            continue
        if st.holdings.get(opt.consume.item, 0) >= scenario.items[opt.consume.item].max_per_agent:
            out[key] = "already_owned"
        elif item.stock is not None and item.stock <= 1e-9:
            out[key] = "sold_out"
        elif item.price * opt.consume.qty > st.budget_left + 1e-9:
            out[key] = "priced_out"
    return out


def summarize_shifts(shifts: dict[str, dict[str, float]]) -> dict[str, float]:
    return {k: round(sum(v.values()), 4) for k, v in shifts.items()}


def describe(shifts: dict[str, dict[str, float]]) -> dict[str, Any]:
    return {k: v for k, v in shifts.items() if v}
