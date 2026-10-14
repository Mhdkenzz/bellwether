import asyncio
import json

import httpx
import pytest

from bellwether.backends import BackendError, CachedBackend, DecisionCache, FakeBackend, WireBackend, typesafe

JEV_LIKE = {
    "model": "typesafe/jev-1.13-20260917",
    "answers": {
        "action": {"type": "choice", "choice": "buy", "probabilities": {"buy": 0.8, "skip": 0.2}, "confidence": 0.7},
        "mood": {"type": "score", "score": 0.9, "probabilities": {"0": 0.1, "1": 0.9}},
        "yes": {"type": "noul", "noul": 0.6},
    },
    "usage": {"input_tokens": 500, "output_tokens": 40, "cost": 2e-5},
}


def backend_with(handler) -> WireBackend:
    b = WireBackend("test", "http://x/decide", model="m", max_retries=2)
    b._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return b


def test_parses_all_question_types():
    b = backend_with(lambda req: httpx.Response(200, json=JEV_LIKE))
    r = asyncio.run(b.decide({"s": 1}, {"action": {}}))
    assert r.answers["action"].choice == "buy" and r.answers["action"].probabilities["buy"] == 0.8
    assert r.answers["mood"].score == 0.9 and r.answers["yes"].noul == 0.6
    assert r.input_tokens == 500 and r.cost == 2e-5


def test_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json=JEV_LIKE)

    async def no_sleep(*_):
        return None

    monkeypatch.setattr(typesafe.asyncio, "sleep", no_sleep)
    asyncio.run(backend_with(handler).decide({}, {}))
    assert calls["n"] == 3


def test_client_errors_are_not_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(400, text="bad question")

    with pytest.raises(BackendError):
        asyncio.run(backend_with(handler).decide({}, {}))
    assert calls["n"] == 1


def test_request_body_shape():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json=JEV_LIKE)

    asyncio.run(backend_with(handler).decide({"person": "x"}, {"q": {"type": "noul", "instructions": "?"}}))
    assert seen == {"state": {"person": "x"}, "questions": {"q": {"type": "noul", "instructions": "?"}}, "model": "m"}


def test_cache_reuses_answers(tmp_path):
    inner = FakeBackend()
    cached = CachedBackend(inner, DecisionCache(tmp_path / "c.sqlite"))
    q = {"a": {"type": "choice", "instructions": "?", "criteria": {"x": "X", "y": "Y"}}}
    first = asyncio.run(cached.decide({"s": 1}, q))
    second = asyncio.run(cached.decide({"s": 1}, q))
    assert inner.calls == 1 and second.cached and not first.cached
    assert second.answers["a"].probabilities == first.answers["a"].probabilities
