import asyncio
import json
import random

from bellwether.backends import FakeBackend
from bellwether.engine import EventBus, RunConfig, run_once
from bellwether.engine.decide import apply_rules, argmax, perturb
from bellwether.engine.runstate import MemoryEntry, Signal
from bellwether.engine.social import inbox_capacity, render_memory, select_inbox
from bellwether.experiment import Experiment, ExperimentSpec
from bellwether.scenario import SignalText


def run(population, scenario, arm="baseline", seed=1, sigma=0.15, backend=None, bus=None, char_budget=None,
        trait_rules=None):
    cfg = RunConfig(experiment_id="t", arm=arm, run_index=0, seed=seed, sigma=sigma, concurrency=8,
                    char_budget=char_budget, trait_rules=trait_rules)
    return asyncio.run(run_once(population, scenario, backend or FakeBackend(), bus or EventBus(), cfg))


# --- decision math ----------------------------------------------------------

def test_noise_is_seeded_and_zero_sigma_is_identity():
    p = {"a": 0.5, "b": 0.3, "c": 0.2}
    assert perturb(p, 0, random.Random(1)) == p
    assert perturb(p, 0.15, random.Random("x")) == perturb(p, 0.15, random.Random("x"))


def test_noise_flips_close_calls_not_clear_ones():
    clear, close = {"a": 0.81, "b": 0.18, "c": 0.01}, {"a": 0.48, "b": 0.45, "c": 0.07}
    flips_clear = sum(argmax(perturb(clear, 0.15, random.Random(i)), list(clear)) != "a" for i in range(500))
    flips_close = sum(argmax(perturb(close, 0.15, random.Random(i)), list(close)) != "a" for i in range(500))
    assert flips_clear == 0
    assert 100 < flips_close < 300


def test_argmax_tie_goes_to_first_option():
    assert argmax({"x": 0.5, "y": 0.5}, ["y", "x"]) == "y"


def test_rules_shift_probabilities():
    p = {"buy": 0.5, "skip": 0.5}
    out = apply_rules(p, {"buy": "2 * price_sensitivity"}, 0.5, {"price_sensitivity": 1.0})
    assert out["buy"] > 0.7


# --- social inputs shaped by traits ------------------------------------------

def test_trend_followers_take_in_more_signals(population):
    assert inbox_capacity(0.0) == 2 and inbox_capacity(1.0) == 8
    sender = population.agents[1].id
    inbox = [Signal(sender, "a001", 1, "positive", True, False, 0.9, "strong", "close friend", 1.0)] * 10
    lines_low, tally_low, _ = select_inbox(inbox, 0.1, population, SignalText())
    lines_high, tally_high, _ = select_inbox(inbox, 0.9, population, SignalText())
    assert len(lines_low) < len(lines_high)
    assert tally_low and "more people" in tally_low


def test_memory_is_capped_with_tally():
    mem = [MemoryEntry(r, "signal", f"thing {r}", tone=1 if r % 2 else -1) for r in range(1, 13)]
    lines = render_memory(mem, limit=8)
    assert len(lines) == 9 and lines[0].startswith("Earlier: 4 things")


# --- full runs ----------------------------------------------------------------

def test_run_is_deterministic(population, scenario):
    a, b = run(population, scenario), run(population, scenario)
    assert a.metrics == b.metrics
    assert a.agents == b.agents


def test_stock_and_scaling(population, scenario):
    r = run(population, scenario, arm="discount")
    weight = scenario.market_size / population.size  # 5 people per agent
    assert weight == 5
    sold = r.metrics["item.sold"]
    assert 0 <= sold <= 30
    assert sold == round(sold / weight) * weight or r.metrics["item.sold_out"]
    for rnd in r.rounds:
        assert rnd["world"]["item"]["stock"] >= -1e-9


def test_owners_are_not_asked_again(population, scenario):
    bus = EventBus()
    run(population, scenario, bus=bus)
    owners: set[str] = set()
    checked = 0
    for ev in bus.history:
        if ev["type"] == "agent_decided" and ev["agent"] in owners:
            assert "action" not in ev["choices"]
            checked += 1
        if ev["type"] == "round_finished":
            owners |= {aid for aid, out in ev["agent_outcomes"].items() if out["result"] == "acquired"}
    assert owners and checked


def test_unaffordable_option_is_not_offered(population, scenario, tmp_path):
    scenario.items["item"].price = 10_000
    bus = EventBus(tmp_path)
    r = run(population, scenario, bus=bus, trait_rules=False)
    bus.close()
    assert r.metrics["item.sold"] == 0
    recs = [json.loads(l) for l in (tmp_path / "traces.jsonl").read_text().splitlines()]
    asked = [rec for rec in recs if "action" in rec["questions"]]
    assert asked and all("get" not in rec["questions"]["action"]["criteria"] for rec in asked)
    assert all(any("CANNOT afford" in f for f in rec["state"]["hard_facts"]) for rec in asked)


def test_variant_event_only_reaches_selected_agents(population, scenario):
    bus = EventBus()
    r = run(population, scenario, arm="insiders", bus=bus)
    started = [e for e in bus.history if e["type"] == "round_started" and e["round"] == 2][0]
    reach = started["events"][0]["visible_to"]
    fans = r.flags.get("early_fan", 0)
    assert fans <= reach < population.size
    assert r.flags.get("saw_preview") == reach


def test_paired_arms_share_initial_state(population, scenario):
    bus_a, bus_b = EventBus(), EventBus()
    run(population, scenario, arm="baseline", bus=bus_a)
    run(population, scenario, arm="discount", bus=bus_b)
    fa = [e for e in bus_a.history if e["type"] == "run_started"][0]["flags"]
    fb = [e for e in bus_b.history if e["type"] == "run_started"][0]["flags"]
    assert fa == fb and fa


def test_state_fits_budget(population, scenario, tmp_path):
    bus = EventBus(tmp_path)
    run(population, scenario, bus=bus, char_budget=1800)
    bus.close()
    for line in (tmp_path / "traces.jsonl").read_text().splitlines():
        rec = json.loads(line)
        assert rec["state_meta"]["chars"] <= 1800 or rec["state_meta"]["trimmed"]["circle"] > 0


def test_states_contain_traits_and_circle(population, scenario, tmp_path):
    bus = EventBus(tmp_path)
    run(population, scenario, bus=bus)
    bus.close()
    recs = [json.loads(l) for l in (tmp_path / "traces.jsonl").read_text().splitlines()]
    assert all("traits" in r["state"] and "person" in r["state"] for r in recs)
    assert any("your_circle" in r["state"] for r in recs if r["round"] > 1)


def test_experiment_end_to_end(population, scenario, tmp_path):
    spec = ExperimentSpec(population=population.key, scenario=scenario.name, backend="fake", seeds=2)
    exp = Experiment(spec, population, scenario, FakeBackend(), root=tmp_path)
    summary = asyncio.run(exp.run())
    assert exp.status == "finished"
    assert set(summary["arms"]) == {"baseline", "discount", "insiders"}
    assert summary["arms"]["baseline"]["runs"] == 2
    assert "item.sold" in summary["deltas"]["discount"]
    assert (exp.dir / "results.json").exists() and (exp.dir / "events.jsonl").exists()
