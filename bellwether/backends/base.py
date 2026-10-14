"""The decision backend interface. Every model plugs in behind `DecisionBackend.decide`."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Answer:
    type: str
    choice: str | None = None
    probabilities: dict[str, float] = field(default_factory=dict)
    score: float | None = None
    noul: float | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, {})}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Answer":
        return cls(**{k: d.get(k) for k in ("type", "choice", "score", "noul", "confidence")},
                   probabilities=d.get("probabilities") or {})


@dataclass
class DecisionResponse:
    answers: dict[str, Answer]
    input_tokens: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False
    model: str = ""
    truncated: bool = False


class BackendError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class DecisionBackend(ABC):
    name: str = "backend"
    model: str = ""
    # Practical state size for this model (characters); the state builder trims to fit.
    state_char_budget: int = 6000
    default_concurrency: int = 8
    # Bump when the way state/questions become a prompt changes, so cached answers are not reused.
    prompt_version: str = "1"

    @abstractmethod
    async def decide(self, state: dict[str, Any], questions: dict[str, Any]) -> DecisionResponse: ...

    async def health(self) -> dict[str, Any]:
        return {"ok": True}

    async def aclose(self) -> None:
        return None


def normalize_answer(raw: dict[str, Any]) -> Answer:
    """Turn a Jev-protocol answer (Jev, laya-serve, ggmlc laya) into an Answer."""
    t = raw.get("type", "choice")
    probs = {str(k): float(v) for k, v in (raw.get("probabilities") or {}).items()}
    return Answer(
        type=t,
        choice=raw.get("choice"),
        probabilities=probs,
        score=raw.get("score"),
        noul=raw.get("noul"),
        confidence=raw.get("confidence"),
    )
