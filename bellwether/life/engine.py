"""Daily life: every scenario round is a day lived slot by slot.

Per slot: scenario events land -> everyone chooses what to do (model + needs/personality
rules + noise) -> money and feelings change -> people who end up together talk (mood
spreads, relationships shift, opinions travel speaker -> listener) -> people post and
scroll -> time passes. Scenario decisions happen in the `decide_at` slot with the whole
day as context. Influence only travels through these real contacts, never by broadcast.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from ..backends import BackendError
from ..engine.decide import argmax, perturb, seeded_rng, shift
from ..engine.rules import summarize_shifts
from ..engine.runstate import MemoryEntry, Signal
from ..engine.social import render_memory
from .config import Activity, Slot, load_life
from .feelings import Feelings
from .rules import activity_shifts
from .social import Gathering, Post, feed_for, form_gatherings, influence_strength, talkativeness

if TYPE_CHECKING:
    from ..engine.run import Runner

QID = "activity"


class LifeEngine:
    def __init__(self, runner: "Runner"):
        self.r = runner
        self.cfg = load_life(runner.sc.life)
        if runner.sc.decide_at not in {s.id for s in self.cfg.slots}:
            raise ValueError(f"decide_at {runner.sc.decide_at!r} is not a slot of life config {self.cfg.name!r}")
        self.pop = runner.pop
        self.feel = {a.id: Feelings.wake_up(a) for a in self.pop.agents}
        self.sleep_bonus = {a.id: 0.0 for a in self.pop.agents}
        self.affinity: dict[tuple[str, str], float] = {}
        for t in self.pop.ties:
            self.affinity[(t.a, t.b)] = 0.7 if t.label == "family" else 0.55 if t.kind == "strong" else 0.2
        self.posts: list[Post] = []
        self.today: dict[str, list[str]] = {}
        first_item = next(iter(runner.world.items.values()), None)
        self.topic = runner.sc.topic or (first_item.label if first_item else "what's going on")
        self.platform_labels = {k: v.label for k, v in self.pop.config.social_media.platforms.items()}

    # ---- relationships & stance -------------------------------------------------------
    def aff(self, a: str, b: str) -> float:
        return self.affinity.get(tuple(sorted((a, b))), 0.0)

    def bump(self, a: str, b: str, delta: float) -> None:
        k = tuple(sorted((a, b)))
        self.affinity[k] = max(-1.0, min(1.0, self.affinity.get(k, 0.0) + delta))

    def stance(self, aid: str) -> str | None:
        """What this person would say about the scenario topic right now."""
        sc, st = self.r.sc, self.r.states[aid]
        signal_q = next((q for q, s in sc.decisions.items() if s.role == "signal"), None)
        if signal_q:
            for r in sorted(st.choices, reverse=True):
                opt = st.choices[r].get(signal_q)
                if opt:
                    return sc.decisions[signal_q].options[opt].signal or None
        return "neutral" if "aware" in st.flags else None

    def tie(self, a: str, b: str) -> tuple[str, str]:
        for other, t in self.pop.neighbors(a):
            if other == b:
                return t.kind, t.label
        return "none", "someone they don't know"

    # ---- state shown to the model for a life choice -------------------------------------
    def life_state(self, aid: str, day: int, slot: Slot) -> dict[str, Any]:
        agent, st, f = self.pop.agent(aid), self.r.states[aid], self.feel[aid]
        budget = self.r.char_budget
        mind = []
        if "aware" in st.flags:
            s = self.stance(aid)
            mind.append(f"Everyone's talking about {self.topic}." + (f" Their own view: {s}." if s else ""))
        mind += [line for line in render_memory(st.memory, unit="Day")[-4:]]
        sym = self.r.sc.currency_symbol
        facts = [f"They have {sym}{st.budget_left:.0f} to spend. Anything that costs more is impossible."]
        duty = slot.obligations.get(agent.life_stage)
        if duty:
            facts.append(duty)
        if f.energy < 0.2:
            facts.append("They are exhausted.")
        if f.hunger > 0.8:
            facts.append("They are very hungry.")
        state: dict[str, Any] = {
            "person": agent.profile if agent.profile and budget >= 4000 else agent.persona,
            "right_now": [f"Day {day}, {slot.label}.", f"Feeling {f.words(agent)}."],
            "today_so_far": self.today[aid][-6:] or ["Nothing yet - the day is just starting."],
        }
        if mind:
            state["on_their_mind"] = mind
        state["hard_facts"] = facts
        while len(json.dumps(state)) > budget and (state.get("on_their_mind") or len(state["today_so_far"]) > 1):
            if state.get("on_their_mind"):
                state["on_their_mind"].pop()
                if not state["on_their_mind"]:
                    state.pop("on_their_mind")
            else:
                state["today_so_far"].pop(0)
        return state

    # ---- one agent's everyday choice ----------------------------------------------------
    async def choose(self, aid: str, day: int, slot: Slot) -> Activity:
        r, agent, st = self.r, self.pop.agent(aid), self.r.states[aid]
        offered = slot.offered(agent.life_stage)
        blocked = {a.id for a in offered if a.cost > st.budget_left + 1e-9}
        question = {"type": "choice",
                    "instructions": f"It's {slot.label.lower()}. What does {agent.name} most likely do?",
                    "criteria": {a.id: a.text for a in offered if a.id not in blocked}
                    or {a.id: a.text for a in offered}}
        state = self.life_state(aid, day, slot)
        async with r.sem:
            r.bus.emit("agent_thinking", **r._tag(), round=day, agent=aid, kind="life", slot=slot.id)
            t0 = time.perf_counter()
            try:
                resp = await r.backend.decide(state, {QID: question})
                raw = resp.answers[QID].probabilities
                r.calls += 1
                r.cached += resp.cached
                r.cost += resp.cost
                error = None
            except (BackendError, KeyError) as e:
                raw, resp, error = {}, None, str(e)
                r.errors += 1
            ms = (time.perf_counter() - t0) * 1000
        order = [a.id for a in offered]
        probs = {k: float(raw.get(k, 0.0)) for k in order}
        z = sum(probs.values())
        probs = {k: v / z for k, v in probs.items()} if z > 0 else {k: 1 / len(order) for k in order}
        parts = {a.id: activity_shifts(a, agent, self.feel[aid], slot.id) for a in offered} if r.rules_on else {}
        adjusted = shift(probs, summarize_shifts(parts), r.rules_strength) if parts else probs
        noisy = perturb(adjusted, r.cfg.sigma, seeded_rng(r.cfg.seed, "life", aid, day, slot.id))
        feasible = [k for k in order if k not in blocked] or order
        pick = argmax(noisy, feasible)
        act = next(a for a in offered if a.id == pick)
        r.bus.trace({**r._tag(), "kind": "life", "round": day, "slot": slot.id, "agent": aid, "state": state,
                     "questions": {QID: question}, "error": error, "latency_ms": round(ms, 1),
                     "cached": bool(resp and resp.cached),
                     "answers": {QID: {"raw": probs, "adjusted": adjusted, "noisy": noisy, "choice": pick,
                                       "shifts": {k: v for k, v in parts.items() if v} or None,
                                       "blocked": {b: "costs too much" for b in blocked} or None}},
                     "feelings": self.feel[aid].to_dict()})
        r.bus.emit("life_decided", **r._tag(), round=day, slot=slot.id, agent=aid, activity=pick, text=act.text,
                   place=act.place, probs=noisy, model_probs=probs, cached=bool(resp and resp.cached),
                   latency_ms=round(ms, 1), feelings=self.feel[aid].to_dict(), error=error,
                   calls=r.calls, cost=round(r.cost, 6))
        return act

    # ---- consequences --------------------------------------------------------------------
    def live_out(self, aid: str, act: Activity, slot: Slot) -> None:
        agent, st, f = self.pop.agent(aid), self.r.states[aid], self.feel[aid]
        if act.cost and st.budget_left >= act.cost:
            st.budget_left -= act.cost
        if act.money:
            st.budget_left += act.money
        f.apply(act.effects, agent.big_five.get("neuroticism", 0.5))
        if slot.id == self.cfg.slots[-1].id:
            self.sleep_bonus[aid] = act.sleep

    def converse(self, g: Gathering, day: int, slot: Slot, choices: dict[str, Activity], rng) -> None:
        members = g.members
        names = {m: self.pop.agent(m).name for m in members}
        if len(members) < 2:
            m = members[0]
            act = choices[m]
            if act.social:  # wanted company, found nobody
                e = self.pop.agent(m).big_five.get("extraversion", 0.5)
                self.feel[m].apply({"mood": -0.03 - 0.05 * e})
                self.today[m].append(f"{slot.label}: {act.text.lower()} - but nobody was free.")
            else:
                self.today[m].append(f"{slot.label}: {act.text.lower()}.")
            return
        # being together: company, energy, shared mood
        avg = sum(self.feel[m].mood for m in members) / len(members)
        for m in members:
            e = self.pop.agent(m).big_five.get("extraversion", 0.5)
            f = self.feel[m]
            f.social_need = max(0.0, f.social_need - (0.25 + 0.25 * e))
            f.apply({"energy": 0.04 if e > 0.6 else -0.03 * (len(members) - 1) * (1 - e), "mood": 0.05 * (e - 0.3)})
            f.mood = max(-1.0, min(1.0, f.mood + 0.25 * (avg - f.mood)))
            for o in members:
                if o > m:
                    self.bump(m, o, 0.02)
        stances = {m: self.stance(m) for m in members}
        talkers = [m for m in members if stances[m] in ("positive", "neutral", "negative")]
        said: list[str] = []
        if talkers and rng.random() < 0.8:
            g.topic = self.topic
            for speaker in talkers:
                if rng.random() >= talkativeness(self.pop, speaker):
                    continue
                pol = stances[speaker]
                sp_state = self.r.states[speaker]
                for listener in members:
                    if listener == speaker:
                        continue
                    kind, label = self.tie(speaker, listener)
                    if kind == "none":
                        label = f"met at {g.place}"
                    strength = influence_strength(self.pop, speaker, listener, self.aff(speaker, listener))
                    channel = "in the group chat" if g.place == "online" else f"in person at {g.place}"
                    last = sp_state.outcome.get(max(sp_state.outcome) if sp_state.outcome else 0, {})
                    self.r.states[listener].inbox.append(Signal(
                        sender=speaker, receiver=listener, round=day, polarity=pol,
                        acquired=any(sp_state.holdings.values()), missed_out=last.get("result") == "missed_out",
                        sentiment=sp_state.sentiment, tie_kind=kind, tie_label=label, weight=strength, channel=channel))
                    self.r.states[listener].flags.add("aware")
                    g.influences.append({"from": speaker, "to": listener, "polarity": pol, "strength": strength,
                                         "channel": channel})
                    if stances[listener] in ("positive", "negative") and stances[listener] != pol and pol != "neutral":
                        a = self.pop.agent(listener).big_five.get("agreeableness", 0.5)
                        self.bump(speaker, listener, -0.04 * (1 - a))
                    elif stances[listener] == pol:
                        self.bump(speaker, listener, 0.02)
                said.append(f"{names[speaker]} was {'hyping' if pol == 'positive' else 'knocking' if pol == 'negative' else 'talking about'} {self.topic}")
        for m in members:
            others = ", ".join(names[o] for o in members if o != m)
            line = f"{slot.label}: {choices[m].text.lower()} (with {others})"
            mine = [s for s in said if not s.startswith(names[m] + " ")]
            if mine:
                line += "; " + "; ".join(mine)
            self.today[m].append(line + ".")

    def media(self, day: int, slot: Slot, choices: dict[str, Activity], rng) -> tuple[list[dict], list[dict]]:
        posts_out, views_out = [], []
        for aid, act in sorted(choices.items()):
            agent = self.pop.agent(aid)
            if act.media in ("post", "both") and agent.platforms:
                platform = rng.choice(agent.platforms)
                stance = self.stance(aid) if rng.random() < 0.75 else None
                post = Post(id=f"p{len(self.posts) + 1}", author=aid, platform=platform, day=day, slot=slot.id,
                            stance=stance)
                self.posts.append(post)
                posts_out.append({"id": post.id, "author": aid, "platform": platform, "stance": stance})
                about = f"about {self.topic}" if stance else "a life update"
                self.today[aid].append(f"{slot.label}: posted {about} on {self.platform_labels[platform]}.")
        recent = [p for p in self.posts if p.day >= day - 1]
        for aid, act in sorted(choices.items()):
            if act.media not in ("scroll", "both"):
                continue
            seen = feed_for(aid, recent, self.pop, rng)
            if not seen:
                continue
            on_topic = 0
            for p in seen:
                if not p.stance:
                    continue
                on_topic += 1
                spec = self.pop.config.social_media.platforms[p.platform]
                kind, label = self.tie(p.author, aid)
                if kind == "none":
                    label = f"someone on {spec.label}"
                strength = influence_strength(self.pop, p.author, aid, max(0.1, self.aff(p.author, aid)), spec.weight)
                a_state = self.r.states[p.author]
                self.r.states[aid].inbox.append(Signal(
                    sender=p.author, receiver=aid, round=day, polarity=p.stance,
                    acquired=any(a_state.holdings.values()), missed_out=False, sentiment=a_state.sentiment,
                    tie_kind=kind, tie_label=label, weight=strength, channel=f"on {spec.label}"))
                self.r.states[aid].flags.add("aware")
                views_out.append({"post": p.id, "from": p.author, "to": aid, "platform": p.platform,
                                  "polarity": p.stance, "strength": strength})
            self.today[aid].append(f"{slot.label}: scrolled and saw {len(seen)} posts"
                                   + (f", {on_topic} about {self.topic}." if on_topic else "."))
        return posts_out, views_out

    # ---- the day ----------------------------------------------------------------------
    async def run_day(self, day: int) -> dict[str, Any]:
        r = self.r
        if day > 1:
            self.feel = {a.id: Feelings.wake_up(a, self.sleep_bonus[a.id], self.feel[a.id]) for a in self.pop.agents}
        self.today = {a.id: [] for a in self.pop.agents}
        seen_all: dict[str, list[str]] = {a.id: [] for a in self.pop.agents}
        event_log: list[dict[str, Any]] = []
        todays = r.sc.events_for(r.cfg.arm, day)
        r.bus.emit("round_started", **r._tag(), round=day, events=[{"text": e.text, "slot": e.slot or self.cfg.slots[0].id,
                                                                     "visible_to": None} for e in todays],
                   world=r._world_snapshot(), asked=[a.id for a in self.pop.agents],
                   slots=[{"id": s.id, "label": s.label} for s in self.cfg.slots],
                   feelings={aid: f.to_dict() for aid, f in self.feel.items()})
        decided: dict = {}
        outcomes: dict = {}
        for slot in self.cfg.slots:
            rng = seeded_rng(r.cfg.seed, "slot", day, slot.id)
            slot_seen = {a.id: [] for a in self.pop.agents}
            here = [e for e in todays if (e.slot or self.cfg.slots[0].id) == slot.id]
            before = len(event_log)
            r._apply_events(day, here, slot_seen, event_log)
            for aid, texts in slot_seen.items():
                seen_all[aid] += texts
                self.today[aid] += [f"{slot.label}: heard that {t[0].lower() + t[1:]}" for t in texts]
            r.bus.emit("slot_started", **r._tag(), round=day, slot=slot.id, label=slot.label,
                       events=event_log[before:])
            acts = await asyncio.gather(*(self.choose(a.id, day, slot) for a in self.pop.agents))
            choices = {a.id: act for a, act in zip(self.pop.agents, acts)}
            for aid, act in choices.items():
                self.live_out(aid, act, slot)
            gatherings = form_gatherings(choices, self.pop, rng, slot.id, day)
            for g in gatherings:
                self.converse(g, day, slot, choices, rng)
            posts, views = self.media(day, slot, choices, rng)
            scenario_round = None
            if slot.id == r.sc.decide_at:
                asks = r._scenario_asks(day)
                extra = {aid: {"how_they_feel": self.feel[aid].words(self.pop.agent(aid)),
                               "today_so_far": self.today[aid][-6:]} for aid in asks}
                decided, outcomes = await r._scenario_step(day, asks, seen_all, extra)
                for aid, out in outcomes.items():
                    if out["result"] == "acquired":
                        self.feel[aid].apply({"mood": 0.2, "stress": -0.05})
                        self.today[aid].append(f"{slot.label}: got {self.topic}!")
                    elif out["result"] in ("missed_out", "priced_out"):
                        self.feel[aid].apply({"mood": -0.2, "stress": 0.1},
                                             self.pop.agent(aid).big_five.get("neuroticism", 0.5))
                        self.today[aid].append(f"{slot.label}: wanted {self.topic} but "
                                               + ("it had sold out." if out["result"] == "missed_out"
                                                  else "couldn't afford it."))
                scenario_round = {"decided": len(decided), "outcomes": outcomes}
            for g in gatherings:
                socialised = set(g.members) if len(g.members) > 1 else set()
                for m in g.members:
                    self.feel[m].drift(self.pop.agent(m), m in socialised)
            counts: dict[str, int] = {}
            for act in choices.values():
                counts[act.id] = counts.get(act.id, 0) + 1
            r.bus.emit("slot_finished", **r._tag(), round=day, slot=slot.id, label=slot.label,
                       activities={aid: act.id for aid, act in choices.items()},
                       places={aid: act.place for aid, act in choices.items()},
                       counts=counts, gatherings=[g.to_dict() for g in gatherings if len(g.members) > 1],
                       posts=posts, views=views,
                       feelings={aid: f.to_dict() for aid, f in self.feel.items()},
                       scenario=scenario_round, calls=r.calls, cost=round(r.cost, 6))
        for aid in seen_all:
            mood = self.feel[aid].words(self.pop.agent(aid)).split(",")[0]
            r.states[aid].memory.append(MemoryEntry(day, "life", f"ended the day {mood}."))
        return r._finish_round(day, seen_all, decided, outcomes, spread=False)
