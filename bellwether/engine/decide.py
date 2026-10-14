"""Questions sent to the model, optional trait rules, seeded noise and the final pick."""

from __future__ import annotations

import math
import random
from typing import Any

from ..backends import Answer
from ..expr import evaluate
from ..scenario import DecisionSpec, Scenario


def wire_question(spec: DecisionSpec) -> dict[str, Any]:
    q: dict[str, Any] = {"type": spec.type, "instructions": spec.instructions}
    if spec.type == "choice":
        q["criteria"] = {k: o.text for k, o in spec.options.items()}
    elif spec.type == "score":
        q["criteria"] = list(spec.criteria)
    return q


def seeded_rng(*parts: Any) -> random.Random:
    return random.Random(":".join(str(p) for p in parts))


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    m = max(logits.values())
    exps = {k: math.exp(v - m) for k, v in logits.items()}
    z = sum(exps.values())
    return {k: v / z for k, v in exps.items()}


def apply_rules(probs: dict[str, float], adjust: dict[str, str], weight: float, env: dict[str, Any]) -> dict[str, float]:
    logits = {k: math.log(max(p, 1e-6)) for k, p in probs.items()}
    for option, expr in adjust.items():
        if option in logits:
            logits[option] += weight * float(evaluate(expr, env))
    return _softmax(logits)


def perturb(probs: dict[str, float], sigma: float, rng: random.Random) -> dict[str, float]:
    """p'_k ∝ p_k · exp(σ·ε_k), ε_k ~ N(0,1). σ = 0 leaves probabilities unchanged."""
    if sigma <= 0:
        return dict(probs)
    logits = {k: math.log(max(p, 1e-6)) + sigma * rng.gauss(0.0, 1.0) for k, p in sorted(probs.items())}
    return _softmax(logits)


def argmax(probs: dict[str, float], order: list[str]) -> str:
    """Highest probability; ties go to the option listed first in the scenario."""
    return max(order, key=lambda k: (probs.get(k, 0.0), -order.index(k)))


def shift(probs: dict[str, float], shifts: dict[str, float], strength: float) -> dict[str, float]:
    """Add log-space shifts to a distribution."""
    logits = {k: math.log(max(p, 1e-6)) + strength * shifts.get(k, 0.0) for k, p in probs.items()}
    return _softmax(logits)


def resolve_choice(
    qid: str,
    spec: DecisionSpec,
    answer: Answer,
    scenario: Scenario,
    sigma: float,
    rng: random.Random,
    rule_env: dict[str, Any],
    trait_shifts: dict[str, float] | None = None,
    strength: float = 1.0,
    blocked: dict[str, str] | None = None,
) -> dict[str, Any]:
    """model probs -> scenario rules -> trait rules -> noise -> top feasible option."""
    order = list(spec.options)
    raw = {k: float(answer.probabilities.get(k, 0.0)) for k in order}
    if sum(raw.values()) <= 0:
        raw = {k: 1.0 / len(order) for k in order}
    z = sum(raw.values())
    raw = {k: v / z for k, v in raw.items()}
    adjusted = raw
    rules = scenario.rules
    if rules and qid in rules.adjust:
        adjusted = apply_rules(raw, rules.adjust[qid], rules.weight, rule_env)
    if trait_shifts:
        adjusted = shift(adjusted, trait_shifts, strength)
    noisy = perturb(adjusted, sigma, rng)
    wanted = argmax(noisy, order)
    blocked = blocked or {}
    feasible = [k for k in order if k not in blocked] or order
    pick = argmax(noisy, feasible)
    return {
        "raw": raw,
        "adjusted": adjusted if adjusted is not raw else None,
        "noisy": noisy,
        "choice": pick,
        "wanted": wanted,
        "blocked": blocked or None,
        "model_choice": answer.choice,
        "flipped": wanted != argmax(adjusted, order),
        "confidence": answer.confidence,
    }
