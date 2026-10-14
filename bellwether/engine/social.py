"""Signals between agents, inbox selection and memory rendering.

Traits shape the input each agent receives:
- `social_influence` of the sender sets how far a signal travels (weak-tie reach)
  and how much attention it wins in a receiver's inbox.
- `trend_following` of the receiver sets how many signals they take in each round.
"""

from __future__ import annotations

import random

from ..population import Population
from ..scenario import SignalText
from .runstate import MemoryEntry, Signal

MEMORY_LINES = 8


def inbox_capacity(trend_following: float) -> int:
    """2 signals for an independent person, up to 8 for a strong trend follower."""
    return 2 + round(6 * trend_following)


def signal_priority(sig: Signal, population: Population) -> float:
    return sig.weight * (0.5 + population.agent(sig.sender).traits["social_influence"])


def deliver(
    population: Population,
    sender: str,
    round_: int,
    polarity: str,
    acquired: bool,
    missed_out: bool,
    sentiment: float | None,
    rng: random.Random,
) -> list[Signal]:
    """Signals from one sender to neighbours. Strong ties always hear; weak ties hear with
    probability equal to the sender's social influence."""
    if polarity == "none" and not acquired and not missed_out:
        return []
    influence = population.agent(sender).traits["social_influence"]
    out = []
    for other, tie in population.neighbors(sender):
        if tie.kind == "weak" and rng.random() >= influence:
            continue
        out.append(Signal(sender=sender, receiver=other, round=round_, polarity=polarity, acquired=acquired,
                          missed_out=missed_out, sentiment=sentiment, tie_kind=tie.kind, tie_label=tie.label,
                          weight=tie.weight))
    return out


def render_signal(sig: Signal, population: Population, text: SignalText) -> str:
    parts = []
    if sig.acquired:
        parts.append(text.acquired)
    if sig.missed_out:
        parts.append(text.missed_out)
    if sig.polarity in ("positive", "neutral", "negative"):
        parts.append(getattr(text, sig.polarity))
    who = population.agent(sig.sender).name
    where = f", {sig.channel}," if sig.channel else ""
    return f"{who} ({sig.tie_label}){where} " + " and ".join(parts) + "."


def select_inbox(
    inbox: list[Signal], receiver_trend: float, population: Population, text: SignalText
) -> tuple[list[str], str | None, list[Signal]]:
    """Lines shown to the receiver, an overflow tally line, and the signals actually shown."""
    ranked = sorted(inbox, key=lambda s: (-signal_priority(s, population), s.sender))
    cap = inbox_capacity(receiver_trend)
    shown, rest = ranked[:cap], ranked[cap:]
    lines = [render_signal(s, population, text) for s in shown]
    tally = None
    if rest:
        pos = sum(s.polarity == "positive" for s in rest)
        neg = sum(s.polarity == "negative" for s in rest)
        got = sum(s.acquired for s in rest)
        tally = f"{len(rest)} more people they know talked about it ({pos} positive, {neg} negative, {got} got one)."
    return lines, tally, shown


def render_memory(memory: list[MemoryEntry], limit: int = MEMORY_LINES, unit: str = "Round") -> list[str]:
    """Last `limit` entries verbatim; older ones collapse into one tally line."""
    def line(m: MemoryEntry) -> str:
        return f"{unit} {m.round}: {m.text}" if m.round else m.text
    if len(memory) <= limit:
        return [line(m) for m in memory]
    old, recent = memory[:-limit], memory[-limit:]
    pos = sum(m.tone > 0 for m in old)
    neg = sum(m.tone < 0 for m in old)
    head = f"Earlier: {len(old)} things happened ({pos} positive, {neg} negative)."
    return [head] + [line(m) for m in recent]
