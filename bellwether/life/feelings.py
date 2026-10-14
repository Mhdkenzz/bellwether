"""How a person feels, and how that changes through the day."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..population import Agent


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Feelings:
    mood: float  # -1 miserable .. +1 elated
    energy: float  # 0 exhausted .. 1 full of energy
    stress: float  # 0 relaxed .. 1 overwhelmed
    hunger: float  # 0 full .. 1 starving
    social_need: float  # 0 wants to be alone .. 1 craving company

    @classmethod
    def wake_up(cls, agent: Agent, sleep_bonus: float = 0.0, previous: "Feelings | None" = None) -> "Feelings":
        chrono = {"early bird": 0.05, "night owl": -0.12}.get(agent.chronotype, 0.0)
        mood = agent.mood_baseline if previous is None else 0.6 * previous.mood + 0.4 * agent.mood_baseline
        stress = agent.stress_baseline if previous is None else 0.7 * previous.stress + 0.3 * agent.stress_baseline
        social = 0.5 if previous is None else previous.social_need
        return cls(mood=_clip(mood, -1, 1), energy=_clip(0.8 + chrono + sleep_bonus), stress=_clip(stress),
                   hunger=0.6, social_need=_clip(social))

    def apply(self, effects: dict[str, float], neuroticism: float = 0.5) -> None:
        """Apply activity effects; anxious people feel stress and bad moods more strongly."""
        amp = 0.7 + 0.6 * neuroticism
        for key, delta in effects.items():
            if (key == "stress" and delta > 0) or (key == "mood" and delta < 0):
                delta *= amp
            if key == "mood":
                self.mood = _clip(self.mood + delta, -1, 1)
            else:
                setattr(self, key, _clip(getattr(self, key) + delta))

    def drift(self, agent: Agent, socialised: bool) -> None:
        """What happens to anyone as time passes: tiredness, hunger, loneliness, mood settling."""
        e = agent.big_five.get("extraversion", 0.5)
        self.energy = _clip(self.energy - 0.06)
        self.hunger = _clip(self.hunger + 0.2)
        if not socialised:
            self.social_need = _clip(self.social_need + 0.05 + 0.2 * e)
        self.stress = _clip(self.stress - 0.03)
        self.mood = _clip(self.mood + 0.15 * (agent.mood_baseline - self.mood), -1, 1)
        if self.hunger > 0.8:
            self.mood = _clip(self.mood - 0.05, -1, 1)
        if self.energy < 0.2:
            self.mood = _clip(self.mood - 0.04, -1, 1)
            self.stress = _clip(self.stress + 0.03)

    def words(self, agent: Agent) -> str:
        mood = ("miserable" if self.mood < -0.5 else "a bit down" if self.mood < -0.15 else "okay"
                if self.mood < 0.15 else "in a good mood" if self.mood < 0.5 else "really happy")
        energy = ("exhausted" if self.energy < 0.2 else "tired" if self.energy < 0.45 else "fine"
                  if self.energy < 0.75 else "full of energy")
        stress = "very stressed" if self.stress > 0.7 else "a bit stressed" if self.stress > 0.45 else "relaxed"
        parts = [mood, energy, stress]
        if self.hunger > 0.7:
            parts.append("hungry")
        if self.social_need > 0.7:
            parts.append("craving company")
        elif self.social_need < 0.2:
            parts.append("wants some time alone")
        return ", ".join(parts)

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in asdict(self).items()}
