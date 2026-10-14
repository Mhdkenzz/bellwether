"""Scenario schema. A scenario is data (YAML); the engine knows no domain."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

Polarity = Literal["positive", "neutral", "negative", "none"]


class Selector(BaseModel):
    """Which agents something applies to. All given conditions must hold (AND).

    `include_groups` / `include_ties` widen the match to the matched agents' friend
    groups or direct ties (e.g. "past buyers plus their friends and family").
    """

    all: bool = False
    flag: str | None = None
    not_flag: str | None = None
    cohort: str | list[str] | None = None
    community: str | list[str] | None = None  # population file(s) people come from, when several run together
    segment: str | None = None
    ids: list[str] | None = None
    where: str | None = None
    platform: str | None = None  # only people who use this social platform
    fraction: float | None = None
    include_groups: bool = False
    include_ties: Literal["strong", "all"] | None = None

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, v: Any) -> Any:
        if v == "all":
            return {"all": True}
        return v


class Consume(BaseModel):
    item: str
    qty: float = 1.0


class OptionSpec(BaseModel):
    text: str
    consume: Consume | None = None
    # What taking this option means, for the engine's trait rules:
    # act = commit (default for options that consume), delay = hold off, decline = say no.
    stance: Literal["act", "delay", "decline"] | None = None
    signal: Polarity | None = None
    set_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, v: Any) -> Any:
        return {"text": v} if isinstance(v, str) else v


class DecisionSpec(BaseModel):
    type: Literal["choice", "score", "noul"]
    instructions: str
    options: dict[str, OptionSpec] = Field(default_factory=dict)
    criteria: list[str] = Field(default_factory=list)
    role: Literal["signal", "sentiment"] | None = None
    ask_if: Selector | None = None

    @model_validator(mode="after")
    def _check(self) -> "DecisionSpec":
        if self.type == "choice" and len(self.options) < 2:
            raise ValueError("a choice decision needs at least 2 options")
        if self.type == "score" and len(self.criteria) < 2:
            raise ValueError("a score decision needs at least 2 criteria levels")
        if self.role == "signal" and self.type != "choice":
            raise ValueError("role 'signal' needs a choice decision whose options set `signal`")
        if self.role == "sentiment" and self.type != "score":
            raise ValueError("role 'sentiment' needs a score decision")
        return self


class ItemSpec(BaseModel):
    label: str | None = None
    price: float = 0.0
    stock: float | None = None  # in real units; None = unlimited
    max_per_agent: int = 1


class InitialFlag(BaseModel):
    flag: str
    select: Selector
    memory: str | None = None
    count: float | None = None  # exact number of real people (scaled to agents)


class EventSpec(BaseModel):
    round: int
    text: str
    slot: str | None = None  # time of day (life scenarios); default = first slot
    visible_to: Selector = Field(default_factory=lambda: Selector(all=True))
    effects: dict[str, Any] = Field(default_factory=dict)
    set_flags: list[str] = Field(default_factory=list)
    # Nudge (log-odds) for agents who see this event, keyed by option stance
    # (act / delay / decline) or message polarity (positive / neutral / negative / none).
    # It fades by `sway_decay` each round after the event.
    sway: dict[Literal["act", "delay", "decline", "positive", "neutral", "negative", "none"], float] = Field(
        default_factory=dict)
    sway_decay: float = 0.5


class Rules(BaseModel):
    """Optional trait rules: logit shifts per option, blended with the model's probabilities."""

    weight: float = 0.3
    adjust: dict[str, dict[str, str]] = Field(default_factory=dict)


class TraitRules(BaseModel):
    """Engine rules: traits/money/stock/social circle shift the model's probabilities."""

    enabled: bool = True
    strength: float = 1.0
    block_infeasible: bool = True


class SignalText(BaseModel):
    acquired: str = "got one"  # rendered as "<name> (<tie>) got one and is recommending it."
    positive: str = "is recommending it"
    neutral: str = "mentioned it"
    negative: str = "is warning people off it"
    missed_out: str = "tried to get one but missed out"


class Scenario(BaseModel):
    name: str
    title: str = ""
    rounds: int = 3
    currency_symbol: str = "$"
    market_size: float | None = None
    context: str
    items: dict[str, ItemSpec] = Field(default_factory=dict)
    show_stock: bool = True
    crowd_stats: bool = False
    initial_state: list[InitialFlag] = Field(default_factory=list)
    trait_context: dict[str, str] = Field(default_factory=dict)
    decisions: dict[str, DecisionSpec]
    timeline: list[EventSpec] = Field(default_factory=list)
    variants: dict[str, list[EventSpec]] = Field(default_factory=dict)
    rules: Rules | None = None
    trait_rules: TraitRules = Field(default_factory=TraitRules)
    metrics: dict[str, str] = Field(default_factory=dict)
    signal_text: SignalText = Field(default_factory=SignalText)
    headline: list[str] = Field(default_factory=list)
    # Daily life: each round becomes a day lived slot by slot (see configs/life/).
    life: str | None = None
    decide_at: str = "evening"  # the slot in which scenario decisions are asked
    topic: str = ""  # what people talk and post about, e.g. "the drop 2 hoodie"

    @field_validator("rounds")
    @classmethod
    def _rounds(cls, v: int) -> int:
        if not 1 <= v <= 20:
            raise ValueError("rounds must be 1-20")
        return v

    @model_validator(mode="after")
    def _check(self) -> "Scenario":
        for name, d in self.decisions.items():
            for key, opt in d.options.items():
                if opt.consume and opt.consume.item not in self.items:
                    raise ValueError(f"decision {name}.{key} consumes unknown item {opt.consume.item!r}")
        for ev in self.all_events():
            if not 1 <= ev.round <= self.rounds:
                raise ValueError(f"event round {ev.round} is outside 1..{self.rounds}")
        if self.rules:
            for dname, opts in self.rules.adjust.items():
                if dname not in self.decisions:
                    raise ValueError(f"rules.adjust references unknown decision {dname!r}")
                unknown = set(opts) - set(self.decisions[dname].options)
                if unknown:
                    raise ValueError(f"rules.adjust.{dname} references unknown options {sorted(unknown)}")
        return self

    def all_events(self) -> list[EventSpec]:
        return self.timeline + [e for evs in self.variants.values() for e in evs]

    def arms(self) -> list[str]:
        return ["baseline", *self.variants]

    def events_for(self, arm: str, round_: int) -> list[EventSpec]:
        evs = [e for e in self.timeline if e.round == round_]
        if arm != "baseline":
            evs += [e for e in self.variants[arm] if e.round == round_]
        return evs


def load_scenario(path: str | Path) -> Scenario:
    return Scenario.model_validate(yaml.safe_load(Path(path).read_text()))
