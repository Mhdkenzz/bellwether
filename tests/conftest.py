from __future__ import annotations

from pathlib import Path

import pytest

from bellwether.population import generate_population, load_population_config
from bellwether.scenario import load_scenario

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def panel_config():
    return load_population_config(ROOT / "configs" / "populations" / "general-panel.yaml")


@pytest.fixture(scope="session")
def population(panel_config):
    return generate_population(panel_config)


@pytest.fixture(scope="session")
def population_150(panel_config):
    return generate_population(panel_config, size=150)


@pytest.fixture()
def scenario():
    return load_scenario(FIXTURES / "limited-release.yaml")
