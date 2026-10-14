"""HTTP backends speaking the TypeSafe/Jev decisions wire protocol.

Jev (OpenRouter `/api/alpha/decisions`), the official `laya-serve` and the ggmlc
`laya serve` runtime (`/v1/systemone`) all take `{state, questions}` and return
`{answers, usage}`, so one client covers all three.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx

from .base import BackendError, DecisionBackend, DecisionResponse, normalize_answer


class WireBackend(DecisionBackend):
    def __init__(
        self,
        name: str,
        url: str,
        model: str = "",
        api_key: str | None = None,
        state_char_budget: int = 6000,
        default_concurrency: int = 8,
        timeout: float = 120.0,
        max_retries: int = 4,
        send_model: bool = True,
        health_url: str | None = None,
    ):
        self.name = name
        self.url = url
        self.model = model
        self.state_char_budget = state_char_budget
        self.default_concurrency = default_concurrency
        self.max_retries = max_retries
        self.send_model = send_model
        self.health_url = health_url
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(headers=headers, timeout=timeout)

    async def decide(self, state: dict[str, Any], questions: dict[str, Any]) -> DecisionResponse:
        body: dict[str, Any] = {"state": state, "questions": questions}
        if self.send_model and self.model:
            body["model"] = self.model
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                resp = await self._client.post(self.url, json=body)
            except httpx.TransportError as e:
                err = BackendError(f"{self.name}: {type(e).__name__}: {e}", retryable=True)
            else:
                if resp.status_code == 200:
                    return self._parse(resp.json(), (time.perf_counter() - started) * 1000)
                retryable = resp.status_code in (408, 409, 425, 429, 500, 502, 503, 504)
                err = BackendError(f"{self.name}: HTTP {resp.status_code}: {resp.text[:300]}", retryable=retryable)
            if not err.retryable or attempt == self.max_retries:
                raise err
            await asyncio.sleep(delay + random.random() * delay * 0.5)
            delay = min(delay * 2, 20)
        raise AssertionError("unreachable")

    def _parse(self, data: dict[str, Any], latency_ms: float) -> DecisionResponse:
        if "answers" not in data:
            raise BackendError(f"{self.name}: response has no answers: {str(data)[:300]}")
        usage = data.get("usage") or {}
        return DecisionResponse(
            answers={k: normalize_answer(v) for k, v in data["answers"].items()},
            input_tokens=int(usage.get("input_tokens") or 0),
            cost=float(usage.get("cost") or 0.0),
            latency_ms=float(usage.get("latency_ms") or latency_ms),
            model=str(data.get("model") or self.model),
            truncated=bool(usage.get("truncated") or usage.get("state_tokens_dropped")),
        )

    async def health(self) -> dict[str, Any]:
        if not self.health_url:
            return {"ok": True}
        try:
            r = await self._client.get(self.health_url, timeout=3.0)
            return {"ok": r.status_code < 500, "status": r.status_code}
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"{type(e).__name__}"}

    async def aclose(self) -> None:
        await self._client.aclose()
