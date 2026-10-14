import asyncio

from bellwether.backends import FakeBackend
from bellwether.engine import EventBus, RunConfig, run_once
from bellwether.engine.rules import Context, blocked_options, summarize_shifts, trait_shifts
from bellwether.engine.runstate import AgentState, World


def ctx(ps=0.5, tf=0.5, rt=0.5, si=0.5, budget=100, pos=0, neg=0, n=0, acquired=0, disappointed=False):
    return Context(traits={"price_sensitivity": ps, "trend_following": tf, "risk_tolerance": rt,
                           "social_influence": si},
                   budget_left=budget, n_signals=n, n_positive=pos, n_negative=neg, n_acquired=acquired,
                   disappointed=disappointed)


def act(scenario, c, world=None):
    world = world or World.from_scenario(scenario)
    return summarize_shifts(trait_shifts(scenario.decisions["action"], c, world))


def test_price_sensitive_people_pull_away_from_buying(scenario):
    low, high = act(scenario, ctx(ps=0.1, budget=50)), act(scenario, ctx(ps=0.9, budget=50))
    assert high["get"] < low["get"] - 1.0
    assert high["pass"] > low["pass"]


def test_discount_pulls_price_sensitive_people_in(scenario):
    world = World.from_scenario(scenario)
    full = act(scenario, ctx(ps=0.9, budget=200), world)["get"]
    world.items["item"].price = 30  # 25% off
    assert act(scenario, ctx(ps=0.9, budget=200), world)["get"] > full + 0.5


def test_circle_moves_trend_followers_not_independents(scenario):
    praise = dict(pos=6, n=6, acquired=3)
    warn = dict(neg=6, n=6)
    follower_up = act(scenario, ctx(tf=0.9, **praise))["get"] - act(scenario, ctx(tf=0.9))["get"]
    follower_down = act(scenario, ctx(tf=0.9, **warn))["get"] - act(scenario, ctx(tf=0.9))["get"]
    loner_up = act(scenario, ctx(tf=0.05, **praise))["get"] - act(scenario, ctx(tf=0.05))["get"]
    assert follower_up > 1.5 and follower_down < -1.5
    assert abs(loner_up) < 0.25


def test_cautious_people_lean_to_waiting(scenario):
    assert act(scenario, ctx(rt=0.1))["wait"] > act(scenario, ctx(rt=0.9))["wait"]
    assert act(scenario, ctx(rt=0.9))["get"] > act(scenario, ctx(rt=0.1))["get"]


def test_quiet_people_post_less_and_disappointed_people_complain(scenario):
    share = scenario.decisions["share"]
    world = World.from_scenario(scenario)
    quiet = summarize_shifts(trait_shifts(share, ctx(si=0.05), world))
    loud = summarize_shifts(trait_shifts(share, ctx(si=0.95), world))
    assert quiet["quiet"] > loud["quiet"]
    sad = summarize_shifts(trait_shifts(share, ctx(disappointed=True), world))
    assert sad["knock"] > 0 > sad["praise"]


def test_blocked_options(scenario):
    world = World.from_scenario(scenario)
    spec = scenario.decisions["action"]
    assert blocked_options(spec, scenario, world, AgentState(budget_left=100)) == {}
    assert blocked_options(spec, scenario, world, AgentState(budget_left=10)) == {"get": "priced_out"}
    world.items["item"].stock = 0
    assert blocked_options(spec, scenario, world, AgentState(budget_left=100)) == {"get": "sold_out"}
    assert blocked_options(spec, scenario, world, AgentState(budget_left=100, holdings={"item": 1})) == {
        "get": "already_owned"}


def _run(population, scenario, trait_rules=None):
    bus = EventBus()
    cfg = RunConfig("t", "baseline", 0, 1, concurrency=8, trait_rules=trait_rules)
    return asyncio.run(run_once(population, scenario, FakeBackend(), bus, cfg)), bus


def test_nobody_chooses_to_buy_what_is_sold_out(population, scenario):
    r, bus = _run(population, scenario)
    sold_out_after = None
    for ev in bus.history:
        if ev["type"] == "round_finished" and ev["world"]["item"]["stock"] <= 0 and sold_out_after is None:
            sold_out_after = ev["round"]
        if ev["type"] == "agent_decided" and sold_out_after and ev["round"] > sold_out_after:
            assert ev["choices"].get("action") != "get"
    assert r.metrics["item.missed_out"] <= scenario.market_size


def test_raw_mode_has_no_shifts(population, scenario, tmp_path):
    import json
    bus = EventBus(tmp_path)
    asyncio.run(run_once(population, scenario, FakeBackend(), bus,
                         RunConfig("t", "baseline", 0, 1, concurrency=8, trait_rules=False)))
    bus.close()
    recs = [json.loads(l) for l in (tmp_path / "traces.jsonl").read_text().splitlines()]
    assert all(a.get("shifts") is None for r in recs for a in r["answers"].values() if "noisy" in a)


def test_events_cannot_push_choices(population, scenario, tmp_path):
    import json

    import pytest
    from pydantic import ValidationError

    from bellwether.scenario.models import EventSpec

    with pytest.raises(ValidationError, match="events can't push choices"):
        EventSpec.model_validate({"round": 1, "text": "x", "sway": {"act": 1.0}})
    bus = EventBus(tmp_path)
    asyncio.run(run_once(population, scenario, FakeBackend(), bus, RunConfig("t", "insiders", 0, 1, concurrency=8)))
    bus.close()
    recs = [json.loads(l) for l in (tmp_path / "traces.jsonl").read_text().splitlines()]
    shifts = [s for r in recs for a in r["answers"].values() for s in (a.get("shifts") or {}).values()]
    assert shifts and not any("event" in s for s in shifts)  # only the person's own traits and circle move them
