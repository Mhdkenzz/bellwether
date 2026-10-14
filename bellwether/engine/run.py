"""One run: a population living through a scenario arm, round by round."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from ..backends import BackendError, DecisionBackend, DecisionResponse
from ..population import Population
from ..scenario import DecisionSpec, Scenario
from . import rules as engine_rules
from .decide import resolve_choice, seeded_rng, wire_question
from .events import EventBus
from .metrics import compute_metrics
from .runstate import AgentState, MemoryEntry, Signal, World
from .selectors import agent_env, select
from .social import deliver, render_signal
from .state import build_state

TONE = {"positive": 1, "negative": -1}


@dataclass
class RunConfig:
    experiment_id: str
    arm: str
    run_index: int
    seed: int
    sigma: float = 0.15
    concurrency: int = 1
    char_budget: int | None = None
    trait_rules: bool | None = None  # None = use the scenario's setting; False = raw model


@dataclass
class RunResult:
    arm: str
    run_index: int
    seed: int
    metrics: dict[str, Any]
    rounds: list[dict[str, Any]]
    agents: dict[str, dict[str, Any]]
    calls: int = 0
    cached: int = 0
    errors: int = 0
    cost: float = 0.0
    seconds: float = 0.0
    flags: dict[str, int] = field(default_factory=dict)


def people_weight(population: Population, scenario: Scenario) -> float:
    """How many real people each agent stands for (scenario market size / agent count)."""
    return (scenario.market_size or population.size) / population.size


def _option_text(spec: DecisionSpec, option: str) -> str:
    return spec.options[option].text.rstrip(".")


class Runner:
    def __init__(self, population: Population, scenario: Scenario, backend: DecisionBackend, bus: EventBus, cfg: RunConfig):
        self.pop = population
        self.sc = scenario
        self.backend = backend
        self.bus = bus
        self.cfg = cfg
        self.weight = people_weight(population, scenario)
        self.world = World.from_scenario(scenario)
        self.states = {a.id: AgentState(budget_left=a.budget) for a in population.agents}
        self.char_budget = cfg.char_budget or backend.state_char_budget
        self.sem = asyncio.Semaphore(max(1, cfg.concurrency))
        self.calls = self.cached = self.errors = 0
        self.cost = 0.0
        tr = scenario.trait_rules
        self.rules_on = tr.enabled if cfg.trait_rules is None else cfg.trait_rules
        self.rules_strength = tr.strength
        self.block_infeasible = tr.block_infeasible
        self._blocked_wants: list[tuple[str, str, str]] = []
        self.life = None
        if scenario.life:
            from ..life.engine import LifeEngine
            self.life = LifeEngine(self)

    # ---- helpers -------------------------------------------------------------
    def _tag(self) -> dict[str, Any]:
        return {"experiment": self.cfg.experiment_id, "arm": self.cfg.arm, "run": self.cfg.run_index}

    def _flags(self) -> dict[str, set[str]]:
        return {aid: st.flags for aid, st in self.states.items()}

    def _world_snapshot(self) -> dict[str, Any]:
        return {name: {"label": it.label, "price": it.price, "stock": it.stock, "initial_stock": it.initial_stock,
                       "sold": round(it.sold, 2), "missed_out": round(it.missed_out, 2),
                       "priced_out": round(it.priced_out, 2)}
                for name, it in self.world.items.items()}

    def _init_state(self) -> None:
        # Initial flags are drawn from the population seed, so every run and arm starts identical.
        for i, init in enumerate(self.sc.initial_state):
            rng = seeded_rng("init", self.pop.seed, i, init.flag)
            count = round(init.count / self.weight) if init.count is not None else None
            for aid in select(init.select, self.pop, self._flags(), rng, count=count):
                st = self.states[aid]
                st.flags.add(init.flag)
                if init.memory:
                    st.memory.append(MemoryEntry(0, "seed", init.memory, tone=0))

    # ---- one agent -----------------------------------------------------------
    async def _ask(self, aid: str, round_: int, specs: dict[str, DecisionSpec],
                   events_seen: list[str], extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Ask one agent, then immediately resolve and publish their choices (stock comes later)."""
        agent, st, cfg = self.pop.agent(aid), self.states[aid], self.cfg
        state, meta = build_state(agent, st, self.pop, self.sc, self.world, round_, events_seen, self.states,
                                  self.char_budget, extra=extra)
        wire = {qid: wire_question(spec) for qid, spec in specs.items()}
        if self.block_infeasible:
            for qid, spec in specs.items():
                gone = engine_rules.blocked_options(spec, self.sc, self.world, st)
                if gone and spec.type == "choice" and len(spec.options) - len(gone) >= 2:
                    wire[qid]["criteria"] = {k: v for k, v in wire[qid]["criteria"].items() if k not in gone}
        async with self.sem:
            self.bus.emit("agent_thinking", **self._tag(), round=round_, agent=aid)
            started = time.perf_counter()
            try:
                resp: DecisionResponse | BackendError = await self.backend.decide(state, wire)
            except BackendError as e:
                resp = e
            elapsed = (time.perf_counter() - started) * 1000

        record: dict[str, Any] = {**self._tag(), "round": round_, "agent": aid, "state_meta": meta,
                                  "latency_ms": round(elapsed, 1)}
        if isinstance(resp, BackendError):
            self.errors += 1
            record["error"] = str(resp)
            prev = st.choices.get(round_ - 1, {})
            st.choices[round_] = {q: prev[q] for q in specs if q in prev}
            self.bus.emit("agent_error", **self._tag(), round=round_, agent=aid, error=str(resp)[:300])
            self.bus.trace({**record, "state": state, "questions": wire})
            return None

        self.calls += 1
        self.cached += resp.cached
        self.cost += resp.cost
        answers: dict[str, Any] = {}
        st.choices[round_], st.scores[round_] = {}, {}
        ctx = engine_rules.context(agent, st, round_)
        for qid, spec in specs.items():
            ans = resp.answers.get(qid)
            if ans is None:
                continue
            if spec.type == "choice":
                parts = engine_rules.trait_shifts(spec, ctx, self.world) if self.rules_on else {}
                blocked = (engine_rules.blocked_options(spec, self.sc, self.world, st)
                           if self.block_infeasible else {})
                res = resolve_choice(qid, spec, ans, self.sc, cfg.sigma,
                                     seeded_rng(cfg.seed, "noise", aid, round_, qid), self._rule_env(aid),
                                     trait_shifts=engine_rules.summarize_shifts(parts) if parts else None,
                                     strength=self.rules_strength, blocked=blocked)
                res["shifts"] = engine_rules.describe(parts) or None
                st.choices[round_][qid] = res["choice"]
                answers[qid] = res
                wanted = res["wanted"]
                if wanted != res["choice"] and wanted in blocked and blocked[wanted] != "already_owned":
                    self._blocked_wants.append((aid, spec.options[wanted].consume.item, blocked[wanted]))
            else:
                value = ans.score if spec.type == "score" else ans.noul
                if value is None:
                    continue
                st.scores[round_][qid] = float(value)
                if spec.role == "sentiment":
                    st.sentiment = float(value)
                answers[qid] = {"value": float(value), "raw": ans.probabilities or None, "confidence": ans.confidence}
        record.update({"answers": answers, "cached": resp.cached, "input_tokens": resp.input_tokens,
                       "truncated": resp.truncated, "cost": resp.cost})
        self.bus.trace({**record, "state": state, "questions": wire})
        self.bus.emit("agent_decided", **self._tag(), round=round_, agent=aid,
                      choices=st.choices[round_], scores=st.scores[round_],
                      probs={q: a["noisy"] for q, a in answers.items() if "noisy" in a},
                      model_probs={q: a["raw"] for q, a in answers.items() if "noisy" in a},
                      wanted={q: a["wanted"] for q, a in answers.items() if a.get("wanted") and a["wanted"] != a["choice"]},
                      flipped=[q for q, a in answers.items() if a.get("flipped")],
                      cached=resp.cached, latency_ms=record["latency_ms"],
                      signals_received=meta["signals_received"], signals_shown=meta["signals_shown"],
                      truncated=resp.truncated, trimmed=meta["trimmed"], calls=self.calls, cost=round(self.cost, 6))
        return record

    def _rule_env(self, aid: str) -> dict[str, Any]:
        agent, st = self.pop.agent(aid), self.states[aid]
        inbox = st.inbox
        pos = sum(s.polarity == "positive" for s in inbox)
        neg = sum(s.polarity == "negative" for s in inbox)
        env = agent_env(agent, st.flags)
        env.update({
            "budget_left": st.budget_left,
            "n_signals": len(inbox),
            "n_positive": pos,
            "n_negative": neg,
            "positive_share": pos / len(inbox) if inbox else 0.0,
            "n_acquired_signals": sum(s.acquired for s in inbox),
            "vars": self.world.vars,
        })
        for name, it in self.world.items.items():
            env[f"price_{name}"] = it.price
            env[f"price_change_{name}"] = (it.price - it.initial_price) / it.initial_price if it.initial_price else 0.0
            env[f"stock_left_{name}"] = it.stock if it.stock is not None else float("inf")
        return env

    # ---- one round -----------------------------------------------------------
    def _apply_events(self, round_: int, events: list, seen: dict[str, list[str]], log: list[dict[str, Any]]) -> None:
        cfg = self.cfg
        for ev in events:
            j = len(log)
            changes = self.world.apply(ev.effects)
            who = select(ev.visible_to, self.pop, self._flags(), seeded_rng(cfg.seed, "event", round_, j, ev.text))
            for aid in who:
                seen[aid].append(ev.text)
                self.states[aid].flags.update(ev.set_flags)
                self.states[aid].flags.add("aware")
            log.append({"text": ev.text, "visible_to": len(who), "changes": changes, "slot": ev.slot,
                        "audience": sorted(who)})

    def _scenario_asks(self, round_: int) -> dict[str, dict[str, DecisionSpec]]:
        asks: dict[str, dict[str, DecisionSpec]] = {}
        order = list(self.sc.decisions)
        for qid, spec in self.sc.decisions.items():
            eligible = (select(spec.ask_if, self.pop, self._flags(), seeded_rng(self.cfg.seed, "ask", round_, qid))
                        if spec.ask_if else {a.id for a in self.pop.agents})
            for aid in eligible:
                asks.setdefault(aid, {})[qid] = spec
        return {aid: dict(sorted(sp.items(), key=lambda kv: order.index(kv[0]))) for aid, sp in sorted(asks.items())}

    async def _scenario_step(self, round_: int, asks: dict[str, dict[str, DecisionSpec]], seen: dict[str, list[str]],
                             extra: dict[str, dict[str, Any]] | None = None) -> tuple[dict, dict]:
        tasks = [self._ask(aid, round_, specs, seen[aid], (extra or {}).get(aid)) for aid, specs in asks.items()]
        decided = {rec["agent"]: rec for rec in await asyncio.gather(*tasks) if rec}
        outcomes = self._resolve_consumption(round_, decided)
        return decided, outcomes

    def _finish_round(self, round_: int, seen: dict[str, list[str]], decided: dict, outcomes: dict,
                      spread: bool = True) -> dict[str, Any]:
        inbox_seen = {aid: st.inbox for aid, st in self.states.items()}
        signals = self._spread(round_, decided, outcomes) if spread else []
        if not spread:
            for aid in decided:
                self.states[aid].inbox = []
        self._remember(round_, seen, decided, outcomes, inbox_seen)
        summary = self._round_summary(round_, decided, outcomes, signals)
        self.bus.emit("round_finished", **self._tag(), **summary, agent_outcomes=outcomes)
        return summary

    async def _round(self, round_: int) -> dict[str, Any]:
        if self.life is not None:
            return await self.life.run_day(round_)
        seen: dict[str, list[str]] = {a.id: [] for a in self.pop.agents}
        event_log: list[dict[str, Any]] = []
        self._apply_events(round_, self.sc.events_for(self.cfg.arm, round_), seen, event_log)
        asks = self._scenario_asks(round_)
        self.bus.emit("round_started", **self._tag(), round=round_, events=event_log, world=self._world_snapshot(),
                      asked=sorted(asks))
        decided, outcomes = await self._scenario_step(round_, asks, seen)
        return self._finish_round(round_, seen, decided, outcomes)

    def _resolve_consumption(self, round_: int, decided: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Buyers arrive in a seeded random order and take stock until it runs out."""
        wants = []
        for aid in decided:
            for qid, option in self.states[aid].choices.get(round_, {}).items():
                opt = self.sc.decisions[qid].options.get(option)
                if opt and opt.consume:
                    wants.append((aid, qid, option, opt.consume))
        rng = seeded_rng(self.cfg.seed, "arrival", round_)
        wants.sort(key=lambda w: w[0])
        rng.shuffle(wants)
        outcomes: dict[str, dict[str, Any]] = {}
        # Agents who wanted an option that was blocked (sold out / unaffordable) are unmet demand.
        for aid, item_name, reason in sorted(self._blocked_wants):
            item = self.world.items[item_name]
            seen_set = item.missed_out_agents if reason == "sold_out" else item.priced_out_agents
            if aid not in seen_set:
                seen_set.add(aid)
                if reason == "sold_out":
                    item.missed_out += self.weight
                else:
                    item.priced_out += self.weight
            outcomes[aid] = {"item": item_name, "result": "missed_out" if reason == "sold_out" else "priced_out",
                             "blocked": True}
        self._blocked_wants = []
        for aid, qid, option, consume in wants:
            st, item = self.states[aid], self.world.items[consume.item]
            spec = self.sc.items[consume.item]
            if st.holdings.get(consume.item, 0) >= spec.max_per_agent:
                outcomes[aid] = {"item": consume.item, "result": "already_owned"}
                continue
            cost = item.price * consume.qty
            if cost > st.budget_left + 1e-9:
                if aid not in item.priced_out_agents:
                    item.priced_out += self.weight
                    item.priced_out_agents.add(aid)
                outcomes[aid] = {"item": consume.item, "result": "priced_out"}
                continue
            if item.stock is not None and item.stock <= 1e-9:
                if aid not in item.missed_out_agents:
                    item.missed_out += self.weight
                    item.missed_out_agents.add(aid)
                outcomes[aid] = {"item": consume.item, "result": "missed_out"}
                continue
            want = self.weight * consume.qty
            got = want if item.stock is None else min(want, item.stock)
            if item.stock is not None:
                item.stock -= got
            item.sold += got
            fraction = got / want if want else 1.0
            if fraction < 1:
                if aid not in item.missed_out_agents:
                    item.missed_out += self.weight * (1 - fraction)
                    item.missed_out_agents.add(aid)
            st.holdings[consume.item] = st.holdings.get(consume.item, 0) + consume.qty
            st.budget_left -= cost
            st.flags.add(f"has:{consume.item}")
            st.flags.update(self.sc.decisions[qid].options[option].set_flags)
            outcomes[aid] = {"item": consume.item, "result": "acquired", "fraction": round(fraction, 3)}
        # Options without consumption may still set flags.
        for aid in decided:
            for qid, option in self.states[aid].choices.get(round_, {}).items():
                opt = self.sc.decisions[qid].options.get(option)
                if opt and not opt.consume:
                    self.states[aid].flags.update(opt.set_flags)
        for aid, out in outcomes.items():
            self.states[aid].outcome[round_] = out
        return outcomes

    def _spread(self, round_: int, decided: dict[str, dict[str, Any]], outcomes: dict[str, dict[str, Any]]) -> list[Signal]:
        signal_q = next((q for q, s in self.sc.decisions.items() if s.role == "signal"), None)
        new_inbox: dict[str, list[Signal]] = {a.id: [] for a in self.pop.agents}
        sent: list[Signal] = []
        for aid in sorted(decided):
            st = self.states[aid]
            polarity = "none"
            if signal_q and signal_q in st.choices.get(round_, {}):
                polarity = self.sc.decisions[signal_q].options[st.choices[round_][signal_q]].signal or "none"
            out = outcomes.get(aid, {})
            sigs = deliver(self.pop, aid, round_, polarity, out.get("result") == "acquired",
                           out.get("result") == "missed_out", st.sentiment,
                           seeded_rng(self.cfg.seed, "reach", aid, round_))
            for s in sigs:
                new_inbox[s.receiver].append(s)
            sent += sigs
        for aid, st in self.states.items():
            st.inbox = new_inbox[aid]
        return sent

    def _remember(self, round_: int, seen: dict[str, list[str]], decided: dict[str, dict[str, Any]],
                  outcomes: dict[str, dict[str, Any]], inbox_seen: dict[str, list[Signal]]) -> None:
        for aid, st in self.states.items():
            for text in seen[aid]:
                st.memory.append(MemoryEntry(round_, "event", text))
            rec = decided.get(aid)
            if rec:
                # What friends said (and this agent actually took in) becomes memory.
                shown = set(rec["state_meta"]["signals_shown"])
                for s in inbox_seen[aid]:
                    if s.sender in shown:
                        st.memory.append(MemoryEntry(s.round, "signal", render_signal(s, self.pop, self.sc.signal_text),
                                                     tone=TONE.get(s.polarity, 0)))
                parts = []
                out = outcomes.get(aid)
                for qid, option in st.choices.get(round_, {}).items():
                    spec = self.sc.decisions[qid]
                    text = _option_text(spec, option).lower()
                    if any(o.consume for o in spec.options.values()):
                        result = {"acquired": " and got one", "missed_out": " but it had sold out",
                                  "priced_out": " but could not afford it",
                                  "already_owned": " but already had one"}.get((out or {}).get("result", ""), "")
                        parts.append(f"they decided: {text}{result}")
                    elif spec.role == "signal":
                        parts.append(f"they told others: {text}")
                if parts:
                    st.memory.append(MemoryEntry(round_, "own_action", "; ".join(parts) + "."))

    def _round_summary(self, round_: int, decided: dict[str, dict[str, Any]], outcomes: dict[str, dict[str, Any]],
                       signals: list[Signal]) -> dict[str, Any]:
        choice_counts: dict[str, dict[str, int]] = {}
        score_means: dict[str, float] = {}
        for qid, spec in self.sc.decisions.items():
            if spec.type == "choice":
                counts = {o: 0 for o in spec.options}
                for aid in decided:
                    c = self.states[aid].choices.get(round_, {}).get(qid)
                    if c:
                        counts[c] += 1
                choice_counts[qid] = counts
            else:
                vals = [self.states[aid].scores.get(round_, {}).get(qid) for aid in decided]
                vals = [v for v in vals if v is not None]
                if vals:
                    score_means[qid] = round(sum(vals) / len(vals), 4)
        results: dict[str, int] = {}
        for out in outcomes.values():
            results[out["result"]] = results.get(out["result"], 0) + 1
        flips = sum(1 for r in decided.values() for a in r["answers"].values() if isinstance(a, dict) and a.get("flipped"))
        return {
            "round": round_,
            "asked": len(decided),
            "choices": choice_counts,
            "scores": score_means,
            "outcomes": results,
            "signals": {"sent": len(signals), "positive": sum(s.polarity == "positive" for s in signals),
                        "negative": sum(s.polarity == "negative" for s in signals)},
            "world": self._world_snapshot(),
            "flips": flips,
            "calls": self.calls,
            "cached": self.cached,
            "errors": self.errors,
            "cost": round(self.cost, 6),
        }

    # ---- whole run -----------------------------------------------------------
    async def run(self) -> RunResult:
        started = time.perf_counter()
        self._init_state()
        self.bus.emit("run_started", **self._tag(), seed=self.cfg.seed, weight=self.weight,
                      flags={aid: sorted(st.flags) for aid, st in self.states.items() if st.flags},
                      world=self._world_snapshot())
        rounds = []
        for r in range(1, self.sc.rounds + 1):
            rounds.append(await self._round(r))
        metrics = compute_metrics(self.pop, self.sc, self.world, self.states, self.weight)
        agents = {
            aid: {"choices": st.choices, "scores": st.scores, "outcome": st.outcome, "flags": sorted(st.flags),
                  "holdings": st.holdings, "sentiment": st.sentiment, "budget_left": st.budget_left}
            for aid, st in self.states.items()
        }
        flag_counts: dict[str, int] = {}
        for st in self.states.values():
            for f in st.flags:
                flag_counts[f] = flag_counts.get(f, 0) + 1
        result = RunResult(arm=self.cfg.arm, run_index=self.cfg.run_index, seed=self.cfg.seed, metrics=metrics,
                           rounds=rounds, agents=agents, calls=self.calls, cached=self.cached, errors=self.errors,
                           cost=round(self.cost, 6), seconds=round(time.perf_counter() - started, 2),
                           flags=flag_counts)
        self.bus.emit("run_finished", **self._tag(), metrics=metrics, calls=self.calls, cached=self.cached,
                      errors=self.errors, cost=result.cost, seconds=result.seconds)
        return result


async def run_once(population: Population, scenario: Scenario, backend: DecisionBackend, bus: EventBus,
                   cfg: RunConfig) -> RunResult:
    return await Runner(population, scenario, backend, bus, cfg).run()
