import itertools
import math

from bellwether.population import CORE_TRAITS, sample_population
from bellwether.population.graph import group_sizes
from bellwether.population import pools
import random


def test_same_seed_same_people(panel_config):
    a = sample_population(panel_config)
    b = sample_population(panel_config)
    assert a.model_dump() == b.model_dump()


def test_different_seed_different_people(panel_config):
    a = sample_population(panel_config, seed=1)
    b = sample_population(panel_config, seed=2)
    assert [x.persona for x in a.agents] != [x.persona for x in b.agents]


def test_every_agent_is_distinct(population, population_150):
    for pop in (population, population_150):
        assert len({a.name for a in pop.agents}) == pop.size
        assert len({a.persona for a in pop.agents}) == pop.size
        sigs = {(a.occupation, tuple(sorted(a.interests))) for a in pop.agents}
        assert len(sigs) == pop.size


def test_trait_vectors_are_spread_apart(population, panel_config):
    gap = min(math.dist(list(a.traits.values()), list(b.traits.values()))
              for a, b in itertools.combinations(population.agents, 2))
    assert gap >= panel_config.min_trait_distance


def test_traits_cover_core_and_stay_in_range(population_150):
    for a in population_150.agents:
        assert set(CORE_TRAITS) <= set(a.traits)
        assert all(0 < v < 1 for v in a.traits.values())


def test_trait_affinities_avoid_clear_persona_contradictions(population_150):
    tables = [pools.SHOPPING_STYLES, pools.MEDIA_HABITS, pools.DECISION_STYLES, pools.QUIRK_AFFINITY]
    for agent in population_150.agents:
        for table, field in zip(tables, ("shopping_style", "media_habit", "decision_style", "quirk")):
            affinity = table.get(getattr(agent, field), {})
            score = sum(sign * (2 * agent.traits.get(name, 0.5) - 1) for name, sign in affinity.items())
            assert score >= -0.75


def test_segments_follow_their_rules(population_150):
    for a in population_150.agents:
        assert ("trend_follower" in a.segments) == (a.traits["trend_following"] >= 0.66)
        assert ("price_sensitive" in a.segments) == (a.traits["price_sensitivity"] >= 0.66)


def test_students_rarely_rich(population_150):
    students = [a for a in population_150.agents if a.life_stage == "student"]
    assert students
    assert sum(a.income == "high" for a in students) / len(students) < 0.2


def test_group_sizes_respect_bounds():
    rng = random.Random(0)
    for n in range(3, 200):
        sizes = group_sizes(n, 3, 6, rng)
        assert sum(sizes) == n
        assert all(3 <= s <= 6 for s in sizes)


def test_everyone_has_ties_and_a_group(population_150):
    for a in population_150.agents:
        assert a.group
        assert population_150.neighbors(a.id)
    for t in population_150.ties:
        if t.kind == "strong":
            assert population_150.agent(t.a).group == population_150.agent(t.b).group


def test_save_and_load_roundtrip(population, tmp_path):
    from bellwether.population import Population

    path = population.save(tmp_path)
    loaded = Population.load(path)
    assert loaded.model_dump() == population.model_dump()
    assert loaded.neighbors(population.agents[0].id) == population.neighbors(population.agents[0].id)
