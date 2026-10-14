"""Mutable state for one run: the world, each agent's flags, memory, inbox and holdings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..scenario import Scenario


@dataclass
class MemoryEntry:
    round: int
    kind: str  # seed | event | signal | own_action
    text: str
    tone: int = 0  # +1 positive, -1 negative, 0 neutral (used for the tally)


@dataclass
class Signal:
    sender: str
    receiver: str
    round: int
    polarity: str  # positive | neutral | negative | none
    acquired: bool
    missed_out: bool
    sentiment: float | None
    tie_kind: str
    tie_label: str
    weight: float
    channel: str = ""  # e.g. "in person at school", "on Instagram"; empty = word of mouth


@dataclass
class AgentState:
    flags: set[str] = field(default_factory=set)
    memory: list[MemoryEntry] = field(default_factory=list)
    inbox: list[Signal] = field(default_factory=list)
    budget_left: float = 0.0
    holdings: dict[str, float] = field(default_factory=dict)  # item -> units owned (per person)
    choices: dict[int, dict[str, str]] = field(default_factory=dict)  # round -> decision -> option
    scores: dict[int, dict[str, float]] = field(default_factory=dict)
    outcome: dict[int, dict[str, Any]] = field(default_factory=dict)
    sentiment: float | None = None


@dataclass
class ItemState:
    label: str
    price: float
    initial_price: float
    stock: float | None  # real units left; None = unlimited
    initial_stock: float | None
    sold: float = 0.0  # real units
    missed_out: float = 0.0  # real people who tried to get one after stock ran out
    priced_out: float = 0.0  # real people who could not afford it
    # An agent may retry in later rounds; outcome metrics count people once.
    missed_out_agents: set[str] = field(default_factory=set, repr=False)
    priced_out_agents: set[str] = field(default_factory=set, repr=False)


@dataclass
class World:
    items: dict[str, ItemState]
    vars: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> "World":
        return cls(items={
            name: ItemState(label=spec.label or name, price=spec.price, initial_price=spec.price,
                            stock=spec.stock, initial_stock=spec.stock)
            for name, spec in scenario.items.items()
        })

    def apply(self, effects: dict[str, Any]) -> list[str]:
        """Apply `items.<name>.<field>` / `vars.<name>` effects; returns human-readable changes."""
        changes = []
        for path, value in effects.items():
            parts = path.split(".")
            if parts[0] == "items" and len(parts) == 3 and parts[1] in self.items:
                item = self.items[parts[1]]
                if parts[2] not in ("price", "stock"):
                    raise ValueError(f"unsupported item field in effect {path!r}")
                old = getattr(item, parts[2])
                setattr(item, parts[2], float(value) if value is not None else None)
                if parts[2] == "stock" and item.initial_stock is not None and value is not None:
                    item.initial_stock = item.sold + float(value)
                changes.append(f"{path}: {old} -> {value}")
            elif parts[0] == "vars" and len(parts) == 2:
                self.vars[parts[1]] = value
                changes.append(f"{path} = {value}")
            else:
                raise ValueError(f"unsupported effect path {path!r}")
        return changes
