"""A deterministic, offline backend for tests and dry runs. Not a model of anything."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .base import Answer, DecisionBackend, DecisionResponse


def _unit(*parts: Any) -> float:
    h = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


class FakeBackend(DecisionBackend):
    """Hash-based probabilities, nudged by positive/negative words in the state so social effects show."""

    name = "fake"
    model = "fake-1"
    state_char_budget = 6000
    default_concurrency = 32

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, state: dict[str, Any], questions: dict[str, Any]) -> DecisionResponse:
        self.calls += 1
        text = json.dumps(state, sort_keys=True)
        mood = text.count("recommending") - text.count("warning")
        answers: dict[str, Answer] = {}
        for qid, q in questions.items():
            if q["type"] == "choice":
                keys = list(q["criteria"])
                logits = [3 * _unit(text, qid, k) + (0.6 * mood if i == 0 else 0.0) for i, k in enumerate(keys)]
                z = sum(math.exp(x) for x in logits)
                probs = {k: math.exp(x) / z for k, x in zip(keys, logits)}
                best = max(probs, key=probs.__getitem__)
                answers[qid] = Answer("choice", choice=best, probabilities=probs, confidence=probs[best])
            elif q["type"] == "score":
                s = min(1.0, max(0.0, _unit(text, qid) + 0.1 * mood))
                answers[qid] = Answer("score", score=s, confidence=0.5)
            else:
                answers[qid] = Answer("noul", noul=_unit(text, qid))
        return DecisionResponse(answers=answers, input_tokens=len(text) // 4, latency_ms=0.1, model=self.model)
