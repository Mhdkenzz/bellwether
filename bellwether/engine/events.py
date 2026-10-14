"""Event bus for live dashboards: in-memory fan-out plus JSONL persistence."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any


class EventBus:
    def __init__(self, directory: Path | None = None):
        self.history: list[dict[str, Any]] = []
        self._subs: list[asyncio.Queue] = []
        self._seq = 0
        self.closed = False
        self._events = self._traces = None
        if directory:
            directory.mkdir(parents=True, exist_ok=True)
            self._events = open(directory / "events.jsonl", "a", encoding="utf-8")
            self._traces = open(directory / "traces.jsonl", "a", encoding="utf-8")

    def emit(self, type_: str, **payload: Any) -> dict[str, Any]:
        self._seq += 1
        event = {"seq": self._seq, "t": round(time.time(), 3), "type": type_, **payload}
        self.history.append(event)
        if self._events:
            self._events.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            self._events.flush()
        for q in list(self._subs):
            q.put_nowait(event)
        return event

    def trace(self, record: dict[str, Any]) -> None:
        """Full per-agent detail (state sent, raw answers). Persisted, not broadcast."""
        if self._traces:
            self._traces.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._traces.flush()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subs:
            self._subs.remove(q)

    def close(self) -> None:
        self.closed = True
        for q in list(self._subs):
            q.put_nowait(None)
        for f in (self._events, self._traces):
            if f:
                f.close()
