import random

import pytest

from bellwether.engine.selectors import select
from bellwether.expr import ExprError, evaluate
from bellwether.scenario import Selector


def test_expressions():
    env = {"a": 2, "items": {"x": {"sold": 30, "stock": 50}}}
    assert evaluate("a * 3 + 1", env) == 7
    assert evaluate("items.x.sold / items.x.stock", env) == 0.6
    assert evaluate("items['x']['sold'] >= 30 and a < 3", env) is True
    assert evaluate("clamp(1.4)", env) == 1.0
    assert evaluate("1 if a > 1 else 0", env) == 1
    assert evaluate("a / 0", env) == 0.0


@pytest.mark.parametrize("bad", ["__import__('os')", "a.__class__", "(lambda: 1)()", "[x for x in a]", "nope + 1"])
def test_unsafe_expressions_rejected(bad):
    with pytest.raises(ExprError):
        evaluate(bad, {"a": {"b": 1}})


def test_selector_conditions(population):
    flags = {a.id: set() for a in population.agents}
    first = population.agents[0].id
    flags[first].add("vip")
    rng = random.Random(0)
    assert select(Selector(flag="vip"), population, flags, rng) == {first}
    assert first not in select(Selector(not_flag="vip"), population, flags, rng)
    assert len(select(Selector.model_validate("all"), population, flags, rng)) == population.size


def test_selector_fraction_is_seeded(population):
    flags = {a.id: set() for a in population.agents}
    a = select(Selector(fraction=0.25), population, flags, random.Random("s"))
    b = select(Selector(fraction=0.25), population, flags, random.Random("s"))
    assert a == b and len(a) == 5


def test_selector_include_groups(population):
    flags = {a.id: set() for a in population.agents}
    seed = population.agents[0]
    flags[seed.id].add("x")
    got = select(Selector(flag="x", include_groups=True), population, flags, random.Random(0))
    assert got == set(population.group_members(seed.group))
