import asyncio
import random
from pathlib import Path

import pytest

from bellwether.backends import FakeBackend
from bellwether.engine import EventBus, RunConfig, run_once
from bellwether.life.config import load_life
from bellwether.life.feelings import Feelings
from bellwether.life.rules import activity_shifts
from bellwether.life.social import form_gatherings
from bellwether.population import load_population_config, sample_population
from bellwether.scenario import load_scenario

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def school():
    return sample_population(load_population_config(ROOT / "configs/populations/school-circle.yaml"))


@pytest.fixture(scope="module")
def life():
    return load_life("everyday")


@pytest.fixture(scope="module")
def run_life(school):
    sc = load_scenario(ROOT / "scenarios/hoodie-life.yaml")
    bus = EventBus()
    res = asyncio.run(run_once(school, sc, FakeBackend(), bus, RunConfig("t", "meetup", 0, 1, char_budget=7000)))
    return res, bus


def test_every_agent_is_deep_and_typed(school):
    for a in school.agents:
        assert set(a.big_five) == {"openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"}
        assert a.personality_type in ("introvert", "ambivert", "extrovert")
        assert a.profile and a.living and a.goal_short and len(a.worries) == 2
        assert a.posting == "never" if not a.platforms else a.posting != "never"


def test_platform_membership_varies(school):
    big = sample_population(school.config, size=150)
    counts = {len(a.platforms) for a in big.agents}
    assert counts == {0, 1, 2, 3}


def test_feelings_stay_in_range(school):
    a = school.agents[0]
    f = Feelings.wake_up(a)
    for _ in range(20):
        f.apply({"mood": -0.5, "stress": 0.5, "energy": -0.4, "hunger": 0.5})
        f.drift(a, socialised=False)
    assert -1 <= f.mood <= 1 and all(0 <= x <= 1 for x in (f.energy, f.stress, f.hunger, f.social_need))


def test_needs_and_personality_pull_choices(school, life):
    a = school.agents[0]
    morning = life.slot("morning")
    eat = morning.activities[0]
    hungry, full = Feelings(0, 0.8, 0.2, 0.95, 0.5), Feelings(0, 0.8, 0.2, 0.05, 0.5)
    assert activity_shifts(eat, a, hungry, "morning")["hunger"] > activity_shifts(eat, a, full, "morning")["hunger"]
    evening = life.slot("evening")
    hang = next(x for x in evening.activities if x.id == "hang_out")
    alone = next(x for x in evening.activities if x.id == "hobby_alone")
    intro = a.model_copy(update={"big_five": {**a.big_five, "extraversion": 0.1}})
    extro = a.model_copy(update={"big_five": {**a.big_five, "extraversion": 0.9}})
    f = Feelings(0, 0.7, 0.3, 0.3, 0.5)
    assert sum(activity_shifts(hang, extro, f, "evening").values()) > sum(activity_shifts(hang, intro, f, "evening").values())
    assert sum(activity_shifts(alone, intro, f, "evening").values()) > sum(activity_shifts(alone, extro, f, "evening").values())
    post = next(x for x in evening.activities if x.id == "post_online")
    never = a.model_copy(update={"posting": "never"})
    assert sum(activity_shifts(post, never, f, "evening").values()) < -3


def test_friends_who_go_out_end_up_together(school, life):
    hang = next(x for x in life.slot("evening").activities if x.id == "hang_out")
    hobby = next(x for x in life.slot("evening").activities if x.id == "hobby_alone")
    a = school.agents[0]
    friend = next(o for o, t in school.neighbors(a.id) if t.kind == "strong")
    choices = {x.id: hobby for x in school.agents}
    choices[a.id] = choices[friend] = hang
    gs = form_gatherings(choices, school, random.Random(0), "evening", 1)
    together = [g for g in gs if a.id in g.members][0]
    assert friend in together.members and together.kind == "friends"


def test_life_run_produces_days(run_life):
    res, bus = run_life
    slots = [e for e in bus.history if e["type"] == "slot_finished"]
    assert len(slots) == 12
    assert sum(1 for e in bus.history if e["type"] == "life_decided") == 20 * 12
    assert res.errors == 0


def test_influence_only_through_real_contact(run_life):
    _, bus = run_life
    for e in bus.history:
        if e["type"] != "slot_finished":
            continue
        for g in e["gatherings"]:
            for inf in g["influences"]:
                assert inf["from"] in g["members"] and inf["to"] in g["members"]
        for v in e["views"]:
            assert any(p["id"] == v["post"] for s in bus.history if s["type"] == "slot_finished" for p in s["posts"])


def test_instagram_announcement_reaches_only_instagram_users(school, run_life):
    _, bus = run_life
    started = next(e for e in bus.history if e["type"] == "slot_started" and e["round"] == 1 and e["slot"] == "morning")
    insta = next(ev for ev in started["events"] if "Instagram" in ev["text"])
    assert set(insta["audience"]) == {a.id for a in school.agents if "instagram" in a.platforms}


def test_buying_only_after_seeing_the_drop_live(run_life):
    _, bus = run_life
    for e in bus.history:
        if e["type"] == "agent_decided" and e["round"] == 1:
            assert "action" not in e["choices"]


def test_hard_facts_reach_the_model(run_life):
    res, bus = run_life
    # scenario decisions: affordability spelled out; life choices: money + school-day duty
    from pathlib import Path
    import json
    import tempfile

    from bellwether.engine import EventBus as Bus
    tmp = Path(tempfile.mkdtemp())
    sc = load_scenario(ROOT / "scenarios/hoodie-life.yaml")
    pop = sample_population(load_population_config(ROOT / "configs/populations/school-circle.yaml"))
    b = Bus(tmp)
    asyncio.run(run_once(pop, sc, FakeBackend(), b, RunConfig("t", "baseline", 0, 1, char_budget=7000)))
    b.close()
    recs = [json.loads(l) for l in (tmp / "traces.jsonl").read_text().splitlines()]
    dec = [r for r in recs if r.get("kind") != "life" and "action" in r["questions"]]
    assert dec and all(any("afford" in f or "SOLD OUT" in f or "already own" in f for f in r["state"]["hard_facts"]) for r in dec)
    poor = [r for r in dec if "CANNOT afford" in " ".join(r["state"]["hard_facts"])]
    assert all(r["answers"]["action"]["choice"] != "buy_now" for r in poor)
    school = [r for r in recs if r.get("kind") == "life" and r["slot"] == "day"
              and pop.agent(r["agent"]).life_stage == "student"]
    assert school and all(any("school day" in f for f in r["state"]["hard_facts"]) for r in school)


def test_truancy_is_pulled_down(school, life):
    day = life.slot("day")
    phone = next(a for a in day.activities if a.id == "phone_in_class")
    focus = next(a for a in day.activities if a.id == "focus_class")
    a = school.agents[0]
    f = Feelings(0, 0.7, 0.3, 0.3, 0.5)
    assert sum(activity_shifts(phone, a, f, "day").values()) < sum(activity_shifts(focus, a, f, "day").values())


def test_minors_are_students_and_adults_have_no_exam_week(school):
    big = sample_population(school.config, size=150)
    for a in big.agents:
        if a.age < 18:
            assert a.life_stage == "student"
        if a.life_stage != "student":
            assert "exam week" not in a.life_context
