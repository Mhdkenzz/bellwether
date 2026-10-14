"""Response cache. The models are deterministic, so identical requests reuse earlier answers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .base import Answer, DecisionBackend, DecisionResponse


def request_key(backend: str, model: str, state: Any, questions: Any) -> str:
    blob = json.dumps([backend, model, state, questions], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


class DecisionCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS decisions (key TEXT PRIMARY KEY, backend TEXT, model TEXT, response TEXT)"
        )
        self._lock = threading.Lock()

    def get(self, key: str) -> DecisionResponse | None:
        with self._lock:
            row = self._db.execute("SELECT response FROM decisions WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        d = json.loads(row[0])
        return DecisionResponse(
            answers={k: Answer.from_dict(v) for k, v in d["answers"].items()},
            input_tokens=d.get("input_tokens", 0),
            cost=0.0,
            latency_ms=0.0,
            cached=True,
            model=d.get("model", ""),
            truncated=d.get("truncated", False),
        )

    def put(self, key: str, backend: str, model: str, resp: DecisionResponse) -> None:
        payload = json.dumps({
            "answers": {k: a.to_dict() for k, a in resp.answers.items()},
            "input_tokens": resp.input_tokens,
            "model": resp.model,
            "truncated": resp.truncated,
        })
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO decisions VALUES (?, ?, ?, ?)", (key, backend, model, payload))
            self._db.commit()


class CachedBackend(DecisionBackend):
    def __init__(self, inner: DecisionBackend, cache: DecisionCache):
        self.inner = inner
        self.cache = cache
        self.name = inner.name
        self.model = inner.model
        self.state_char_budget = inner.state_char_budget
        self.default_concurrency = inner.default_concurrency

    async def decide(self, state: dict[str, Any], questions: dict[str, Any]) -> DecisionResponse:
        key = request_key(self.inner.name, f"{self.inner.model}|{self.inner.prompt_version}", state, questions)
        hit = self.cache.get(key)
        if hit:
            return hit
        resp = await self.inner.decide(state, questions)
        self.cache.put(key, self.inner.name, self.inner.model, resp)
        return resp

    async def health(self) -> dict[str, Any]:
        return await self.inner.health()

    async def aclose(self) -> None:
        await self.inner.aclose()
