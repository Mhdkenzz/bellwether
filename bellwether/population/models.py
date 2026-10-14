"""Agents, social ties and the population that holds them."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, PrivateAttr, model_validator

from .config import PopulationConfig


class Agent(BaseModel):
    id: str
    name: str
    age: int
    cohort: str | None = None
    cohort_label: str | None = None
    community: str = ""  # which population file they come from (matters when communities run together)
    life_stage: str
    occupation: str
    location: str
    income: str
    budget: float
    interests: list[str]
    values: list[str]
    shopping_style: str
    media_habit: str
    decision_style: str
    quirk: str
    traits: dict[str, float]
    segments: list[str]
    group: str = ""
    persona: str = ""
    # depth: personality, daily life, inner life, online life
    big_five: dict[str, float] = {}
    personality_type: str = ""  # introvert | ambivert | extrovert
    chronotype: str = ""
    living: str = ""
    goal_short: str = ""
    goal_long: str = ""
    worries: list[str] = []
    life_context: str = ""
    stress_baseline: float = 0.3
    mood_baseline: float = 0.0
    music: str = ""
    food: str = ""
    temperament: str = ""
    platforms: list[str] = []
    posting: str = ""  # often | sometimes | rarely | never
    susceptibility: float = 0.5  # how easily other people's opinions move them
    profile: str = ""  # long persona for models with room to read it
    # 7. health and wellbeing
    health: str = ""
    sleep: str = ""
    fitness: str = ""
    # 8. relationships and home
    relationship: str = ""
    pets: str = ""
    family_closeness: str = ""
    # 9. background
    hometown: str = ""
    family_money: str = ""
    formative: str = ""
    # 10. attitudes and beliefs
    money_mindset: str = ""
    brand_attitude: str = ""
    tech_attitude: str = ""
    cause: str = ""


class Tie(BaseModel):
    a: str
    b: str
    kind: Literal["strong", "weak"]
    label: str
    weight: float


class Population(BaseModel):
    name: str
    seed: int
    config: PopulationConfig
    agents: list[Agent]
    ties: list[Tie]

    _by_id: dict[str, Agent] = PrivateAttr(default_factory=dict)
    _adjacency: dict[str, list[tuple[str, Tie]]] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _validate_integrity(self) -> "Population":
        ids = [a.id for a in self.agents]
        if len(ids) != len(set(ids)):
            raise ValueError("population agent ids must be unique")
        names = [a.name for a in self.agents]
        if len(names) != len(set(names)):
            raise ValueError("population agent names must be unique")
        personas = [a.persona for a in self.agents if a.persona]
        if len(personas) != len(set(personas)):
            raise ValueError("population personas must be unique")
        signatures = [(a.occupation, tuple(sorted(a.interests))) for a in self.agents]
        if len(signatures) != len(set(signatures)):
            raise ValueError("population occupation/interest signatures must be unique")
        known = set(ids)
        tie_keys: set[tuple[str, str]] = set()
        for tie in self.ties:
            if tie.a == tie.b or tie.a not in known or tie.b not in known:
                raise ValueError(f"invalid tie endpoints: {tie.a!r}, {tie.b!r}")
            key = tuple(sorted((tie.a, tie.b)))
            if key in tie_keys:
                raise ValueError(f"duplicate tie: {key[0]}-{key[1]}")
            tie_keys.add(key)
        if len(self.agents) > 1 and self.config.min_trait_distance > 0:
            for i, left in enumerate(self.agents):
                for right in self.agents[i + 1:]:
                    gap = math.dist(list(left.traits.values()), list(right.traits.values()))
                    if gap < self.config.min_trait_distance:
                        raise ValueError(f"agents {left.id} and {right.id} have near-duplicate traits")
        return self

    def model_post_init(self, __context: object) -> None:
        self._by_id = {a.id: a for a in self.agents}
        adj: dict[str, list[tuple[str, Tie]]] = defaultdict(list)
        for t in self.ties:
            adj[t.a].append((t.b, t))
            adj[t.b].append((t.a, t))
        self._adjacency = dict(adj)

    @property
    def size(self) -> int:
        return len(self.agents)

    def agent(self, agent_id: str) -> Agent:
        return self._by_id[agent_id]

    def neighbors(self, agent_id: str) -> list[tuple[str, Tie]]:
        return self._adjacency.get(agent_id, [])

    def group_members(self, group: str) -> list[str]:
        return [a.id for a in self.agents if a.group == group]

    @property
    def key(self) -> str:
        return f"{self.name}-n{self.size}-s{self.seed}"

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.key}.json"
        path.write_text(self.model_dump_json(indent=2))
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Population":
        return cls.model_validate(json.loads(Path(path).read_text()))
