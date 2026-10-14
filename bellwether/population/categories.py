"""The 10 description groups every agent is built from.

USE THESE CATEGORIES WHEN MAKING AGENTS. Every sampled person must have every category
below filled in, and anything new about a person belongs in one of these groups (or a new
group added here). `tests/test_categories.py` fails if any agent is missing one, so this
list is the single source of truth for what a complete person looks like.

How to make agents (hand-written or sampled): guide.md at the project root.

Each entry maps a category name to the Agent field that holds it.
"""

from __future__ import annotations

from typing import Any

from .models import Agent

CATEGORY_GROUPS: dict[str, dict[str, str]] = {
    "1. Identity": {
        "First name": "name", "Age": "age", "Life stage": "life_stage", "Occupation": "occupation",
        "Location": "location",
    },
    "2. Money": {
        "Income band": "income", "Spending money": "budget",
    },
    "3. Personality": {
        "Decision traits": "traits", "Big Five": "big_five", "Introvert / ambivert / extrovert": "personality_type",
        "Temperament": "temperament", "Chronotype": "chronotype", "How easily swayed": "susceptibility",
    },
    "4. Habits and tastes": {
        "Interests": "interests", "Values": "values", "Shopping style": "shopping_style", "Media habit": "media_habit",
        "Decision style": "decision_style", "Quirk": "quirk", "Music": "music", "Favourite food": "food",
    },
    "5. Life situation": {
        "Living situation": "living", "Short-term goal": "goal_short", "Long-term dream": "goal_long",
        "Worries": "worries", "What's going on right now": "life_context",
    },
    "6. Social life": {
        "Social platforms": "platforms", "Posting frequency": "posting",
    },
    "7. Health and wellbeing": {
        "Health": "health", "Sleep": "sleep", "Fitness": "fitness",
    },
    "8. Relationships and home": {
        "Relationship status": "relationship", "Pets": "pets", "Family closeness": "family_closeness",
    },
    "9. Background": {
        "Where they grew up": "hometown", "Money growing up": "family_money", "Formative experience": "formative",
    },
    "10. Attitudes and beliefs": {
        "Money mindset": "money_mindset", "Attitude to brands": "brand_attitude", "Attitude to tech": "tech_attitude",
        "Cause they care about": "cause",
    },
}

# Fields that may legitimately be empty for some people (e.g. no social media at all).
MAY_BE_EMPTY = {"platforms"}


def missing_categories(agent: Agent) -> list[str]:
    """Names of categories this agent has no value for (should always be empty)."""
    out = []
    for group, cats in CATEGORY_GROUPS.items():
        for label, field in cats.items():
            value: Any = getattr(agent, field, None)
            if field in MAY_BE_EMPTY:
                continue
            if value is None or value == "" or value == [] or value == {}:
                out.append(f"{group} / {label}")
    return out


def describe_categories() -> str:
    """Human-readable list of the 10 groups (used in docs and the dashboard)."""
    return "\n".join(f"{g}: " + ", ".join(cats) for g, cats in CATEGORY_GROUPS.items())
