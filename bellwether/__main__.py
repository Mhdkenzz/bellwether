"""Command line: `python -m bellwether serve | population | export | roster | run | probe`."""

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


def _parts(cfg) -> dict[str, int]:
    """The parts a run's proportion is set over: communities for a combined config, else cohorts."""
    from collections import Counter

    from .population.combine import available

    if cfg.include:
        return available(cfg)
    if cfg.agents:
        return dict(Counter(a.get("cohort") or "-" for a in cfg.agents))
    return {}


def choose_people(cfg, size: int | None, mix_text: str | None, ask: bool) -> tuple[int | None, dict | None]:
    """How many people and in what proportion. Asks on a terminal unless both were given."""
    from .population.mix import parse_mix, plan_counts

    parts = _parts(cfg)
    if not parts:  # generated population: any size, cohort shares from the config
        if ask and size is None:
            answer = input(f"How many people to generate? [Enter = {cfg.size}]: ").strip()
            size = int(answer) if answer else None
        return size, parse_mix(mix_text, [c.name for c in cfg.cohorts]) if mix_text else None
    names = list(parts)
    total = sum(parts.values())
    if ask and (size is None or mix_text is None):
        kind = "community" if cfg.include else "cohort"
        print(f"\nPeople written for {cfg.name}, by {kind}:")
        for name, n in parts.items():
            print(f"  {name:24s} {n:4d}")
        print(f"  {'total':24s} {total:4d}")
        print("Most accurate: everyone, in their natural mix (the biggest sample, with nobody over- or "
              "under-represented).")
        while True:
            try:
                if size is None:
                    answer = input(f"How many people? [Enter = all {total}]: ").strip()
                    size = int(answer) if answer else None
                if mix_text is None:
                    natural = ":".join(str(n) for n in parts.values())
                    mix_text = input(f"Proportion {' : '.join(names)} [Enter = natural {natural}]: ").strip()
                mix = parse_mix(mix_text, names)
                counts = plan_counts(parts, size, mix)
                break
            except ValueError as e:
                print(f"  {e}. Try again.")
                size, mix_text = None, None
        print("-> " + ", ".join(f"{k} {v}" for k, v in counts.items() if v) + f" ({sum(counts.values())} people)")
        return size, mix
    mix = parse_mix(mix_text, names)
    plan_counts(parts, size, mix)  # fail early with a clear message
    return size, mix


def _estimate(scenario, n: int, arms: int, seeds: int, backend: str) -> str:
    per_person = len(scenario.decisions) + (4 if scenario.life else 0)
    calls = n * scenario.rounds * per_person * arms * seeds
    note = f"~{calls} model calls before caching"
    if backend == "gemma":
        note += f" (about {calls * 8 / 3600:.1f} h at ~8 s per call on this machine)"
    return note


def cmd_population(args: argparse.Namespace) -> None:
    from .population import load_population_config, sample_population

    cfg = load_population_config(POPULATION_CONFIG_DIR / f"{args.config}.yaml")
    size, mix = choose_people(cfg, args.size, args.mix, ask=False)
    pop = sample_population(cfg, size=size, seed=args.seed, mix=mix)
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
    cfg = load_population_config(POPULATION_CONFIG_DIR / f"{args.population}.yaml")
    size, mix = choose_people(cfg, args.size, args.mix, ask=sys.stdin.isatty() and not args.yes)
    pop = sample_population(cfg, size=size, seed=args.population_seed, mix=mix)
    pop.save(POPULATION_DIR)
    backend = make_backend(args.backend)
    spec = ExperimentSpec(population=pop.key, scenario=scenario.name, backend=args.backend,
                          arms=args.arms.split(",") if args.arms else None, seeds=args.seeds, sigma=args.sigma)
    exp = Experiment(spec, pop, scenario, backend)
    print(f"Running {pop.size} people from {pop.name} on {args.backend}: "
          + _estimate(scenario, pop.size, len(exp.arms), args.seeds, args.backend))

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


def cmd_export(args: argparse.Namespace) -> None:
    from .population import generate_population, load_population_config
    from .population.export import to_written, write_agents

    path = POPULATION_CONFIG_DIR / f"{args.config}.yaml"
    pop = generate_population(load_population_config(path), size=args.size)
    write_agents(path, to_written(pop), "Written out from the generator")
    print(f"wrote {pop.size} people into {path}; read them and fix anything that doesn't ring true (see guide.md)")


def cmd_roster(args: argparse.Namespace) -> None:
    from .population.roster import ROSTER_PATH, write_roster

    n = write_roster()
    print(f"{n} people -> {ROSTER_PATH}")


def cmd_probe(args: argparse.Namespace) -> None:
    from .population import load_population_config, sample_population
    from .population.mix import parse_mix
    from .probe import probe_traits, sensitivity
    from .scenario import load_scenario

    _check_paid(args)
    scenario = load_scenario(SCENARIO_DIR / f"{args.scenario}.yaml")
    pop = sample_population(load_population_config(POPULATION_CONFIG_DIR / f"{args.population}.yaml"), size=args.size,
                            mix=parse_mix(args.mix, []) if args.mix and "=" in args.mix else None)
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

    s = sub.add_parser("population", help="build a population (written people, combined, or generated) and save it")
    s.add_argument("config", nargs="?", default="all")
    s.add_argument("--size", type=int)
    s.add_argument("--mix", help="proportion, e.g. 25:27:38 or school-circle=50,general-panel=50")
    s.add_argument("--seed", type=int)
    s.add_argument("--show", type=int, default=5)
    s.set_defaults(func=cmd_population)

    s = sub.add_parser("export", help="write a generated population into its file as written people")
    s.add_argument("config")
    s.add_argument("--size", type=int)
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("roster", help="write every written person into docs/all-agents.md")
    s.set_defaults(func=cmd_roster)

    for name, func, helptext in (("run", cmd_run, "run an experiment headless (it also shows in the dashboard)"),
                                 ("probe", cmd_probe, "check that each trait moves the model's decisions")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("scenario")
        s.add_argument("--population", default="all", help="population file; 'all' = everyone written")
        s.add_argument("--size", type=int, help="how many people (asked on a terminal; default everyone)")
        s.add_argument("--mix", help="proportion, e.g. 25:27:38 or school-circle=50,general-panel=50")
        s.add_argument("--backend", default=DEFAULT_BACKEND, choices=sorted(BACKENDS))
        s.add_argument("--json", action="store_true")
        s.add_argument("--yes-paid", action="store_true", help="confirm a paid jev run")
        s.set_defaults(func=func)
        if name == "run":
            s.add_argument("--yes", action="store_true", help="don't ask; use --size/--mix or everyone")
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
