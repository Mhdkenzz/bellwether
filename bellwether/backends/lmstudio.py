"""Typed decisions from any local chat model served by LM Studio (OpenAI-compatible API).

Each question becomes a short prompt ending in lettered options; the model's next-token
log-probabilities over the letters give a full probability distribution, the same shape
Jev/Laya return. `score` questions use digits 0-9 (expected value), `noul` uses Yes/No.
Questions for one agent share the same prompt prefix, so LM Studio's prompt cache makes
every question after the first cheap.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import string
import time
from typing import Any

import httpx

from .base import Answer, BackendError, DecisionBackend, DecisionResponse

SYSTEM = (
    "You predict what one specific, ordinary person does next.\n"
    "Read every section. HARD FACTS are always true and override everything else: never pick "
    "something the person cannot afford, cannot get, or is not allowed to do.\n"
    "Act like this person, not like an ideal person: real people are tired, distracted, "
    "impulsive, shy or broke. Their traits matter: a price-sensitive person hesitates at prices, "
    "a cautious person waits, a trend follower copies friends, an introvert avoids crowds.\n"
    "Most people are not 100% sure. Reply with the single answer character only."
)

LETTERS = string.ascii_uppercase


def _render_value(value: Any, indent: str = "") -> str:
    if isinstance(value, dict):
        return "\n".join(f"{indent}- {k.replace('_', ' ')}: {_render_value(v)}" if not isinstance(v, (dict, list))
                         else f"{indent}- {k.replace('_', ' ')}:\n{_render_value(v, indent + '  ')}" for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(f"{indent}- {v}" for v in value)
    return str(value)


SECTION_TITLES = {
    "person": "WHO THEY ARE", "traits": "THEIR TRAITS (0 = very low, 1 = very high)", "situation": "THE SITUATION",
    "now": "RIGHT NOW", "right_now": "RIGHT NOW", "how_they_feel": "HOW THEY FEEL", "today_so_far": "TODAY SO FAR",
    "just_happened": "JUST HAPPENED", "your_circle": "WHAT PEOPLE AROUND THEM SAID", "crowd": "WHAT THEY SEE OTHERS DOING",
    "on_their_mind": "ON THEIR MIND", "your_memory": "WHAT THEY REMEMBER", "hard_facts": "HARD FACTS (always true)",
}
# Hard facts go last, right before the question, so they are the freshest thing the model reads.
ORDER_LAST = ("hard_facts",)


def render_state(state: dict[str, Any]) -> str:
    """Clearly titled sections in a stable order (stable prefixes also cache well)."""
    keys = [k for k in state if k not in ORDER_LAST] + [k for k in ORDER_LAST if k in state]
    parts = []
    for key in keys:
        value = state[key]
        title = SECTION_TITLES.get(key, key.replace("_", " ").upper())
        body = _render_value(value) if isinstance(value, (dict, list)) else str(value)
        parts.append(f"## {title}\n{body}")
    return "\n\n".join(parts)


def option_orders(keys: list[str], seed: str, n: int) -> list[list[str]]:
    """n repeatable orderings: one seeded shuffle, then rotations of it, so every option
    appears at a different letter in each ordering (cancels small models' position bias)."""
    base = keys[:]
    random.Random(hashlib.sha256(seed.encode()).hexdigest()).shuffle(base)
    n = max(1, min(n, len(base)))
    step = max(1, len(base) // n)
    return [base[i * step:] + base[:i * step] for i in range(n)]


def render_question(q: dict[str, Any], order: list[str] | None = None) -> tuple[str, list[str], list[str]]:
    """Returns (prompt text, answer tokens, option keys); `order` sets the option order for choices."""
    t = q["type"]
    if t == "choice":
        keys = order or list(q["criteria"])
        tokens = list(LETTERS[: len(keys)])
        lines = [f"{tok}) {q['criteria'][k]}" for tok, k in zip(tokens, keys)]
        return f"## QUESTION\n{q['instructions']}\n" + "\n".join(lines) + "\nAnswer with one letter:", tokens, keys
    if t == "score":
        lo, hi = q["criteria"][0], q["criteria"][-1]
        return (f"## QUESTION\n{q['instructions']}\nRate on a scale from 0 to 9 where 0 means \"{lo}\" and 9 means "
                f"\"{hi}\".\nAnswer with one digit:", list("0123456789"), [str(i) for i in range(10)])
    return f"## QUESTION\n{q['instructions']}\nAnswer Yes or No:", ["Yes", "No"], ["yes", "no"]


class LMStudioBackend(DecisionBackend):
    def __init__(self, name: str, model: str, base_url: str = "http://127.0.0.1:1234",
                 state_char_budget: int = 7000, timeout: float = 300.0, max_retries: int = 3,
                 temperature: float = 1.0, orderings: int = 3):
        self.name = name
        self.model = model
        self.url = f"{base_url}/v1/chat/completions"
        self.health_url = f"{base_url}/v1/models"
        self.state_char_budget = state_char_budget
        self.default_concurrency = 1  # one CPU; parallel requests only queue
        self.orderings = orderings
        self.prompt_version = f"lmstudio-structured-v4-orders{orderings}-T{temperature}"
        self.max_retries = max_retries
        # >1 softens over-confident answers (p ** (1/T), renormalised); 1 leaves them as the model gave them.
        self.temperature = temperature
        self._client = httpx.AsyncClient(timeout=timeout)

    async def _ask(self, prefix: str, question: str, tokens: list[str]) -> dict[str, float]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": f"{prefix}\n\n{question}"}],
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": True,
            "top_logprobs": 20,
        }
        for attempt in range(self.max_retries + 1):
            try:
                r = await self._client.post(self.url, json=body)
                if r.status_code == 200:
                    break
                err = BackendError(f"{self.name}: HTTP {r.status_code}: {r.text[:200]}", retryable=r.status_code >= 500)
            except httpx.TransportError as e:
                err = BackendError(f"{self.name}: {type(e).__name__}: {e}", retryable=True)
            if not err.retryable or attempt == self.max_retries:
                raise err
        data = r.json()
        try:
            top = data["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
        except (KeyError, IndexError, TypeError):
            raise BackendError(f"{self.name}: no logprobs in response; is this LM Studio >= 0.3 with logprobs?") from None
        mass: dict[str, float] = {}
        for item in top:
            tok = item["token"].strip()
            for want in tokens:
                # case-insensitive: models often spread mass over "B" and "b"
                if tok == want or tok.lower() == want.lower():
                    mass[want] = mass.get(want, 0.0) + math.exp(item["logprob"])
        if not mass:  # model answered off-format; fall back to uniform
            return {t: 1.0 / len(tokens) for t in tokens}
        floor = 1e-4
        soft = {t: mass.get(t, floor) ** (1.0 / self.temperature) for t in tokens}
        z = sum(soft.values())
        return {t: v / z for t, v in soft.items()}

    async def decide(self, state: dict[str, Any], questions: dict[str, Any]) -> DecisionResponse:
        prefix = render_state(state)
        started = time.perf_counter()
        answers: dict[str, Answer] = {}
        for qid, q in questions.items():
            if q["type"] == "choice":
                orders = option_orders(list(q["criteria"]), f"{prefix}|{qid}", self.orderings)
                p = {k: 0.0 for k in q["criteria"]}
                for order in orders:  # same prefix -> LM Studio reuses it; only the question is new
                    text, tokens, keys = render_question(q, order)
                    probs = await self._ask(prefix, text, tokens)
                    for t, k in zip(tokens, keys):
                        p[k] += probs[t] / len(orders)
                best = max(p, key=p.__getitem__)
                answers[qid] = Answer("choice", choice=best, probabilities=p, confidence=p[best])
                continue
            text, tokens, keys = render_question(q)
            probs = await self._ask(prefix, text, tokens)
            if q["type"] == "score":
                value = sum(int(t) * probs[t] for t in tokens) / 9
                answers[qid] = Answer("score", score=round(value, 4), probabilities={"0": 1 - value, "1": value},
                                      confidence=max(probs.values()))
            else:
                answers[qid] = Answer("noul", noul=round(probs["Yes"], 4), confidence=max(probs.values()))
        chars = len(prefix) + sum(len(json.dumps(q)) for q in questions.values())
        return DecisionResponse(answers=answers, input_tokens=chars // 4,
                                latency_ms=(time.perf_counter() - started) * 1000, model=self.model)

    async def health(self) -> dict[str, Any]:
        try:
            r = await self._client.get(self.health_url, timeout=3.0)
            ids = [m["id"] for m in r.json().get("data", [])]
            return {"ok": self.model in ids, "status": r.status_code}
        except (httpx.HTTPError, ValueError) as e:
            return {"ok": False, "error": type(e).__name__}

    async def aclose(self) -> None:
        await self._client.aclose()
