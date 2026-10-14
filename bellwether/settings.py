"""Project paths and environment loading."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("BELLWETHER_HOME", Path(__file__).resolve().parent.parent))

POPULATION_CONFIG_DIR = ROOT / "configs" / "populations"
POPULATION_DIR = ROOT / "populations"
SCENARIO_DIR = Path(os.environ.get("BELLWETHER_SCENARIO_DIR", ROOT / "scenarios"))
RUNS_DIR = ROOT / "runs"
CACHE_PATH = ROOT / ".cache" / "decisions.sqlite"


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=value lines from .env without overriding the real environment."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str, default: str | None = None) -> str | None:
    load_dotenv()
    value = os.environ.get(name)
    return value if value else default
