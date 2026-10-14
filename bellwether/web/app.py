"""Local dashboard: launch experiments and watch every agent live (server-sent events)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from ..backends import BACKENDS, DEFAULT_BACKEND, BackendError, make_backend
from ..experiment import Experiment, ExperimentSpec
from ..population import load_population_config, sample_population
from ..scenario import load_scenario
from ..settings import POPULATION_CONFIG_DIR, POPULATION_DIR, RUNS_DIR, SCENARIO_DIR

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Bellwether")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

EXPERIMENTS: dict[str, Experiment] = {}
TASKS: dict[str, asyncio.Task] = {}


class LaunchRequest(BaseModel):
    population_config: str = "all"
    size: int | None = None  # None = everyone written (or the config's size for a generated population)
    mix: dict[str, float] | None = None  # proportion per community (combined) or cohort; None = natural mix
    population_seed: int | None = None
    scenario: str
    backend: str = DEFAULT_BACKEND
    arms: list[str] | None = None
    seeds: int = 1
    base_seed: int = 1
    sigma: float = 0.15
    concurrency: int | None = None
    char_budget: int | None = None


@app.get("/")
def index() -> HTMLResponse:
    html = (STATIC / "index.html").read_text()
    for name in ("app.css", "app.js"):
        stamp = int((STATIC / name).stat().st_mtime)
        html = html.replace(f"/static/{name}", f"/static/{name}?v={stamp}")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/backends")
async def backends() -> list[dict[str, Any]]:
    out = []
    for name, desc in BACKENDS.items():
        try:
            b = make_backend(name, cache=False)
            health = await b.health()
            await b.aclose()
        except BackendError as e:
            health = {"ok": False, "error": str(e)}
        out.append({"name": name, "description": desc, "health": health, "default": name == DEFAULT_BACKEND,
                    "paid": name == "jev"})
    return out


def _parts(cfg) -> dict[str, int]:
    from collections import Counter

    from ..population.combine import available

    if cfg.include:
        return available(cfg)
    if cfg.agents:
        return dict(Counter(a.get("cohort") or "-" for a in cfg.agents))
    return {}


@app.get("/api/population-configs")
def population_configs() -> list[dict[str, Any]]:
    out = []
    for path in sorted(POPULATION_CONFIG_DIR.glob("*.yaml")):
        try:
            cfg = load_population_config(path)
            parts = _parts(cfg)
            out.append({"name": cfg.name, "file": path.stem, "size": cfg.size, "seed": cfg.seed,
                        "description": cfg.description, "cohorts": [c.name for c in cfg.cohorts],
                        "written": sum(parts.values()) or None, "parts": parts,
                        "part_kind": "community" if cfg.include else "cohort" if parts else None})
        except (ValidationError, ValueError, yaml.YAMLError) as e:
            out.append({"name": path.stem, "file": path.stem, "error": str(e)[:300]})
    out.sort(key=lambda c: (c["file"] != "all", c["file"]))  # everyone first
    return out


class PlanRequest(BaseModel):
    size: int | None = None
    mix: dict[str, float] | None = None


@app.post("/api/population-configs/{name}/plan")
def population_plan(name: str, req: PlanRequest) -> dict[str, Any]:
    """How many people from each part a run would use (or why that size/mix can't work)."""
    from ..population.mix import plan_counts

    parts = _parts(_load_pop_config(name))
    if not parts:
        return {"counts": {}, "total": req.size, "natural": True}
    try:
        counts = plan_counts(parts, req.size, req.mix)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    natural = counts == parts
    return {"counts": counts, "total": sum(counts.values()), "natural": natural}


@app.get("/api/population-configs/{name}/preview")
def population_preview(name: str, size: int | None = None, seed: int | None = None) -> dict[str, Any]:
    try:
        pop = sample_population(_load_pop_config(name), size=size, seed=seed)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return json.loads(pop.model_dump_json())


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, Any]]:
    out = []
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        try:
            sc = load_scenario(path)
            out.append({"name": sc.name, "file": path.stem, "title": sc.title, "rounds": sc.rounds,
                        "arms": sc.arms(), "market_size": sc.market_size, "decisions": len(sc.decisions),
                        "life": bool(sc.life),
                        "items": {k: v.model_dump() for k, v in sc.items.items()}})
        except (ValidationError, yaml.YAMLError) as e:
            out.append({"name": path.stem, "file": path.stem, "error": str(e)[:500]})
    return out


@app.get("/api/scenarios/{name}")
def scenario_detail(name: str) -> dict[str, Any]:
    path = SCENARIO_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(404, "no such scenario")
    return {"yaml": path.read_text(), "parsed": json.loads(load_scenario(path).model_dump_json())}


def _load_pop_config(name: str):
    path = POPULATION_CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(404, f"no population config {name!r}")
    return load_population_config(path)


@app.post("/api/experiments")
async def launch(req: LaunchRequest) -> dict[str, Any]:
    scenario_path = SCENARIO_DIR / f"{req.scenario}.yaml"
    if not scenario_path.exists():
        raise HTTPException(404, f"no scenario {req.scenario!r}")
    try:
        scenario = load_scenario(scenario_path)
        population = sample_population(_load_pop_config(req.population_config), size=req.size,
                                       seed=req.population_seed, mix=req.mix)
        population.save(POPULATION_DIR)
        backend = make_backend(req.backend)
    except (ValidationError, BackendError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    spec = ExperimentSpec(population=population.key, scenario=scenario.name, backend=req.backend, arms=req.arms,
                          seeds=req.seeds, base_seed=req.base_seed, sigma=req.sigma, concurrency=req.concurrency,
                          char_budget=req.char_budget)
    exp = Experiment(spec, population, scenario, backend)
    try:
        exp.arms
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    EXPERIMENTS[exp.id] = exp

    async def go() -> None:
        try:
            await exp.run()
        finally:
            await backend.aclose()

    TASKS[exp.id] = asyncio.create_task(go())
    return exp.overview()


def _from_disk(data: dict[str, Any]) -> dict[str, Any]:
    """A run marked running on disk but not owned by this server process was interrupted."""
    if data.get("status") in ("running", "pending") and data.get("id") not in EXPERIMENTS:
        data["status"] = "interrupted"
    return data


@app.get("/api/experiments")
def experiments() -> list[dict[str, Any]]:
    seen = {e.id: e.overview() for e in EXPERIMENTS.values()}
    for spec in sorted(RUNS_DIR.glob("*/spec.json"), reverse=True):
        eid = spec.parent.name
        if eid not in seen:
            try:
                seen[eid] = _from_disk(json.loads(spec.read_text()))
            except json.JSONDecodeError:
                continue
    return sorted(seen.values(), key=lambda e: e["id"], reverse=True)


@app.get("/api/experiments/{eid}")
def experiment(eid: str) -> dict[str, Any]:
    if eid in EXPERIMENTS:
        e = EXPERIMENTS[eid]
        return {**e.overview(), "summary": e.summary}
    path = RUNS_DIR / eid / "results.json"
    if path.exists():
        data = json.loads(path.read_text())
        data.pop("runs", None)
        return data
    spec = RUNS_DIR / eid / "spec.json"
    if spec.exists():
        return _from_disk(json.loads(spec.read_text()))
    raise HTTPException(404, "no such experiment")


@app.post("/api/experiments/{eid}/cancel")
def cancel(eid: str) -> dict[str, Any]:
    task = TASKS.get(eid)
    if not task or task.done():
        raise HTTPException(409, "experiment is not running")
    task.cancel()
    return {"ok": True}


@app.get("/api/experiments/{eid}/events")
async def events(eid: str) -> StreamingResponse:
    async def live(exp: Experiment):
        q = exp.bus.subscribe()
        try:
            last = 0
            for ev in list(exp.bus.history):
                last = ev["seq"]
                yield f"data: {json.dumps(ev, default=str)}\n\n"
            while True:
                if exp.bus.closed and q.empty():
                    break
                ev = await q.get()
                if ev is None:
                    break
                if ev["seq"] > last:
                    last = ev["seq"]
                    yield f"data: {json.dumps(ev, default=str)}\n\n"
        finally:
            exp.bus.unsubscribe(q)
        yield "event: end\ndata: {}\n\n"

    async def from_disk(path: Path):
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield f"data: {line.strip()}\n\n"
        yield "event: end\ndata: {}\n\n"

    if eid in EXPERIMENTS:
        gen = live(EXPERIMENTS[eid])
    else:
        path = RUNS_DIR / eid / "events.jsonl"
        if not path.exists():
            raise HTTPException(404, "no such experiment")
        gen = from_disk(path)
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/experiments/{eid}/trace")
def trace(eid: str, agent: str, arm: str | None = None, run: int | None = None) -> list[dict[str, Any]]:
    path = RUNS_DIR / eid / "traces.jsonl"
    if not path.exists():
        raise HTTPException(404, "no traces")
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if f'"agent": "{agent}"' not in line:
                continue
            rec = json.loads(line)
            if rec.get("agent") != agent:
                continue
            if arm is not None and rec.get("arm") != arm:
                continue
            if run is not None and rec.get("run") != run:
                continue
            out.append(rec)
    return out
