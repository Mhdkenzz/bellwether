# Bellwether

A domain-agnostic society simulation engine. A seeded population of distinct agents lives through a
scenario timeline; each agent's decisions come from a typed-decision model (Laya locally, Jev via
OpenRouter), shaped by their traits and their social circle. Results compare a baseline against
variants across seeds.

## Run it

```bash
# LM Studio running with qwen/qwen3-30b-a3b-2507 loaded (default model, local + free)
.venv/bin/python -m bellwether serve        # dashboard on http://127.0.0.1:8765
scripts/start-laya.sh                       # optional: Laya checkpoints on :8000 for comparison
```

Headless: `.venv/bin/python -m bellwether run <scenario> --size 20 --backend laya`.
Trait check: `.venv/bin/python -m bellwether probe <scenario> --agents 4`.
Tests: `.venv/bin/python -m pytest`.

## Layout

| Path | What |
| --- | --- |
| `bellwether/population/` | Seeded sampler, deep personas (Big Five, type, life details, platforms), social graph |
| `bellwether/life/` | Daily life: time slots, activities, feelings, gatherings, conversations, posts and feeds |
| `bellwether/scenario/` | Scenario schema (YAML): world, decisions, timeline, variants, metrics |
| `bellwether/engine/` | Round loop, state builder, signals, memory, noise, stock and budget |
| `bellwether/backends/` | Jev wire protocol client (Jev, Laya), cache, fake backend |
| `bellwether/analysis/` | Spreads across seeds, paired deltas, segment breakdowns |
| `bellwether/web/` | Live dashboard (FastAPI + server-sent events) |
| `configs/populations/` | Population configs |
| `configs/life/` | Life libraries (time slots and activities) |
| `scenarios/` | Scenario files |
| `runs/<id>/` | events.jsonl, traces.jsonl (every state sent and answer), results.json |

## Models

| Backend | Runtime | Speed (this laptop CPU) |
| --- | --- | --- |
| `qwen` (default) | Qwen3-30B-A3B-Instruct-2507 in LM Studio, probabilities from token logprobs | ~4-6 s per question |
| `laya` / `laya-typed` | official `laya-serve`, English / typed-decisions checkpoints | ~1.8 s per agent call |
| `laya-gguf` | ggmlc `laya serve` on the LM Studio GGUF (LM Studio itself can't load it) | ~5.2 s per agent call |
| `jev` | OpenRouter `/api/alpha/decisions`, paid | network-bound |

Laya reads at most 1,024 tokens per question, so agent states are kept to ~2,600 characters.

Laya checkpoints barely respond to persona traits (trait probe moves < 0.07); Qwen moves them 0.2-0.5, so it is the default.
