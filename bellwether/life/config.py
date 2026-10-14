"""Life config: time slots in a day and the activities people can choose in each."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from ..settings import ROOT

LIFE_DIR = ROOT / "configs" / "life"
FEELINGS = ("energy", "mood", "stress", "hunger", "social_need")


class Activity(BaseModel):
    id: str
    text: str
    place: str = "home"
    # who it brings you together with; "event" = everyone else who chose this activity, at its place
    social: Literal["friends", "household", "colleagues", "online_friends", "event"] | None = None
    media: Literal["scroll", "post", "both"] | None = None
    tags: list[str] = Field(default_factory=list)
    effects: dict[str, float] = Field(default_factory=dict)
    life_stages: list[str] | None = None
    cost: float = 0.0
    money: float = 0.0
    sleep: float = 0.0  # night only: change to tomorrow's starting energy

    @model_validator(mode="after")
    def _check(self) -> "Activity":
        bad = set(self.effects) - set(FEELINGS)
        if bad:
            raise ValueError(f"activity {self.id}: unknown effects {sorted(bad)}")
        return self


class Slot(BaseModel):
    id: str
    label: str
    activities: list[Activity]
    # What is expected of people at this time, by life stage (shown to the model as a hard fact).
    obligations: dict[str, str] = Field(default_factory=dict)

    def offered(self, life_stage: str) -> list[Activity]:
        return [a for a in self.activities if not a.life_stages or life_stage in a.life_stages]


class LifeConfig(BaseModel):
    name: str
    slots: list[Slot]

    def slot(self, slot_id: str) -> Slot:
        return next(s for s in self.slots if s.id == slot_id)

    def activity(self, slot_id: str, activity_id: str) -> Activity:
        return next(a for a in self.slot(slot_id).activities if a.id == activity_id)


def load_life(name: str) -> LifeConfig:
    path = Path(name) if name.endswith(".yaml") else LIFE_DIR / f"{name}.yaml"
    return LifeConfig.model_validate(yaml.safe_load(path.read_text()))
