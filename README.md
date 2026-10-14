# Bellwether

A domain-agnostic society simulation engine. A seeded population of distinct agents lives through a
scenario timeline; each agent's decisions come from a typed-decision model (Laya locally, Jev via
OpenRouter), shaped by their traits and their social circle. Results compare a baseline against
variants across seeds.

## Run it

```bash
# LM Studio running with Gemma 3 4B loaded on CPU (--gpu off --parallel 1); the default model, local + free
.venv/bin/python -m bellwether serve        # dashboard on http://127.0.0.1:8765
scripts/start-laya.sh                       # optional: Laya checkpoints on :8000 for comparison
```

Headless: `.venv/bin/python -m bellwether run <scenario>` (asks how many people and in what proportion; everyone by default). Non-interactive: add `--yes`, or `--size 30 --mix 25:27:38`.
Trait check: `.venv/bin/python -m bellwether probe <scenario> --agents 4`.
Tests: `.venv/bin/python -m pytest`.

## Making agents: the 10 description groups

Every agent is built from 10 groups: identity, money, personality, habits and tastes, life situation,
social life, health and wellbeing, relationships and home, background, attitudes and beliefs. **Use these
categories while making agents**: the list is `bellwether/population/categories.py`, documented in
[docs/agent-categories.md](docs/agent-categories.md), and a test fails if any agent is missing one.

**Every agent is written in a file**: `school-circle` (25), `northgate-handwritten` (27) and `general-panel` (38) in
`configs/populations/`, and `all` runs all 90 together. [docs/all-agents.md](docs/all-agents.md) lists everyone. Each run
asks how many people and in what proportion; the most accurate choice is everyone, in their natural mix. How to make
and edit agents, field by field: [guide.md](guide.md).

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
| `gemma` (default) | Gemma 3 4B in LM Studio, probabilities from token logprobs averaged over 3 option orders | ~8 s per question |
| `laya` / `laya-typed` | official `laya-serve`, English / typed-decisions checkpoints | ~1.8 s per agent call |
| `laya-gguf` | ggmlc `laya serve` on the LM Studio GGUF (LM Studio itself can't load it) | ~5.2 s per agent call |

Laya reads at most 1,024 tokens per question, so agent states are kept to ~2,600 characters.

V1 uses local, free models only: Gemma and Laya (jev is hidden). Laya checkpoints barely respond to persona traits (trait probe moves < 0.07); Gemma moves them modestly in the right direction, and the engine's trait rules add the rest, so Gemma is the default.
