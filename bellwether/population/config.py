"""Population config: how a population is sampled. Contains no scenario."""

from __future__ import annotations

from pathlib import Path

import yaml
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CORE_TRAITS = ("risk_tolerance", "price_sensitivity", "trend_following", "social_influence")


class TraitDist(BaseModel):
    """A trait drawn from Beta(a, b), shifted by attributes like `income.low` or `cohort.junior`."""

    beta: tuple[float, float] = (2.0, 2.0)
    shift: dict[str, float] = Field(default_factory=dict)


class Cohort(BaseModel):
    """A sub-group of the community (e.g. 'juniors', 'parents'). Overrides the global defaults."""

    name: str
    share: float
    label: str | None = None
    age: tuple[int, int] | None = None
    income: dict[str, float] | None = None
    location: dict[str, float] | None = None
    life_stage: list[str] | None = None
    occupations: list[str] | None = None
    trait_shift: dict[str, float] = Field(default_factory=dict)


BIG_FIVE = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


class PlatformSpec(BaseModel):
    label: str
    reach: Literal["followers", "algorithmic", "group"]
    weight: float = 0.6  # how much a seen post sways someone, relative to face to face (1.0)


class SocialMediaConfig(BaseModel):
    platforms: dict[str, PlatformSpec] = Field(default_factory=lambda: {
        "instagram": PlatformSpec(label="Instagram", reach="followers", weight=0.6),
        "tiktok": PlatformSpec(label="TikTok", reach="algorithmic", weight=0.4),
        "group_chat": PlatformSpec(label="Group chats", reach="group", weight=0.9),
    })
    # How many platforms a person uses (sampled independently of demographics by default).
    platform_counts: dict[int, float] = Field(default_factory=lambda: {0: 0.1, 1: 0.3, 2: 0.35, 3: 0.25})


class GroupsConfig(BaseModel):
    size: tuple[int, int] = (3, 7)
    same_cohort: float = 0.8
    weak_ties_per_agent: int = 2
    strong_label: str = "close friend"
    weak_label: str = "acquaintance"
    cross_cohort_labels: dict[str, str] = Field(default_factory=dict)


class PopulationConfig(BaseModel):
    name: str
    size: int = 20
    seed: int = 42
    description: str = ""
    age: tuple[int, int] = (18, 70)
    income: dict[str, float] = Field(default_factory=lambda: {"low": 0.35, "mid": 0.45, "high": 0.2})
    location: dict[str, float] = Field(
        default_factory=lambda: {"city centre": 0.3, "inner suburb": 0.3, "outer suburb": 0.2, "small town": 0.15, "rural area": 0.05}
    )
    cohorts: list[Cohort] = Field(default_factory=list)
    traits: dict[str, TraitDist] = Field(default_factory=lambda: {t: TraitDist() for t in CORE_TRAITS})
    trait_words: dict[str, list[str]] = Field(default_factory=dict)
    budget: dict[str, tuple[float, float]] = Field(
        default_factory=lambda: {"low": (20, 80), "mid": (60, 200), "high": (150, 600)}
    )
    budget_label: str = "spare money this month"
    currency_symbol: str = "$"
    groups: GroupsConfig = Field(default_factory=GroupsConfig)
    segments: dict[str, str] = Field(
        default_factory=lambda: {
            "trend_follower": "trend_following >= 0.66",
            "price_sensitive": "price_sensitivity >= 0.66",
            "risk_taker": "risk_tolerance >= 0.66",
            "influencer": "social_influence >= 0.66",
        }
    )
    min_trait_distance: float = 0.12
    big_five: dict[str, TraitDist] = Field(default_factory=lambda: {t: TraitDist() for t in BIG_FIVE})
    social_media: SocialMediaConfig = Field(default_factory=SocialMediaConfig)

    @field_validator("size")
    @classmethod
    def _size(cls, v: int) -> int:
        if not 2 <= v <= 1000:
            raise ValueError("size must be between 2 and 1000")
        return v

    @model_validator(mode="after")
    def _check(self) -> "PopulationConfig":
        missing = [t for t in CORE_TRAITS if t not in self.traits]
        if missing:
            raise ValueError(f"traits must include the core traits; missing {missing}")
        if self.cohorts and abs(sum(c.share for c in self.cohorts) - 1.0) > 1e-6:
            raise ValueError("cohort shares must sum to 1")
        for label, ladder in self.trait_words.items():
            if len(ladder) != 5:
                raise ValueError(f"trait_words.{label} needs exactly 5 levels, low to high")
        return self


def load_population_config(path: str | Path) -> PopulationConfig:
    data = yaml.safe_load(Path(path).read_text())
    return PopulationConfig.model_validate(data.get("population", data))
