"""Experiments: baseline + variants × seeds on one population, with live events and saved results."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .analysis import summarize
from .backends import DecisionBackend
from .engine.events import EventBus
from .engine.run import RunConfig, RunResult, people_weight, run_once
from .population import Population
from .population.categories import CATEGORY_GROUPS
from .scenario import Scenario
from .settings import RUNS_DIR


@dataclass
class ExperimentSpec:
    population: str
    scenario: str
    backend: str = "laya"
    arms: list[str] | None = None
    seeds: int = 1
    base_seed: int = 1
    sigma: float = 0.15
    concurrency: int | None = None
    char_budget: int | None = None
    label: str = ""


@dataclass
class Experiment:
    spec: ExperimentSpec
    population: Population
    scenario: Scenario
    backend: DecisionBackend
    root: Path = RUNS_DIR
    id: str = ""
    status: str = "pending"
    results: list[RunResult] = field(default_factory=list)
    summary: dict[str, Any] | None = None
    error: str | None = None
    started_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.id:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.id = f"{stamp}-{self.scenario.name}-{self.spec.backend}-n{self.population.size}"
        self.dir = self.root / self.id
        self.bus = EventBus(self.dir)

    @property
    def arms(self) -> list[str]:
        arms = self.spec.arms or self.scenario.arms()
        unknown = set(arms) - set(self.scenario.arms())
        if unknown:
            raise ValueError(f"unknown arms {sorted(unknown)}; scenario has {self.scenario.arms()}")
        return arms

    def overview(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "spec": asdict(self.spec),
            "arms": self.arms,
            "population": self.population.key,
            "scenario": self.scenario.name,
            "title": self.scenario.title,
            "agents": self.population.size,
            "rounds": self.scenario.rounds,
            "weight": people_weight(self.population, self.scenario),
            "started_at": self.started_at,
            "error": self.error,
        }

    def _start_payload(self) -> dict[str, Any]:
        agents = [
            {"id": a.id, "name": a.name, "age": a.age, "cohort": a.cohort, "cohort_label": a.cohort_label, "community": a.community,
             "occupation": a.occupation, "segments": a.segments, "traits": a.traits, "group": a.group,
             "persona": a.persona, "income": a.income, "budget": a.budget, "profile": a.profile,
             "big_five": a.big_five, "personality_type": a.personality_type, "platforms": a.platforms,
             "posting": a.posting, "chronotype": a.chronotype, "living": a.living, "life_context": a.life_context,
             "goal_short": a.goal_short, "goal_long": a.goal_long, "worries": a.worries,
             "temperament": a.temperament, "susceptibility": a.susceptibility, "life_stage": a.life_stage,
             "location": a.location, "interests": a.interests, "values": a.values, "shopping_style": a.shopping_style,
             "media_habit": a.media_habit, "decision_style": a.decision_style, "quirk": a.quirk, "music": a.music,
             "food": a.food, "health": a.health, "sleep": a.sleep, "fitness": a.fitness,
             "relationship": a.relationship, "pets": a.pets, "family_closeness": a.family_closeness,
             "hometown": a.hometown, "family_money": a.family_money, "formative": a.formative,
             "money_mindset": a.money_mindset, "brand_attitude": a.brand_attitude, "tech_attitude": a.tech_attitude,
             "cause": a.cause}
            for a in self.population.agents
        ]
        ties = [{"a": t.a, "b": t.b, "kind": t.kind, "label": t.label} for t in self.population.ties]
        decisions = {q: {"type": d.type, "role": d.role, "options": {k: o.text for k, o in d.options.items()},
                         "consumes": [k for k, o in d.options.items() if o.consume]}
                     for q, d in self.scenario.decisions.items()}
        return {**self.overview(), "agents_detail": agents, "ties": ties, "decisions": decisions,
                "items": {k: v.model_dump() for k, v in self.scenario.items.items()},
                "context": self.scenario.context, "model": self.backend.model, "topic": self.scenario.topic,
                "life": self.scenario.life, "decide_at": self.scenario.decide_at,
                "platforms": {k: v.label for k, v in self.population.config.social_media.platforms.items()},
                "categories": CATEGORY_GROUPS}

    async def run(self) -> dict[str, Any] | None:
        self.started_at = time.time()
        self.status = "running"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "spec.json").write_text(json.dumps(self.overview(), indent=2))
        (self.dir / "population.json").write_text(self.population.model_dump_json(indent=2))
        (self.dir / "scenario.json").write_text(self.scenario.model_dump_json(indent=2))
        self.bus.emit("experiment_started", **self._start_payload())
        concurrency = self.spec.concurrency or self.backend.default_concurrency
        try:
            for k in range(self.spec.seeds):
                seed = self.spec.base_seed + k
                for arm in self.arms:
                    cfg = RunConfig(experiment_id=self.id, arm=arm, run_index=k, seed=seed, sigma=self.spec.sigma,
                                    concurrency=concurrency, char_budget=self.spec.char_budget)
                    self.results.append(await run_once(self.population, self.scenario, self.backend, self.bus, cfg))
            self.summary = summarize(self.results, self.population, self.scenario)
            self.status = "finished"
            self.bus.emit("experiment_finished", **self.overview(), summary=self.summary)
        except asyncio.CancelledError:
            self.status = "cancelled"
            self.bus.emit("experiment_cancelled", **self.overview())
            raise
        except Exception as e:
            self.status = "failed"
            self.error = f"{type(e).__name__}: {e}"
            self.bus.emit("experiment_failed", **self.overview())
        finally:
            self._save()
            self.bus.close()
        return self.summary

    def _save(self) -> None:
        payload = {
            **self.overview(),
            "summary": self.summary,
            "runs": [asdict(r) for r in self.results],
        }
        (self.dir / "results.json").write_text(json.dumps(payload, indent=2, default=str))
        (self.dir / "spec.json").write_text(json.dumps(self.overview(), indent=2))
