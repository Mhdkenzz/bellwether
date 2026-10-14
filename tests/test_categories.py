from pathlib import Path

import pytest

from bellwether.population import generate_population, load_population_config
from bellwether.population.categories import CATEGORY_GROUPS, missing_categories

ROOT = Path(__file__).resolve().parent.parent


def test_there_are_ten_groups():
    assert len(CATEGORY_GROUPS) == 10


@pytest.mark.parametrize("config", ["general-panel", "school-circle"])
@pytest.mark.parametrize("size", [20, 150])
def test_every_agent_fills_every_category(config, size):
    pop = generate_population(load_population_config(ROOT / f"configs/populations/{config}.yaml"), size=size)
    for a in pop.agents:
        assert missing_categories(a) == [], (a.name, missing_categories(a))


def test_new_groups_are_consistent():
    pop = generate_population(load_population_config(ROOT / "configs/populations/school-circle.yaml"), size=150)
    for a in pop.agents:
        if a.age < 18:
            assert a.relationship not in ("married", "divorced", "widowed", "in a long-term relationship")
            assert a.health not in ("has a bad back", "managing a long-term condition")
        if "partner" in a.living:
            assert a.relationship in ("in a long-term relationship", "married")
        assert all(k in a.profile for k in ("Health:", "Relationships:", "Background:", "Attitudes:"))
        if a.health == "recovering from a sports injury":
            assert a.fitness in ("very active, works out most days", "fairly active")
        if a.life_stage != "student":
            assert "exams and grades" not in a.worries


@pytest.mark.parametrize("config", ["general-panel", "school-circle"])
def test_profiles_have_no_contradictions(config):
    from bellwether.population import pools
    pop = generate_population(load_population_config(ROOT / f"configs/populations/{config}.yaml"), size=150)
    for a in pop.agents:
        minor_home = a.age < 18 or "high school" in a.occupation.lower()
        if minor_home:
            assert "halls" not in a.living and "flat" not in a.living, a.living
            assert not set(a.worries) & pools.ADULT_ONLY_WORRIES, a.worries
        if a.age < 35:
            assert a.goal_long not in pools.ADULT_ONLY_DREAMS
        if "dog" in a.quirk:
            assert "dog" in a.pets
        if a.quirk == "never posts but reads everything" and a.platforms:
            assert a.posting in ("rarely", "never")
        if not a.platforms:
            assert "being judged online" not in a.worries
            assert a.media_habit not in pools.MEDIA_NEEDS_PLATFORM
        if a.relationship == "married":
            assert "partner" in a.living
        if a.cohort == "family":
            assert any(w in a.living for w in ("teenager", "kids", "niece")), a.living


def test_less_repetition():
    from collections import Counter
    pop = generate_population(load_population_config(ROOT / "configs/populations/school-circle.yaml"), size=20)
    for field in ("goal_short", "goal_long", "music", "food"):
        top = Counter(getattr(a, field) for a in pop.agents).most_common(1)[0][1]
        assert top <= 4, (field, top)


@pytest.mark.parametrize("config", ["general-panel", "school-circle"])
def test_dreams_and_worries_fit_their_age(config):
    from bellwether.population import pools
    pop = generate_population(load_population_config(ROOT / f"configs/populations/{config}.yaml"), size=150)
    for a in pop.agents:
        assert pools.fits_age(pools.DREAM_AGES, a.goal_long, a.age), (a.name, a.age, a.goal_long)
        for w in a.worries:
            assert pools.fits_age(pools.WORRY_AGES, w, a.age), (a.name, a.age, w)
        if a.life_stage == "retired":
            assert "job security" not in a.worries and "save for retirement" != a.goal_short
