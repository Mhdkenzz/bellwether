import copy
import math
from collections import Counter
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bellwether.population import generate_population, load_population_config, sample_population
from bellwether.population.categories import missing_categories
from bellwether.population.config import PopulationConfig

ROOT = Path(__file__).resolve().parent.parent
POPS = ROOT / "configs/populations"
NORTHGATE = POPS / "northgate-handwritten.yaml"
WRITTEN = {"school-circle": 25, "northgate-handwritten": 27, "general-panel": 38}


def raw() -> dict:
    return copy.deepcopy(yaml.safe_load(NORTHGATE.read_text())["population"])


def build(data: dict, size: int | None = None, mix: dict | None = None):
    return sample_population(PopulationConfig.model_validate(data), size=size, mix=mix)


def person(data: dict, name: str) -> dict:
    return next(a for a in data["agents"] if a["name"] == name)


@pytest.mark.parametrize("name, count", WRITTEN.items())
def test_every_written_population_loads_complete(name, count):
    pop = sample_population(load_population_config(POPS / f"{name}.yaml"))
    assert pop.size == count
    for a in pop.agents:
        assert missing_categories(a) == [], (a.name, missing_categories(a))
        assert all(k in a.profile for k in ("Health:", "Relationships:", "Background:", "Attitudes:"))
        assert a.community == name


def test_only_listed_relatives_are_family():
    pop = sample_population(load_population_config(NORTHGATE))
    names = {a.id: a.name for a in pop.agents}
    family = {frozenset((names[t.a], names[t.b])) for t in pop.ties if t.label == "family"}
    assert family == {frozenset(p) for p in (("Priya", "Grace"), ("Tomasz", "Viktor"), ("Lucía", "Leilani"),
                                             ("Idris", "Omar"), ("Jonah", "Maureen"), ("Ayesha", "Zainab"))}
    assert all(t.kind == "strong" for t in pop.ties if t.label == "family")


def test_written_acquaintances_replace_random_ones():
    data = raw()
    pop = build(data)
    written = {frozenset((a["name"], o)) for a in data["agents"] for o in a.get("knows", [])}
    names = {a.id: a.name for a in pop.agents}
    weak = {frozenset((names[t.a], names[t.b])) for t in pop.ties if t.kind == "weak"}
    assert weak <= written  # pairs already tied as group/family/close friends aren't repeated
    assert build(raw()).ties == pop.ties  # and nothing random


def test_trait_key_order_does_not_matter():
    data = raw()
    p = person(data, "Priya")
    p["traits"] = dict(reversed(list(p["traits"].items())))
    pop = build(data)
    priya = next(a for a in pop.agents if a.name == "Priya")
    assert list(priya.traits) == list(pop.config.traits)


def test_a_smaller_run_keeps_each_cohorts_share():
    pop = build(raw(), size=9)
    assert Counter(a.cohort for a in pop.agents) == {"junior": 3, "senior": 2, "friend": 1, "family": 2, "staff": 1}
    with pytest.raises(ValueError, match="only 27 people are written"):
        build(raw(), size=30)


def test_a_custom_mix_takes_as_many_as_it_can():
    pop = build(raw(), mix={"junior": 1, "senior": 1})
    assert Counter(a.cohort for a in pop.agents) == {"junior": 6, "senior": 6}
    with pytest.raises(ValueError, match="the most you can run is 12"):
        build(raw(), size=20, mix={"junior": 1, "senior": 1})


@pytest.mark.parametrize("change, message", [
    (lambda d: person(d, "Priya").pop("cause"), "cause"),
    (lambda d: person(d, "Priya").update(favourite_colour="blue"), "favourite_colour"),
    (lambda d: person(d, "Priya").update(platforms=["snapchat"]), "unknown platforms"),
    (lambda d: person(d, "Hana").update(platforms=[]), "posting 'never'"),
    (lambda d: person(d, "Hana").update(life_stage="early career"), "under-18s are students"),
    (lambda d: person(d, "Priya").update(chronotype="morning person"), "chronotype"),
    (lambda d: person(d, "Priya").update(family=["Nobody"]), "not in this population"),
    (lambda d: person(d, "Priya").update(knows=["Nobody"]), "knows 'Nobody'"),
    (lambda d: person(d, "Priya").update(cohort="teacher"), "unknown cohort"),
    (lambda d: person(d, "Mateus").update(name="Priya"), "names must be unique"),
    (lambda d: person(d, "Mateus").update(traits=dict(person(d, "Priya")["traits"])), "near-identical traits"),
    (lambda d: person(d, "Priya")["big_five"].pop("openness"), "big_five"),
])
def test_mistakes_are_caught_with_a_clear_message(change, message):
    data = raw()
    change(data)
    with pytest.raises((ValueError, ValidationError), match=message):
        build(data)


def test_relatives_who_share_a_home_agree_on_area_and_pets():
    for name in ("school-circle", "northgate-handwritten"):
        pop = sample_population(load_population_config(POPS / f"{name}.yaml"))
        for t in pop.ties:
            if t.label != "family":
                continue
            a, b = pop.agent(t.a), pop.agent(t.b)
            shared = "at the school" in a.living + b.living or "at Northgate High" in a.living + b.living
            if shared and "a street away" not in a.living + b.living:
                assert a.location == b.location, (a.name, b.name)


# ------------------------------------------------------------------ everyone together


def test_all_runs_every_written_person_as_one_society():
    pop = sample_population(load_population_config(POPS / "all.yaml"))
    assert pop.size == sum(WRITTEN.values())
    assert Counter(a.community for a in pop.agents) == WRITTEN
    assert len({a.id for a in pop.agents}) == pop.size
    assert len({a.name for a in pop.agents}) == pop.size  # names are unique across communities
    by_id = {a.id: a for a in pop.agents}
    assert all(by_id[t.a].community == by_id[t.b].community for t in pop.ties)
    assert len({a.group for a in pop.agents}) == len({(a.community, a.group.split(":")[1]) for a in pop.agents})


def test_all_with_fewer_people_or_another_proportion():
    cfg = load_population_config(POPS / "all.yaml")
    small = sample_population(cfg, size=30)
    assert Counter(a.community for a in small.agents) == {"school-circle": 8, "northgate-handwritten": 9,
                                                         "general-panel": 13}
    assert small.name != "all"  # a partial run is saved under its own key
    students = sample_population(cfg, mix={"school-circle": 1, "northgate-handwritten": 1})
    assert Counter(a.community for a in students.agents) == {"school-circle": 25, "northgate-handwritten": 25}
    with pytest.raises(ValueError, match="the most you can run is 25"):
        sample_population(cfg, size=30, mix={"school-circle": 1})


def test_parse_mix_forms():
    from bellwether.population.mix import parse_mix

    parts = ["a", "b", "c"]
    assert parse_mix("", parts) is None
    assert parse_mix("25:27:38", parts) == {"a": 25, "b": 27, "c": 38}
    assert parse_mix("50%, 30%, 20%", parts) == {"a": 50, "b": 30, "c": 20}
    assert parse_mix("a=1,c=3", parts) == {"a": 1, "c": 3}
    with pytest.raises(ValueError, match="give 3 numbers"):
        parse_mix("1:2", parts)


def test_run_asks_how_many_and_what_proportion(monkeypatch, capsys):
    from bellwether.__main__ import choose_people

    cfg = load_population_config(POPS / "all.yaml")
    answers = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert choose_people(cfg, None, None, ask=True) == (None, None)
    assert "Most accurate: everyone" in capsys.readouterr().out
    answers = iter(["500", "", "30", "1:1:1"])  # a bad answer is asked again
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    size, mix = choose_people(cfg, None, None, ask=True)
    assert size == 30 and mix == {"school-circle": 1, "northgate-handwritten": 1, "general-panel": 1}
    assert "Try again" in capsys.readouterr().out


def test_scenarios_can_target_a_community():
    import random

    from bellwether.engine.selectors import select
    from bellwether.scenario import Selector

    pop = sample_population(load_population_config(POPS / "all.yaml"))
    chosen = select(Selector(community="northgate-handwritten", cohort="junior"), pop, {}, random.Random(1))
    assert len(chosen) == 9 and all(pop.agent(a).community == "northgate-handwritten" for a in chosen)


# ------------------------------------------------------------------ export and roster


def test_export_round_trips_a_generated_population():
    from bellwether.population.export import to_written

    cfg = load_population_config(POPS / "general-panel.yaml").model_copy(update={"agents": None})
    gen = generate_population(cfg, size=12)
    back = sample_population(cfg.model_copy(update={"agents": to_written(gen)}))
    assert [a.persona for a in back.agents] == [a.persona for a in gen.agents]
    for a, b in zip(gen.agents, back.agents):
        assert math.isclose(a.stress_baseline, b.stress_baseline, abs_tol=0.002)
        assert math.isclose(a.mood_baseline, b.mood_baseline, abs_tol=0.002)
        assert (a.temperament, a.susceptibility) == (b.temperament, b.susceptibility)
    pairs = lambda p: {(frozenset((p.agent(t.a).name, p.agent(t.b).name)), t.kind) for t in p.ties}
    assert pairs(back) == pairs(gen)


def test_roster_is_up_to_date():
    from bellwether.population.roster import ROSTER_PATH, render_roster

    text, total = render_roster()
    assert total == sum(WRITTEN.values())
    assert ROSTER_PATH.read_text() == text, "run: python -m bellwether roster"
