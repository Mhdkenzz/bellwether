"""Backend registry. V1 uses local models only: Gemma 4B (LM Studio) and Laya. Jev is not offered."""

from __future__ import annotations

from ..settings import CACHE_PATH, env
from .base import Answer, BackendError, DecisionBackend, DecisionResponse
from .cache import CachedBackend, DecisionCache
from .fake import FakeBackend
from .lmstudio import LMStudioBackend
from .typesafe import WireBackend

DEFAULT_BACKEND = "gemma"

# Laya reads at most 1024 tokens per question pass and shares that window with the
# question and its options, so states sent to it are kept around 650 tokens.
LAYA_STATE_CHARS = 2600

LMSTUDIO_MODELS = {
    "gemma": "gemma-3-4b-null-space-abliterated-rp-writer",
}

BACKENDS = {
    "gemma": "Gemma 3 4B in LM Studio, scored by token odds (local, free). Default.",
    "laya": "Laya general English checkpoint via laya-serve (local, free).",
    "laya-typed": "Laya typed-decisions specialist via laya-serve (local, free).",
    "laya-gguf": "Laya typed-decisions GGUF from LM Studio via the ggmlc runtime (local, ~5 s/call).",
    "fake": "Deterministic offline stand-in for tests.",
}
# Kept in code for later, not offered in V1 (user decision 2026-10-14).
HIDDEN_BACKENDS = {"jev"}


def make_backend(name: str = DEFAULT_BACKEND, cache: bool = True, state_char_budget: int | None = None) -> DecisionBackend:
    backend: DecisionBackend
    if name in LMSTUDIO_MODELS:
        backend = LMStudioBackend(name, env(f"LMSTUDIO_MODEL_{name.upper().replace('-', '_')}", LMSTUDIO_MODELS[name]),
                                  base_url=env("LMSTUDIO_URL", "http://127.0.0.1:1234"))
    elif name in ("laya", "laya-typed"):
        base = env("LAYA_URL", "http://127.0.0.1:8000")
        backend = WireBackend(
            name, f"{base}/v1/systemone", model="english" if name == "laya" else "typed-decisions",
            state_char_budget=LAYA_STATE_CHARS, default_concurrency=1, health_url=f"{base}/health",
        )
    elif name == "laya-gguf":
        base = env("LAYA_GGUF_URL", "http://127.0.0.1:8080")
        backend = WireBackend(
            "laya-gguf", f"{base}/v1/systemone", model="laya-typed-decisions", send_model=False,
            state_char_budget=LAYA_STATE_CHARS, default_concurrency=1, health_url=f"{base}/health",
        )
    elif name == "jev":
        key = env("OPENROUTER_API_KEY")
        if not key:
            raise BackendError("OPENROUTER_API_KEY is not set in .env")
        backend = WireBackend(
            "jev", "https://openrouter.ai/api/alpha/decisions", model=env("BELLWETHER_MODEL", "typesafe/jev-1.13"),
            api_key=key, state_char_budget=6000, default_concurrency=16,
        )
    elif name == "fake":
        backend = FakeBackend()
    else:
        raise BackendError(f"unknown backend {name!r}; choose from {sorted(BACKENDS)}")
    if name in HIDDEN_BACKENDS and env("BELLWETHER_ALLOW_JEV") != "1":
        raise BackendError("jev is disabled for V1 (set BELLWETHER_ALLOW_JEV=1 to re-enable)")
    if state_char_budget:
        backend.state_char_budget = state_char_budget
    if cache and name != "fake":
        backend = CachedBackend(backend, DecisionCache(CACHE_PATH))
    return backend


__all__ = [
    "Answer",
    "BACKENDS",
    "BackendError",
    "CachedBackend",
    "DEFAULT_BACKEND",
    "DecisionBackend",
    "DecisionCache",
    "DecisionResponse",
    "FakeBackend",
    "LMStudioBackend",
    "WireBackend",
    "make_backend",
]
