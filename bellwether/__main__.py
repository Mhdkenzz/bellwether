"""Command line: `python -m bellwether serve | population | run | probe`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .backends import BACKENDS, DEFAULT_BACKEND, make_backend
from .settings import POPULATION_CONFIG_DIR, POPULATION_DIR, SCENARIO_DIR


def _check_paid(args: argparse.Namespace) -> None:
    if args.backend == "jev" and not args.yes_paid:
        sys.exit("jev is paid; pass --yes-paid to confirm.")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    print(f"Bellwether dashboard: http://{args.host}:{args.port}")
    uvicorn.run("bellwether.web.app:app", host=args.host, port=args.port, log_level="warning")


def cmd_population(args: argparse.Namespace) -> None:
    from .population import load_population_config, sample_population

    pop = sample_population(load_population_config(POPULATION_CONFIG_DIR / f"{args.config}.yaml"),
                            size=args.size, seed=args.seed)
    path = pop.save(POPULATION_DIR)
    print(f"{pop.size} agents, {len(pop.ties)} ties -> {path}")
    for a in pop.agents[: args.show]:
        t = a.traits
        print(f"\n{a.id} [{a.group}] R{t['risk_tolerance']:.2f} P{t['price_sensitivity']:.2f} "
              f"T{t['trend_following']:.2f} S{t['social_influence']:.2f} {a.segments}\n  {a.persona}")


def cmd_run(args: argparse.Namespace) -> None:
    from .experiment import Experiment, ExperimentSpec
    from .population import load_population_config, sample_population
    from .scenario import load_scenario

    _check_paid(args)
    scenario = load_scenario(SCENARIO_DIR / f"{args.scenario}.yaml")
    pop = sample_population(load_population_config(POPULATION_CONFIG_DIR / f"{args.population}.yaml"),
                            size=args.size, seed=args.population_seed)
    pop.save(POPULATION_DIR)
    backend = make_backend(args.backend)
    spec = ExperimentSpec(population=pop.key, scenario=scenario.name, backend=args.backend,
                          arms=args.arms.split(",") if args.arms else None, seeds=args.seeds, sigma=args.sigma)
    exp = Experiment(spec, pop, scenario, backend)

    async def go() -> None:
        q = exp.bus.subscribe()
        task = asyncio.create_task(exp.run())
        while True:
            ev = await q.get()
            if ev is None:
                break
            t = ev["type"]
            if t == "round_started":
                print(f"[{ev['arm']} run{ev['run']}] round {ev['round']}: " + "; ".join(e["text"] for e in ev["events"]))
            elif t == "round_finished":
                print(f"   asked {ev['asked']} · {ev['choices']} · outcomes {ev['outcomes']} · "
                      f"calls {ev['calls']} ({ev['cached']} cached) · errors {ev['errors']}")
            elif t == "run_finished":
                print(f"   run done in {ev['seconds']}s")
        await task
        await backend.aclose()

    asyncio.run(go())
    print(f"\n{exp.status}: {exp.dir}")
    if exp.error:
        print(exp.error)
    if exp.summary and args.json:
        print(json.dumps(exp.summary, indent=2))


def cmd_probe(args: argparse.Namespace) -> None:
    from .population import load_population_config, sample_population
    from .probe import probe_traits, sensitivity
    from .scenario import load_scenario

    _check_paid(args)
    scenario = load_scenario(SCENARIO_DIR / f"{args.scenario}.yaml")
    pop = sample_population(load_population_config(POPULATION_CONFIG_DIR / f"{args.population}.yaml"), size=args.size)
    ids = [a.id for a in pop.agents[: args.agents]]
    backend = make_backend(args.backend)

    async def go():
        try:
            return await probe_traits(pop, scenario, backend, ids, arm=args.arm)
        finally:
            await backend.aclose()

    rows = asyncio.run(go())
    for key, label in (("probs", "model only"), ("probs_rules", "model + engine trait rules")):
        print(f"Mean change in probability when one trait goes 0.1 -> 0.9 ({len(ids)} agents, {args.backend}, {label}):")
        for trait, qs in sensitivity(rows, key).items():
            for q, opts in qs.items():
                print(f"  {trait:18s} {q:10s} " + "  ".join(f"{o} {v:+.3f}" for o, v in opts.items()))
    if args.json:
        print(json.dumps(rows, indent=1))


def main() -> None:
    p = argparse.ArgumentParser(prog="bellwether")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="start the live dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("population", help="sample and save a population")
    s.add_argument("config", nargs="?", default="general-panel")
    s.add_argument("--size", type=int)
    s.add_argument("--seed", type=int)
    s.add_argument("--show", type=int, default=5)
    s.set_defaults(func=cmd_population)

    for name, func, helptext in (("run", cmd_run, "run an experiment headless (it also shows in the dashboard)"),
                                 ("probe", cmd_probe, "check that each trait moves the model's decisions")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("scenario")
        s.add_argument("--population", default="general-panel")
        s.add_argument("--size", type=int, default=20)
        s.add_argument("--backend", default=DEFAULT_BACKEND, choices=sorted(BACKENDS))
        s.add_argument("--json", action="store_true")
        s.add_argument("--yes-paid", action="store_true", help="confirm a paid jev run")
        s.set_defaults(func=func)
        if name == "run":
            s.add_argument("--population-seed", type=int)
            s.add_argument("--arms")
            s.add_argument("--seeds", type=int, default=1)
            s.add_argument("--sigma", type=float, default=0.15)
        else:
            s.add_argument("--agents", type=int, default=4)
            s.add_argument("--arm", default="baseline")

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
