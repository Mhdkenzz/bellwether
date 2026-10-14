"use strict";
// Bellwether live dashboard: follows the experiment event stream and shows every person live.

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x) => `${Math.round((x || 0) * 100)}%`;
const fmt = (x, d = 2) => (x == null ? "–" : typeof x === "number" ? (Number.isInteger(x) ? String(x) : x.toFixed(d)) : String(x));
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
};
const PALETTE = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--c6)", "var(--c7)", "var(--c8)"];
const TRAITS = [["risk_tolerance", "R", "Risk tolerance"], ["price_sensitivity", "P", "Price sensitivity"],
  ["trend_following", "T", "Trend following"], ["social_influence", "S", "Social influence"]];
const BIG5 = [["openness", "Openness"], ["conscientiousness", "Conscientiousness"], ["extraversion", "Extraversion"],
  ["agreeableness", "Agreeableness"], ["neuroticism", "Neuroticism"]];
const runKey = (arm, run) => `${arm}#${run}`;
const POL_WORD = { positive: "hyped", negative: "knocked", neutral: "mentioned" };

let S = freshState();
let source = null;

function freshState() {
  return {
    exp: null, id: null, status: "idle", agents: {}, runs: {}, liveKey: null, viewKey: null, follow: true,
    per: {}, feed: [], selected: null, summary: null, layout: {}, colors: {}, primary: null, signalQ: null,
    sentimentQ: null, round: null, slots: [], now: null, stats: { calls: 0, cached: 0, errors: 0, cost: 0 },
    t0: null, tLast: null, speaking: new Set(),
  };
}
const run = (k = S.viewKey) => S.runs[k];
const dayOf = (k, d) => ((S.runs[k].days ||= {})[d] ||= { slots: {}, started: {} });
const agentName = (id) => S.agents[id]?.name || id;
const shortSlot = (label) => String(label || "").replace(/ \(.*\)/, "");

// ================================================================== events
function handle(ev) {
  const live = Date.now() / 1000 - ev.t < 8;
  S.tLast = ev.t;
  const k = ev.arm !== undefined ? runKey(ev.arm, ev.run) : null;
  switch (ev.type) {
    case "experiment_started": {
      S = { ...freshState(), follow: S.follow, exp: ev, id: ev.id, status: "running", t0: ev.t };
      ev.agents_detail.forEach((a) => { S.agents[a.id] = a; S.per[a.id] = { thinking: false, byRun: {}, life: {}, feel: {} }; });
      const decisions = Object.entries(ev.decisions);
      S.primary = (decisions.find(([, d]) => d.consumes.length) || decisions.find(([, d]) => d.type === "choice") || [])[0];
      S.signalQ = (decisions.find(([, d]) => d.role === "signal") || [])[0];
      S.sentimentQ = (decisions.find(([, d]) => d.role === "sentiment") || [])[0];
      decisions.forEach(([q, d]) => { S.colors[q] = {}; Object.keys(d.options).forEach((o, i) => { S.colors[q][o] = PALETTE[i % PALETTE.length]; }); });
      S.layout = layoutGraph(ev.agents_detail, ev.ties);
      buildGraph(ev.agents_detail, ev.ties);
      pushFeed({ sys: true, text: `Experiment started: ${ev.scenario} · ${ev.agents} people · arms ${ev.arms.join(", ")} · model ${ev.model}` });
      break;
    }
    case "run_started":
      S.runs[k] = { arm: ev.arm, run: ev.run, seed: ev.seed, rounds: {}, started: {}, world: ev.world, metrics: null,
        weight: ev.weight, days: {}, infl: [] };
      S.liveKey = k;
      if (S.follow || !S.viewKey) S.viewKey = k;
      Object.values(S.per).forEach((p) => { p.thinking = false; p.error = null; p.queued = false; });
      pushFeed({ sys: true, text: `Run started: arm ${ev.arm}, seed ${ev.seed}` });
      break;
    case "round_started":
      S.runs[k].started[ev.round] = ev;
      S.runs[k].world = ev.world;
      if (ev.slots) S.slots = ev.slots;
      S.round = { key: k, round: ev.round, decided: 0, asked: (ev.asked || []).length, events: ev.events };
      if (ev.feelings) Object.entries(ev.feelings).forEach(([id, f]) => { S.per[id].feel[k] = f; });
      if (!ev.slots) ev.events.forEach((e) => pushFeed({ sys: true, text: `Round ${ev.round} [${ev.arm}]: ${e.text} (seen by ${e.visible_to})` }));
      else pushFeed({ sys: true, text: `Day ${ev.round} begins [${ev.arm}]` });
      break;
    case "slot_started":
      dayOf(k, ev.round).started[ev.slot] = ev;
      S.now = { key: k, day: ev.round, slot: ev.slot, label: ev.label };
      S.round = { ...(S.round || {}), key: k, round: ev.round, decided: 0, asked: Object.keys(S.per).length };
      S.speaking = new Set();
      ev.events.forEach((e) => pushFeed({ sys: true, text: `Day ${ev.round} · ${ev.label}: ${e.text} (seen by ${e.visible_to})` }));
      break;
    case "agent_thinking":
      if (S.per[ev.agent]) { S.per[ev.agent].thinking = true; S.per[ev.agent].thinkingKind = ev.kind || "decision"; }
      break;
    case "life_decided": {
      const p = S.per[ev.agent];
      p.thinking = false;
      ((p.life[k] ||= {})[ev.round] ||= {})[ev.slot] = ev;
      p.feel[k] = ev.feelings;
      if (S.round && S.round.key === k) S.round.decided += 1;
      if (S.runs[k]) S.runs[k].liveStats = { calls: ev.calls, cost: ev.cost };
      sumStats();
      break;
    }
    case "slot_finished": {
      dayOf(k, ev.round).slots[ev.slot] = ev;
      Object.entries(ev.feelings || {}).forEach(([id, f]) => { S.per[id].feel[k] = f; });
      const fresh = [];
      ev.gatherings.forEach((g) => {
        g.influences.forEach((i) => fresh.push({ ...i, day: ev.round, slot: ev.slot, kind: "talk", place: g.place }));
        if (g.influences.length) {
          const speakers = [...new Set(g.influences.map((i) => i.from))];
          const listeners = g.members.filter((m) => !speakers.includes(m));
          pushFeed({ talk: true, text: `${speakers.map(agentName).join(", ")} talked about ${g.topic}${listeners.length ? ` with ${listeners.map(agentName).join(", ")}` : ""} · ${g.place}` });
        }
      });
      ev.views.forEach((v) => fresh.push({ ...v, day: ev.round, slot: ev.slot, kind: "post", channel: `on ${S.exp.platforms?.[v.platform] || v.platform}` }));
      ev.posts.forEach((p) => pushFeed({ talk: true, text: `${agentName(p.author)} posted on ${S.exp.platforms?.[p.platform] || p.platform}${p.stance ? ` (${p.stance} about ${S.exp.topic || "it"})` : " (life update)"}` }));
      run(k).infl.push(...fresh);
      S.speaking = new Set(fresh.map((f) => f.from));
      if (live && k === S.viewKey) animateFlows(fresh);
      break;
    }
    case "agent_decided": {
      const p = S.per[ev.agent];
      p.thinking = false; p.queued = false;
      (p.byRun[k] ||= {})[ev.round] = ev;
      S.runs[k].stats = { ...(S.runs[k].stats || { cached: 0, errors: 0 }), calls: ev.calls, cost: ev.cost };
      sumStats();
      if (live && k === S.viewKey && !S.slots.length) flashSignals(ev);
      pushFeed({ agent: ev.agent, k, ev });
      break;
    }
    case "agent_error":
      if (S.per[ev.agent]) { S.per[ev.agent].thinking = false; S.per[ev.agent].error = ev.error; }
      pushFeed({ sys: true, text: `Error for ${agentName(ev.agent)}: ${ev.error}` });
      break;
    case "round_finished":
      S.runs[k].rounds[ev.round] = ev;
      S.runs[k].world = ev.world;
      S.runs[k].stats = { calls: ev.calls, cached: ev.cached, errors: ev.errors, cost: ev.cost };
      Object.entries(ev.agent_outcomes || {}).forEach(([id, out]) => {
        const e = S.per[id]?.byRun[k]?.[ev.round];
        if (e) e.outcome = out;
        if (out.result !== "already_owned") pushFeed({ outcome: true, agent: id, round: ev.round, out });
      });
      sumStats();
      break;
    case "run_finished":
      S.runs[k].metrics = ev.metrics; S.runs[k].done = true;
      pushFeed({ sys: true, text: `Run finished (${ev.arm}, seed ${S.runs[k].seed}) in ${fmtTime(ev.seconds)} · ${ev.calls} model calls (${ev.cached} cached)` });
      break;
    case "experiment_finished": S.status = "finished"; S.summary = ev.summary; pushFeed({ sys: true, text: "Experiment finished. See Results." }); break;
    case "experiment_failed": S.status = "failed"; pushFeed({ sys: true, text: `Experiment failed: ${ev.error}` }); break;
    case "experiment_cancelled": S.status = "cancelled"; pushFeed({ sys: true, text: "Experiment cancelled." }); break;
  }
  dirty();
}

function sumStats() {
  S.stats = Object.values(S.runs).reduce((acc, r) => {
    const s = r.stats || {}, l = r.liveStats || {};
    acc.calls += Math.max(s.calls || 0, l.calls || 0); acc.cached += s.cached || 0; acc.errors += s.errors || 0;
    acc.cost += Math.max(s.cost || 0, l.cost || 0);
    return acc;
  }, { calls: 0, cached: 0, errors: 0, cost: 0 });
}
function pushFeed(item) { S.feed.push(item); if (S.feed.length > 800) S.feed.splice(0, S.feed.length - 800); }
const fmtTime = (s) => (s < 90 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`);

// ================================================================== queries
function latestFor(id, key = S.viewKey) {
  const rounds = S.per[id]?.byRun[key];
  if (!rounds) return null;
  const rs = Object.keys(rounds).map(Number).sort((a, b) => b - a);
  return rs.length ? { round: rs[0], ev: rounds[rs[0]] } : null;
}
function ownedIn(id, key = S.viewKey) { return Object.values(S.per[id]?.byRun[key] || {}).some((e) => e.outcome?.result === "acquired"); }
function lastChoice(id, q, key = S.viewKey) {
  const rounds = S.per[id]?.byRun[key] || {};
  for (const r of Object.keys(rounds).map(Number).sort((a, b) => b - a)) if (rounds[r].choices?.[q]) return rounds[r].choices[q];
  return null;
}
function latestLife(id, key = S.viewKey) {
  const days = S.per[id]?.life[key] || {};
  const d = Math.max(0, ...Object.keys(days).map(Number));
  if (!d) return null;
  const slot = S.slots.map((s) => s.id).filter((s) => days[d][s]).pop();
  return slot ? { day: d, slot, ev: days[d][slot] } : null;
}
const slotLabel = (id) => S.slots.find((s) => s.id === id)?.label || id;
function inflOf(id, key = S.viewKey) {
  const all = run(key)?.infl || [];
  return { out: all.filter((i) => i.from === id), inn: all.filter((i) => i.to === id) };
}

// ================================================================== render loop
let pending = false;
function dirty() { if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; renderLive(); }); } }
function renderLive() {
  renderRunbar();
  if (!S.exp) return;
  renderClock(); renderWorld(); renderHappening(); renderGraphState(); renderDays(); renderAgents(); renderFeed();
  if (S.selected && !$("#drawer").hidden && Date.now() - (S._drawerAt || 0) > 1500) renderDrawer(false);
  if ($("#view-results").classList.contains("active")) renderResults();
}

function renderRunbar() {
  const el = $("#runbar");
  if (!S.exp || document.activeElement?.id === "run-select") return;
  const e = S.exp;
  const totalRuns = e.arms.length * e.spec.seeds, doneRuns = Object.values(S.runs).filter((r) => r.done).length;
  const r = S.round;
  const prog = r ? Math.min(1, r.decided / Math.max(1, r.asked || 1)) : 0;
  const elapsed = S.t0 ? Math.max(0, (S.status === "running" ? Date.now() / 1000 : S.tLast) - S.t0) : 0;
  const options = Object.keys(S.runs).map((k) => `<option value="${esc(k)}" ${k === S.viewKey ? "selected" : ""}>${esc(S.runs[k].arm)} · seed ${S.runs[k].seed}${S.runs[k].done ? "" : " (live)"}</option>`).join("");
  const unit = S.slots.length ? "day" : "round";
  const where = S.now && S.slots.length ? ` · <b>${esc(shortSlot(S.now.label))}</b>` : "";
  el.innerHTML = `
    <div class="title"><span class="status-pill status-${S.status}">${S.status}</span><b>${esc(e.title || e.scenario)}</b><span class="hint">${esc(e.id)}</span></div>
    <div class="stats">
      <span>model <b>${esc(e.model || e.spec.backend)}</b></span>
      <span>runs <b>${doneRuns}/${totalRuns}</b></span>
      <span>${unit} <b>${r ? r.round : "–"}/${e.rounds}</b>${where} ${r ? `(${esc(S.runs[r.key]?.arm)})` : ""}</span>
      <span class="progress" title="decisions made in this step"><i style="width:${pct(prog)}"></i></span>
      <span>calls <b>${S.stats.calls}</b> (${S.stats.cached} cached)</span>
      <span>errors <b>${S.stats.errors}</b></span>
      <span>elapsed <b>${fmtTime(elapsed)}</b></span>
    </div>
    <div class="controls">
      <label class="hint">viewing <select id="run-select">${options}</select></label>
      <label class="hint"><input type="checkbox" id="follow" ${S.follow ? "checked" : ""}> follow live</label>
      ${S.status === "running" ? '<button id="cancel-run">Cancel</button>' : ""}
    </div>`;
  $("#run-select")?.addEventListener("change", (ev) => { S.viewKey = ev.target.value; S.follow = false; renderLive(); });
  $("#follow")?.addEventListener("change", (ev) => { S.follow = ev.target.checked; if (S.follow && S.liveKey) S.viewKey = S.liveKey; renderLive(); });
  $("#cancel-run")?.addEventListener("click", () => api(`/api/experiments/${S.id}/cancel`, { method: "POST" }).catch(alert));
}

function renderClock() {
  const el = $("#clock");
  if (!S.slots.length) { el.hidden = true; return; }
  el.hidden = false;
  const R = run(), days = S.exp.rounds;
  const now = S.now && S.now.key === S.viewKey ? S.now : null;
  let html = "";
  for (let d = 1; d <= days; d++) {
    const dd = R?.days?.[d];
    html += `<div class="day"><b>Day ${d}</b>${S.slots.map((s) => {
      const done = dd?.slots[s.id];
      const isNow = now && now.day === d && now.slot === s.id && !done;
      return `<span class="slot ${isNow ? "now" : done ? "done" : ""}">${esc(shortSlot(s.label))}</span>`;
    }).join("")}</div>${d < days ? '<span class="sep"></span>' : ""}`;
  }
  el.innerHTML = html;
}

function renderWorld() {
  const R = run();
  if (!R) { $("#world").innerHTML = '<span class="muted">Waiting for the first run…</span>'; return; }
  $("#world").innerHTML = Object.values(R.world || {}).map((it) => {
    const init = it.initial_stock, sold = it.sold || 0, left = it.stock;
    const bar = init ? `<div class="stockbar"><i class="sold" style="width:${pct(sold / init)}"></i><i class="left" style="width:${pct(Math.max(0, left) / init)}"></i></div>` : "";
    return `<div class="item"><div class="name"><span>${esc(it.label)}</span><span class="num">$${fmt(it.price)}</span></div>${bar}
      <div class="kv"><span>sold</span><span>${fmt(sold, 1)}${init ? ` / ${init}` : ""}</span>
      <span>left</span><span>${left == null ? "unlimited" : left <= 0 ? "sold out" : fmt(left, 1)}</span>
      <span>missed out (people)</span><span>${fmt(it.missed_out, 1)}</span>
      <span>priced out (people)</span><span>${fmt(it.priced_out, 1)}</span></div></div>`;
  }).join("") + `<div class="hint">Each agent stands for ${fmt(R.weight, 2)} people (market ${fmt(R.weight * S.exp.agents, 0)}).</div>`;
  const d = S.round && S.round.key === S.viewKey ? S.round.round : Math.max(0, ...Object.keys(R.started).map(Number));
  const happened = Object.values(R.days?.[d]?.started || {}).flatMap((s) => s.events.map((e) => ({ ...e, label: s.label })));
  const items = happened.length
    ? happened.map((e) => `<li><span class="when">${esc(e.label)} · seen by ${e.visible_to}</span>${esc(e.text)}</li>`)
    : (R.started[d]?.events || []).map((e) => `<li><span class="when">${e.slot ? `${esc(slotLabel(e.slot))} · scheduled` : `seen by ${e.visible_to}`}</span>${esc(e.text)}</li>`);
  $("#round-events").innerHTML = items.join("") || '<li class="muted">Nothing scheduled.</li>';
}

function renderHappening() {
  const el = $("#happening");
  const R = run();
  if (!R || !S.slots.length) { el.innerHTML = '<span class="muted">Daily life shows here for life scenarios.</span>'; $("#now-label").textContent = ""; return; }
  const d = Math.max(0, ...Object.keys(R.days || {}).map(Number));
  const slot = S.slots.map((s) => s.id).filter((s) => R.days[d]?.slots[s]).pop();
  if (!slot) { el.innerHTML = '<span class="muted">The day is just starting…</span>'; $("#now-label").textContent = ""; return; }
  const ev = R.days[d].slots[slot];
  $("#now-label").textContent = `Day ${d} · ${shortSlot(ev.label)}`;
  const counts = Object.entries(ev.counts).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([a, n]) => `${n}× ${esc(activityText(ev, a))}`).join("<br>");
  const groups = ev.gatherings.map((g) => {
    const talk = g.influences.length ? ` · <b>${g.influences.length}</b> nudges about ${esc(g.topic)}` : "";
    return `<div class="h"><b>${g.members.map((m) => esc(agentName(m))).join(", ")}</b><br><span class="hint">${esc(g.kind.replace("_", " "))} · ${esc(g.place)}${talk}</span></div>`;
  }).join("");
  const posts = ev.posts.length ? `<div class="h">${ev.posts.length} post(s), seen ${ev.views.length} time(s)</div>` : "";
  el.innerHTML = `<div class="h">${counts}</div>${groups}${posts}`;
}
function activityText(slotEv, actId) {
  for (const id of Object.keys(slotEv.activities)) if (slotEv.activities[id] === actId) {
    const l = S.per[id]?.life[S.viewKey]?.[slotEv.round]?.[slotEv.slot];
    if (l) return l.text;
  }
  return actId.replace(/_/g, " ");
}

// ================================================================== graph
function layoutGraph(agents, ties) {
  const W = 640, H = 440, n = agents.length;
  const groups = [...new Set(agents.map((a) => a.group))];
  const idx = Object.fromEntries(agents.map((a, i) => [a.id, i]));
  let seed = 11;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const P = agents.map((a) => {
    const g = groups.indexOf(a.group), ang = (2 * Math.PI * g) / groups.length;
    return { x: W / 2 + Math.cos(ang) * 160 + (rnd() - 0.5) * 50, y: H / 2 + Math.sin(ang) * 130 + (rnd() - 0.5) * 50, vx: 0, vy: 0 };
  });
  const links = ties.map((t) => ({ s: idx[t.a], t: idx[t.b], strong: t.kind === "strong" }));
  const iters = 320, rep = 900 * Math.sqrt(40 / Math.max(n, 10));
  for (let it = 0; it < iters; it++) {
    const alpha = 1 - it / iters;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const dx = P[i].x - P[j].x, dy = P[i].y - P[j].y, d2 = Math.max(dx * dx + dy * dy, 30);
      const f = (rep / d2) * alpha, d = Math.sqrt(d2);
      P[i].vx += (dx / d) * f; P[i].vy += (dy / d) * f; P[j].vx -= (dx / d) * f; P[j].vy -= (dy / d) * f;
    }
    for (const l of links) {
      const a = P[l.s], b = P[l.t], dx = b.x - a.x, dy = b.y - a.y, d = Math.max(1, Math.hypot(dx, dy));
      const f = (d - (l.strong ? 34 : 120)) * (l.strong ? 0.06 : 0.008) * alpha;
      a.vx += (dx / d) * f; a.vy += (dy / d) * f; b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
    }
    for (const p of P) { p.vx += (W / 2 - p.x) * 0.004 * alpha; p.vy += (H / 2 - p.y) * 0.004 * alpha; p.x += p.vx; p.y += p.vy; p.vx *= 0.55; p.vy *= 0.55; }
  }
  const xs = P.map((p) => p.x), ys = P.map((p) => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const s = Math.min((W - 70) / Math.max(1, x1 - x0), (H - 50) / Math.max(1, y1 - y0));
  const out = {};
  agents.forEach((a, i) => { out[a.id] = { x: 30 + (P[i].x - x0) * s + ((W - 70) - (x1 - x0) * s) / 2, y: 25 + (P[i].y - y0) * s + ((H - 50) - (y1 - y0) * s) / 2 }; });
  return out;
}

const NS = "http://www.w3.org/2000/svg";
const edgeEls = {};
function svgEl(tag, attrs) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; }
function buildGraph(agents, ties) {
  const svg = $("#graph"), L = S.layout;
  svg.innerHTML = "";
  const defs = svgEl("defs", {});
  ["positive", "negative", "neutral"].forEach((p) => {
    const m = svgEl("marker", { id: `arrow-${p}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" });
    const path = svgEl("path", { d: "M0 0L10 5L0 10z" });
    path.style.fill = p === "positive" ? "var(--good)" : p === "negative" ? "var(--bad)" : "var(--muted)";
    m.appendChild(path); defs.appendChild(m);
  });
  svg.appendChild(defs);
  const ge = svgEl("g", { id: "edges" }), gk = svgEl("g", { id: "keep" }), gf = svgEl("g", { id: "flows" }), gn = svgEl("g", { id: "nodes" });
  for (const k in edgeEls) delete edgeEls[k];
  ties.forEach((t) => {
    const l = svgEl("line", { x1: L[t.a].x, y1: L[t.a].y, x2: L[t.b].x, y2: L[t.b].y, class: `edge ${t.kind}` });
    l.dataset.a = t.a; l.dataset.b = t.b;
    const title = svgEl("title", {}); title.textContent = `${S.agents[t.a].name} – ${S.agents[t.b].name} (${t.label})`;
    l.appendChild(title); ge.appendChild(l);
    edgeEls[[t.a, t.b].sort().join("|")] = l;
  });
  agents.forEach((a) => {
    const c = svgEl("circle", { cx: L[a.id].x, cy: L[a.id].y, r: 4.5 + 7 * a.traits.social_influence, class: "node" });
    c.dataset.id = a.id;
    const title = svgEl("title", {}); title.textContent = `${a.name}, ${a.age} · ${a.occupation}${a.personality_type ? ` · ${a.personality_type}` : ""}`;
    c.appendChild(title);
    c.addEventListener("click", () => openDrawer(a.id));
    c.addEventListener("mouseenter", () => hoverNode(a.id));
    c.addEventListener("mouseleave", () => hoverNode(null));
    gn.appendChild(c);
    if (agents.length <= 60) {
      const tx = svgEl("text", { x: L[a.id].x + 9, y: L[a.id].y + 3 }); tx.textContent = a.name; tx.dataset.id = a.id;
      gn.appendChild(tx);
    }
  });
  svg.append(ge, gk, gf, gn);
}
function hoverNode(id) {
  $("#graph").classList.toggle("hovering", !!id);
  $$("#graph .edge").forEach((e) => e.classList.toggle("hl", !!id && (e.dataset.a === id || e.dataset.b === id)));
}
function curve(a, b, bend = 0.18) {
  const A = S.layout[a], B = S.layout[b];
  const mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2, dx = B.x - A.x, dy = B.y - A.y;
  const cx = mx - dy * bend, cy = my + dx * bend;
  const len = Math.hypot(B.x - cx, B.y - cy) || 1, r = 4.5 + 7 * S.agents[b].traits.social_influence + 2;
  return `M${A.x} ${A.y} Q${cx} ${cy} ${B.x - ((B.x - cx) / len) * r} ${B.y - ((B.y - cy) / len) * r}`;
}
function animateFlows(list) {
  const g = $("#flows");
  if (!g) return;
  const seen = new Set();
  list.slice(0, 90).forEach((f, i) => {
    const key = `${f.from}>${f.to}`;
    if (seen.has(key) || !S.layout[f.from] || !S.layout[f.to]) return;
    seen.add(key);
    const pol = f.polarity || "neutral";
    const p = svgEl("path", { d: curve(f.from, f.to), class: `flow ${pol}`, "marker-end": `url(#arrow-${pol})` });
    p.style.animationDelay = `0s, ${Math.min(i * 0.04, 1)}s`;
    const t = svgEl("title", {}); t.textContent = `${agentName(f.from)} → ${agentName(f.to)} (${pol}, ${f.channel || f.kind})`;
    p.appendChild(t);
    g.appendChild(p);
    setTimeout(() => p.remove(), 4200);
  });
}
function renderKeptFlows() {
  const g = $("#keep");
  if (!g) return;
  g.innerHTML = "";
  if (!S.selected || !run()) { $("#graph-note").textContent = "Hover a person to see their ties; click to follow their influence."; return; }
  const { out, inn } = inflOf(S.selected);
  const last = (arr, key) => Object.values(Object.fromEntries(arr.map((x) => [x[key], x])));
  last(out, "to").forEach((f) => g.appendChild(svgEl("path", { d: curve(f.from, f.to), class: `flow keep ${f.polarity}`, "marker-end": `url(#arrow-${f.polarity})` })));
  last(inn, "from").forEach((f) => g.appendChild(svgEl("path", { d: curve(f.from, f.to, -0.18), class: `flow keep in ${f.polarity}` })));
  $("#graph-note").textContent = `${agentName(S.selected)} influenced ${new Set(out.map((f) => f.to)).size} people (solid arrows) and was influenced by ${new Set(inn.map((f) => f.from)).size} (dotted).`;
}
function renderGraphState() {
  const q = S.primary;
  $$("#graph .node").forEach((c) => {
    const id = c.dataset.id, choice = q ? lastChoice(id, q) : null;
    c.style.fill = choice ? S.colors[q][choice] : "var(--line)";
    c.classList.toggle("owner", ownedIn(id));
    c.classList.toggle("thinking", !!S.per[id]?.thinking && S.viewKey === S.liveKey);
    c.classList.toggle("speaking", S.speaking.has(id) && S.viewKey === S.liveKey);
    c.classList.toggle("selected", S.selected === id);
  });
  $$("#graph text").forEach((t) => t.classList.toggle("sel", t.dataset.id === S.selected));
  renderKeptFlows();
  if (q) {
    $("#legend").innerHTML = Object.keys(S.exp.decisions[q].options).map((o) => `<span><i style="background:${S.colors[q][o]}"></i>${esc(o)}</span>`).join("")
      + '<span><i style="background:var(--line)"></i>no decision yet</span><span><i class="line" style="background:var(--good)"></i>positive nudge</span><span><i class="line" style="background:var(--bad)"></i>negative nudge</span>';
  }
}
function flashSignals(ev) {
  (ev.signals_shown || []).forEach((sender) => {
    const el = edgeEls[[sender, ev.agent].sort().join("|")];
    if (!el) return;
    const sl = S.signalQ ? lastChoice(sender, S.signalQ) : null;
    const pol = sl ? polarityOf(sl) : "neutral";
    el.classList.add(`flash-${pol}`);
    setTimeout(() => el.classList.remove(`flash-${pol}`), 1400);
  });
}
function polarityOf(option) {
  const o = option.toLowerCase();
  if (/(hype|praise|recommend|positive|support)/.test(o)) return "positive";
  if (/(warn|knock|against|negative|oppose)/.test(o)) return "negative";
  return "neutral";
}

// ================================================================== days panel
function dayStats(k, d) {
  const R = S.runs[k], dd = R?.days?.[d], fin = R?.rounds?.[d];
  const infl = (R?.infl || []).filter((i) => i.day === d);
  const slotEvs = Object.values(dd?.slots || {});
  return {
    fin, dd, infl,
    pos: infl.filter((i) => i.polarity === "positive").length, neg: infl.filter((i) => i.polarity === "negative").length,
    talks: infl.filter((i) => i.kind === "talk").length, postViews: infl.filter((i) => i.kind === "post").length,
    posts: slotEvs.reduce((a, s) => a + s.posts.length, 0), gatherings: slotEvs.reduce((a, s) => a + s.gatherings.length, 0),
  };
}
function renderDays() {
  const R = run(), q = S.primary;
  if (!R) { $("#round-chart").innerHTML = ""; return; }
  const opts = q ? Object.keys(S.exp.decisions[q].options) : [];
  const unit = S.slots.length ? "Day" : "Round";
  let html = "";
  for (let d = 1; d <= S.exp.rounds; d++) {
    const st = dayStats(S.viewKey, d), fin = st.fin;
    let counts = fin ? fin.choices[q] : null;
    if (!fin && q) {
      counts = Object.fromEntries(opts.map((o) => [o, 0]));
      Object.values(S.per).forEach((p) => { const e = p.byRun[S.viewKey]?.[d]; if (e?.choices?.[q]) counts[e.choices[q]] += 1; });
    }
    const total = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : 0;
    const stack = total ? opts.map((o) => counts[o] ? `<i style="width:${pct(counts[o] / total)};background:${S.colors[q][o]}" title="${esc(o)}: ${counts[o]}">${counts[o]}</i>` : "").join("") : "";
    const isNow = S.now && S.now.key === S.viewKey && S.now.day === d && !fin;
    const strip = S.slots.length ? `<div class="slotstrip">${S.slots.map((s) => `<span class="${st.dd?.slots[s.id] ? "done" : isNow && S.now.slot === s.id ? "now" : ""}">${esc(shortSlot(s.label))}</span>`).join("")}</div>` : "";
    const meta = [];
    if (fin) {
      const o = Object.entries(fin.outcomes).map(([kk, v]) => `${kk.replace("_", " ")} ${v}`).join(" · ");
      if (o) meta.push(o);
      if (S.sentimentQ && fin.scores[S.sentimentQ] != null) meta.push(`brand mood ${fmt(fin.scores[S.sentimentQ])}`);
    }
    if (S.slots.length && (st.pos || st.neg || st.posts)) meta.push(`nudges +${st.pos}/−${st.neg} · posts ${st.posts}`);
    if (!S.slots.length && fin) meta.push(`signals +${fin.signals.positive}/−${fin.signals.negative} of ${fin.signals.sent}`);
    const status = fin ? `${fin.asked} decided` : isNow || st.dd ? "in progress" : "";
    html += `<div class="daycard ${isNow ? "now" : ""}" data-day="${d}" title="Click for the ${unit.toLowerCase()} summary"><div class="top"><b>${unit} ${d}</b><span class="hint">${status}</span></div>
      ${strip}${stack ? `<div class="stack">${stack}</div>` : ""}<div class="meta">${meta.join(" · ") || "&nbsp;"}</div></div>`;
  }
  html += q ? `<div class="legend">${opts.map((o) => `<span><i style="background:${S.colors[q][o]}"></i>${esc(o)}</span>`).join("")}</div>` : "";
  $("#round-chart").innerHTML = html;
}

function openDay(d) {
  const R = run();
  if (!R) return;
  const st = dayStats(S.viewKey, d), fin = st.fin, unit = S.slots.length ? "Day" : "Round", q = S.primary;
  $("#day-title").textContent = `${unit} ${d} · ${R.arm} · seed ${R.seed}`;
  const stats = [];
  if (fin) {
    stats.push([fin.asked, "people decided"]);
    Object.entries(fin.outcomes).forEach(([kk, v]) => stats.push([v, kk.replace("_", " ")]));
    const w = fin.world && Object.values(fin.world)[0];
    if (w) stats.push([w.stock <= 0 ? "sold out" : fmt(w.stock, 0), `${w.label} left`]);
    if (S.sentimentQ && fin.scores[S.sentimentQ] != null) stats.push([fmt(fin.scores[S.sentimentQ]), "brand mood (0–1)"]);
  }
  if (S.slots.length) { stats.push([st.gatherings, "get-togethers"]); stats.push([`+${st.pos} / −${st.neg}`, "nudges (positive / negative)"]); stats.push([st.posts, "posts"]); }
  const lines = [];
  const events = Object.values(st.dd?.started || {}).flatMap((s) => s.events.map((e) => `${shortSlot(s.label)}: ${e.text} (seen by ${e.visible_to})`));
  const evs = events.length ? events : (R.started[d]?.events || []).map((e) => `${e.text}${e.visible_to != null ? ` (seen by ${e.visible_to})` : ""}`);
  if (fin && q) {
    const best = Object.entries(fin.choices[q] || {}).sort((a, b) => b[1] - a[1]);
    if (best.length && best[0][1]) lines.push(`Most people chose <b>${esc(best[0][0])}</b> (${best[0][1]} of ${Object.values(fin.choices[q]).reduce((a, b) => a + b, 0)} asked).`);
  }
  const talkers = {};
  st.infl.forEach((i) => { talkers[i.from] = (talkers[i.from] || 0) + 1; });
  const top = Object.entries(talkers).sort((a, b) => b[1] - a[1]).slice(0, 3);
  if (top.length) lines.push(`Biggest influencers: ${top.map(([id, n]) => `<b>${esc(agentName(id))}</b> (${n})`).join(", ")}.`);
  if (st.pos || st.neg) lines.push(`Word of mouth was ${st.pos > st.neg * 2 ? "strongly positive" : st.neg > st.pos ? "mostly negative" : "mixed"}: ${st.pos} positive vs ${st.neg} negative nudges (${st.talks} in person, ${st.postViews} from posts).`);
  let html = `<div class="summary">${lines.join(" ") || "Nothing decided yet."}</div><div class="statgrid">${stats.map(([v, l]) => `<div class="stat"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div></div>`).join("")}</div>`;
  html += `<div class="section"><h3>Events</h3><ul class="events">${evs.map((e) => `<li>${esc(e)}</li>`).join("") || '<li class="muted">None</li>'}</ul></div>`;
  if (S.slots.length) {
    html += `<div class="section"><h3>Hour by hour</h3><table><tr><th>Time</th><th>What people did</th><th class="num">Get-togethers</th><th class="num">Nudges</th><th class="num">Avg mood</th></tr>`;
    S.slots.forEach((s) => {
      const ev = st.dd?.slots[s.id];
      if (!ev) return;
      const top3 = Object.entries(ev.counts).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([a, n]) => `${n}× ${esc(activityText(ev, a))}`).join("<br>");
      const moods = Object.values(ev.feelings).map((f) => f.mood);
      const nudges = ev.gatherings.reduce((a, g) => a + g.influences.length, 0) + ev.views.length;
      html += `<tr><td>${esc(shortSlot(s.label))}</td><td>${top3}</td><td class="num">${ev.gatherings.length}</td><td class="num">${nudges}</td><td class="num">${fmt(moods.reduce((a, b) => a + b, 0) / moods.length)}</td></tr>`;
    });
    html += "</table></div>";
  }
  if (fin) html += `<div class="section"><h3>Decisions</h3><table><tr><th>Question</th><th>Answers</th></tr>${Object.entries(fin.choices).map(([qq, c]) => `<tr><td>${esc(qq)}</td><td>${Object.entries(c).map(([o, n]) => `${esc(o)} <b>${n}</b>`).join(" · ")}</td></tr>`).join("")}</table></div>`;
  $("#day-body").innerHTML = html;
  $("#day-dialog").showModal();
}

// ================================================================== people cards
function renderAgents() {
  const filter = $("#filter-agents").value.trim().toLowerCase();
  const sort = $("#sort-agents").value, q = S.primary;
  let list = Object.values(S.agents);
  if (filter) list = list.filter((a) => `${a.name} ${a.occupation} ${a.segments.join(" ")} ${a.cohort || ""} ${a.personality_type || ""}`.toLowerCase().includes(filter));
  const keyFn = {
    id: (a) => a.id, group: (a) => a.group + a.id, trend: (a) => -a.traits.trend_following, price: (a) => -a.traits.price_sensitivity,
    influence: (a) => -inflOf(a.id).out.length, mood: (a) => -(S.per[a.id].feel[S.viewKey]?.mood ?? 0),
    choice: (a) => (q ? lastChoice(a.id, q) || "~" : "") + a.id,
  }[sort];
  list.sort((x, y) => (keyFn(x) < keyFn(y) ? -1 : keyFn(x) > keyFn(y) ? 1 : 0));
  $("#agent-grid").innerHTML = list.map(cardHtml).join("");
}
function meter(label, v, cls = "") { return `<div class="meter ${cls}" title="${label}: ${fmt(v)}">${label}<div class="bar"><i style="width:${pct(v)}"></i></div></div>`; }
function cardHtml(a) {
  const p = S.per[a.id], last = latestFor(a.id), q = S.primary, life = latestLife(a.id);
  const thinking = p.thinking && S.viewKey === S.liveKey, ev = last?.ev, f = p.feel[S.viewKey];
  let now;
  if (thinking) now = `<span class="hint">${p.thinkingKind === "life" ? "deciding what to do…" : "thinking about the decision…"}</span>`;
  else if (life) now = `${esc(life.ev.text)} <span class="place">· ${esc(life.ev.place)} · ${esc(shortSlot(slotLabel(life.slot)))}</span>`;
  else now = `<span class="hint">${p.queued ? "queued" : "waiting"}</span>`;
  let foot = "", probbar = "";
  if (ev) {
    const probs = ev.probs?.[q];
    if (probs) probbar = `<div class="probbar" title="${esc(Object.entries(probs).map(([k, v]) => `${k} ${pct(v)}`).join(" · "))}">${Object.entries(probs).map(([o, v]) => `<i style="width:${pct(v)};background:${S.colors[q][o]}"></i>`).join("")}</div>`;
    const choice = q ? lastChoice(a.id, q) : null;
    if (choice) foot += `<span class="chip c" style="background:${S.colors[q][choice]}">${esc(choice)}</span>`;
    if (S.signalQ && ev.choices[S.signalQ]) foot += `<span class="chip">says: ${esc(ev.choices[S.signalQ])}</span>`;
    if (ownedIn(a.id)) foot += '<span class="badge acquired">got one</span>';
    else if (ev.outcome && ev.outcome.result !== "acquired") foot += `<span class="badge ${ev.outcome.result}">${esc(ev.outcome.result.replace("_", " "))}</span>`;
    if (ev.wanted && Object.keys(ev.wanted).length) foot += `<span class="badge missed_out" title="wanted this but it was blocked">wanted ${esc(Object.values(ev.wanted).join(", "))}</span>`;
    if (ev.flipped?.length) foot += '<span class="badge flip" title="noise changed the top option">flip</span>';
  }
  const io = inflOf(a.id);
  if (io.out.length || io.inn.length) foot += `<span class="hint" title="nudges given → / received ←">→${io.out.length} ←${io.inn.length}</span>`;
  const dot = p.error ? "error" : thinking ? "" : ev || life ? "done" : "";
  const meters = f ? `<div class="meters">${meter("mood", (f.mood + 1) / 2, "mood")}${meter("energy", f.energy)}${meter("stress", f.stress)}</div>`
    : `<div class="traits">${TRAITS.map(([t, l, full]) => `<div class="trait" title="${full}: ${fmt(a.traits[t])}">${l}<div class="bar"><i style="width:${pct(a.traits[t])}"></i></div></div>`).join("")}</div>`;
  return `<div class="card ${thinking ? "thinking" : ""} ${S.selected === a.id ? "selected" : ""}" data-id="${a.id}">
    <div class="card-head"><span class="dot ${dot}"></span><span class="name">${esc(a.name)}</span><span class="age">${a.age}</span>${a.personality_type ? `<span class="typechip">${esc(a.personality_type)}</span>` : ""}</div>
    <div class="card-sub">${esc(a.occupation)}${a.cohort ? ` · ${esc(a.cohort)}` : ""}</div>
    <div class="card-now">${now}</div>${meters}${probbar}${foot ? `<div class="card-foot">${foot}</div>` : ""}</div>`;
}

// ================================================================== feed
function renderFeed() {
  const ol = $("#feed");
  ol.innerHTML = S.feed.slice(-300).map((f) => {
    if (f.sys) return `<li class="sys">${esc(f.text)}</li>`;
    if (f.talk) return `<li class="talk"><span class="tag">social</span>${esc(f.text)}</li>`;
    if (f.outcome) return `<li><span class="who" data-id="${f.agent}">${esc(agentName(f.agent))}</span> <span class="badge ${f.out.result}">${esc(f.out.result.replace("_", " "))}</span></li>`;
    const e = f.ev, q = S.primary, c = q && e.choices[q];
    const p = c && e.probs?.[q] ? ` (${pct(e.probs[q][c])})` : "";
    const say = S.signalQ && e.choices[S.signalQ] ? ` · says ${esc(e.choices[S.signalQ])}` : "";
    return `<li><span class="tag">decision</span><span class="who" data-id="${f.agent}">${esc(agentName(f.agent))}</span> ${c ? `→ <b>${esc(c)}</b>${p}` : ""}${say}${e.flipped?.length ? " · flip" : ""}</li>`;
  }).join("");
  if ($("#feed-follow").checked) ol.scrollTop = ol.scrollHeight;
}

// ================================================================== person panel
function openDrawer(id) {
  S.selected = id;
  $("#drawer").hidden = false;
  renderDrawer(true);
  renderLive();
}
function feelWords(f) {
  const mood = f.mood < -0.5 ? "miserable" : f.mood < -0.15 ? "a bit down" : f.mood < 0.15 ? "okay" : f.mood < 0.5 ? "good" : "really happy";
  const en = f.energy < 0.2 ? "exhausted" : f.energy < 0.45 ? "tired" : f.energy < 0.75 ? "fine" : "energetic";
  const st = f.stress > 0.7 ? "very stressed" : f.stress > 0.45 ? "a bit stressed" : "relaxed";
  return `${mood}, ${en}, ${st}`;
}
function quickSummary(a) {
  const f = S.per[a.id].feel[S.viewKey], life = latestLife(a.id), io = inflOf(a.id), q = S.primary;
  const parts = [`<b>${esc(a.name)}</b> is ${a.age}, ${esc(a.occupation)}${a.personality_type ? `, ${a.personality_type === "ambivert" ? "an ambivert" : `an ${a.personality_type}`}` : ""}${a.temperament ? ` (${esc(a.temperament.split(";")[0])})` : ""}.`];
  if (a.life_context) parts.push(`At the moment ${esc(a.name)} ${esc(a.life_context)}.`);
  if (life) parts.push(`Latest: <b>${esc(life.ev.text.toLowerCase())}</b> (day ${life.day}, ${esc(shortSlot(slotLabel(life.slot)).toLowerCase())}).`);
  if (f) parts.push(`Feeling ${feelWords(f)}.`);
  const c = q ? lastChoice(a.id, q) : null, says = S.signalQ ? lastChoice(a.id, S.signalQ) : null;
  if (c || says) parts.push(`Decision: ${c ? `<b>${esc(c)}</b>` : "not asked yet"}${says ? `; telling people: <b>${esc(says)}</b>` : ""}.`);
  if (ownedIn(a.id)) parts.push("Got one.");
  const outN = new Set(io.out.map((i) => i.to)).size, inN = new Set(io.inn.map((i) => i.from)).size;
  if (outN || inN) parts.push(`Influenced <b>${outN}</b> people; was influenced by <b>${inN}</b> (${io.inn.filter((i) => i.polarity === "positive").length} positive, ${io.inn.filter((i) => i.polarity === "negative").length} negative nudges).`);
  return parts.join(" ");
}
function renderDrawer(fetchTrace) {
  const a = S.agents[S.selected];
  if (!a) return;
  const k = S.viewKey, R = run(), f = S.per[a.id].feel[k];
  S._drawerAt = Date.now();
  const bodyEl = $("#drawer-body"), keepScroll = bodyEl.scrollTop, keepOpen = $$("details", bodyEl).map((d) => d.open);
  const platforms = (a.platforms || []).map((p) => S.exp.platforms?.[p] || p).join(", ") || "no social media";
  $("#drawer-title").innerHTML = `<div class="who">${esc(a.name)}, ${a.age}</div><div class="hint">${esc(a.occupation)}${a.cohort_label ? ` · ${esc(a.cohort_label)}` : ""}${a.personality_type ? ` · ${esc(a.personality_type)}` : ""} · ${esc(platforms)} · group ${esc(a.group)}</div>`;
  const days = S.per[a.id].life[k] || {}, decs = S.per[a.id].byRun[k] || {}, inf = R?.infl || [];
  const dayNums = [...new Set([...Object.keys(days), ...Object.keys(decs)].map(Number))].sort((x, y) => x - y);
  const timeline = dayNums.map((d) => {
    const rows = S.slots.map((s) => {
      const l = days[d]?.[s.id];
      if (!l) return "";
      const heard = inf.filter((i) => i.to === a.id && i.day === d && i.slot === s.id);
      const said = inf.filter((i) => i.from === a.id && i.day === d && i.slot === s.id);
      const extra = [];
      if (said.length) extra.push(`${POL_WORD[said[0].polarity] || "talked about"} it to ${[...new Set(said.map((i) => agentName(i.to)))].join(", ")}`);
      if (heard.length) extra.push(`heard from ${[...new Set(heard.map((i) => `${agentName(i.from)} (${i.polarity})`))].join(", ")}`);
      return `<div class="trow"><span class="when">${esc(shortSlot(s.label))}</span><span>${esc(l.text)} <span class="hint">· ${esc(l.place)}</span>${extra.length ? `<br><span class="hint">${esc(extra.join(" · "))}</span>` : ""}</span></div>`;
    }).join("");
    const dec = decs[d];
    const decRow = dec ? `<div class="trow decision"><span class="when">Decision</span><span>${Object.entries(dec.choices).map(([qq, o]) => `${esc(qq)}: <b>${esc(o)}</b>`).join(" · ")}${dec.outcome ? ` · <b>${esc(dec.outcome.result.replace("_", " "))}</b>` : ""}${Object.entries(dec.scores || {}).map(([qq, v]) => ` · ${esc(qq)} ${fmt(v)}`).join("")}</span></div>` : "";
    return `<div class="tday">${S.slots.length ? "Day" : "Round"} ${d}</div>${rows}${decRow}`;
  }).join("") || '<span class="muted">Nothing yet.</span>';
  const io = inflOf(a.id);
  const listInf = (arr, key) => {
    const by = {};
    arr.forEach((i) => { const o = i[key]; (by[o] ||= { pos: 0, neg: 0, neu: 0, ch: new Set() }); by[o][i.polarity === "positive" ? "pos" : i.polarity === "negative" ? "neg" : "neu"]++; by[o].ch.add(i.channel || i.kind); });
    return Object.entries(by).sort((x, y) => (y[1].pos + y[1].neg + y[1].neu) - (x[1].pos + x[1].neg + x[1].neu)).map(([o, v]) =>
      `<div class="r"><b>${esc(agentName(o))}</b>${v.pos ? `<span class="badge acquired">+${v.pos}</span>` : ""}${v.neg ? `<span class="badge missed_out">−${v.neg}</span>` : ""}${v.neu ? `<span class="chip">${v.neu} neutral</span>` : ""}<span class="hint">${esc([...v.ch].join(", "))}</span></div>`).join("") || '<span class="muted">Nobody yet.</span>';
  };
  const bar = (label, v, shown) => `<div class="row"><span>${label}</span><div class="bar"><i style="width:${pct(v)}"></i></div><span class="num">${fmt(shown ?? v)}</span></div>`;
  const b5 = a.big_five && Object.keys(a.big_five).length ? `<h3>Personality (Big Five)</h3><div class="tbars">${BIG5.map(([t, l]) => bar(l, a.big_five[t])).join("")}</div>` : "";
  $("#drawer-body").innerHTML = `
    <div class="summary">${quickSummary(a)}</div>
    ${f ? `<div class="section"><h3>Right now</h3><div class="tbars">${bar("Mood", (f.mood + 1) / 2, f.mood)}${bar("Energy", f.energy)}${bar("Stress", f.stress)}${bar("Hunger", f.hunger)}${bar("Wants company", f.social_need)}</div></div>` : ""}
    <div class="section"><h3>Their days</h3><div class="timeline">${timeline}</div></div>
    <div class="section grid2"><div><h3>Influenced by</h3><div class="inflist">${listInf(io.inn, "from")}</div></div><div><h3>Influenced</h3><div class="inflist">${listInf(io.out, "to")}</div></div></div>
    <details><summary>Who they are</summary>
      <p>${esc(a.profile || a.persona)}</p>${b5}
      <h3>Decision traits</h3><div class="tbars">${TRAITS.map(([t, , full]) => bar(full, a.traits[t])).join("")}</div>
      <p class="hint">Segments: ${esc(a.segments.join(", ") || "none")} · income ${esc(a.income)} · budget $${a.budget}${a.susceptibility != null ? ` · how easily swayed ${fmt(a.susceptibility)}` : ""}</p>
    </details>
    <details id="trace-box"><summary>Model traces (what the model saw and answered)</summary><div id="trace" class="muted">Loading…</div></details>`;
  if (!fetchTrace) { $$("details", bodyEl).forEach((d, i) => { if (keepOpen[i]) d.open = true; }); bodyEl.scrollTop = keepScroll; }
  else bodyEl.scrollTop = 0;
  if (fetchTrace || !S._traceFor || S._traceFor !== `${a.id}|${k}`) loadTrace(a.id);
  else if (S._traceHtml) { $("#trace").innerHTML = S._traceHtml; $("#trace").classList.remove("muted"); }
}
let traceToken = 0;
async function loadTrace(id) {
  const token = ++traceToken, R = run();
  if (!R) return;
  S._traceFor = `${id}|${S.viewKey}`;
  try {
    const recs = await api(`/api/experiments/${S.id}/trace?agent=${id}&arm=${encodeURIComponent(R.arm)}&run=${R.run}`);
    if (token !== traceToken || !$("#trace")) return;
    S._traceHtml = recs.length ? recs.map(traceHtml).join("") : "No trace yet.";
    $("#trace").innerHTML = S._traceHtml;
    $("#trace").classList.remove("muted");
  } catch (e) { if (token === traceToken && $("#trace")) $("#trace").textContent = `Trace unavailable: ${e.message}`; }
}
function traceHtml(r) {
  const when = r.kind === "life" ? `Day ${r.round} · ${shortSlot(slotLabel(r.slot))} · everyday choice` : `${S.slots.length ? "Day" : "Round"} ${r.round} · decision`;
  if (r.error && !r.answers) return `<details><summary>${esc(when)}: error</summary><pre>${esc(r.error)}</pre></details>`;
  const answers = Object.entries(r.answers || {}).map(([q, a]) => {
    if (a.value != null) return `<tr><td>${esc(q)}</td><td colspan="5">score ${fmt(a.value)}</td></tr>`;
    return Object.keys(a.raw).map((o, i) => {
      const sh = a.shifts?.[o] ? Object.entries(a.shifts[o]).map(([kk, v]) => `${kk} ${v > 0 ? "+" : ""}${Number(v).toFixed(2)}`).join(", ") : "";
      const blk = a.blocked?.[o] ? ` <span class="badge missed_out">${esc(String(a.blocked[o]).replace("_", " "))}</span>` : "";
      const want = a.wanted === o && a.wanted !== a.choice ? ' <span class="badge flip">wanted</span>' : "";
      return `<tr><td>${i ? "" : esc(q)}</td><td>${o === a.choice ? `<b>${esc(o)}</b>` : esc(o)}${blk}${want}</td><td class="num">${pct(a.raw[o])}</td><td class="num">${pct((a.adjusted || a.raw)[o])}</td><td class="num">${pct(a.noisy[o])}</td><td class="hint">${esc(sh)}</td></tr>`;
    }).join("");
  }).join("");
  const meta = r.state_meta;
  return `<details><summary>${esc(when)} · ${r.cached ? "cached" : `${Math.round(r.latency_ms)} ms`}${meta ? ` · ${meta.chars} chars` : ""}${r.truncated ? " · TRUNCATED" : ""}</summary>
    <table><tr><th>Question</th><th>Option</th><th class="num">Model</th><th class="num">+ rules</th><th class="num">+ noise</th><th>Rule shifts</th></tr>${answers}</table>
    <pre>${esc(JSON.stringify(r.state, null, 2))}</pre></details>`;
}

// ================================================================== results / history / population
async function renderResults() {
  const el = $("#results");
  if (!S.id) { el.innerHTML = '<p class="muted">No experiments yet. Click <b>New run</b>.</p>'; return; }
  if (!S.summary && S.status === "finished") { try { S.summary = (await api(`/api/experiments/${S.id}`)).summary; } catch { /* ignore */ } }
  const sum = S.summary;
  if (!sum) { el.innerHTML = `<p class="muted">Results appear when the experiment finishes (status: ${esc(S.status)}).</p>`; return; }
  const arms = Object.keys(sum.arms), metrics = [...new Set(arms.flatMap((a) => Object.keys(sum.arms[a].metrics)))];
  const cell = (d) => !d || !d.n ? "–" : d.kind === "bool" ? `${d.true}/${d.n}` : d.n > 1 ? `${fmt(d.mean)} <span class="hint">[${fmt(d.p10)}–${fmt(d.p90)}]</span>` : fmt(d.mean);
  const dcell = (d) => {
    if (!d) return "–";
    if (d.kind === "bool") return `${d.variant}/${d.n} vs ${d.baseline}/${d.n}`;
    if (!d.n) return "–";
    const cls = d.mean > 0 ? "delta-pos" : d.mean < 0 ? "delta-neg" : "";
    return `<span class="${cls}">${d.mean > 0 ? "+" : ""}${fmt(d.mean)}</span>${d.n > 1 ? ` <span class="hint">[${fmt(d.p10)}–${fmt(d.p90)}]</span>` : ""}`;
  };
  const variants = arms.filter((a) => a !== "baseline");
  let html = `<h2>Results · ${esc(S.exp.title || S.exp.scenario)}</h2><p class="hint">${esc(S.id)} · ${sum.arms[arms[0]].runs} run(s) per arm · means with [p10–p90] across seeds</p>`;
  html += `<div class="panel"><table><tr><th>Metric</th>${arms.map((a) => `<th class="num">${esc(a)}</th>`).join("")}${variants.map((v) => `<th class="num">Δ ${esc(v)}</th>`).join("")}</tr>`;
  html += metrics.map((m) => `<tr><td>${esc(m)}</td>${arms.map((a) => `<td class="num">${cell(sum.arms[a].metrics[m])}</td>`).join("")}${variants.map((v) => `<td class="num">${dcell(sum.deltas[v]?.[m])}</td>`).join("")}</tr>`).join("");
  html += "</table></div>";
  for (const a of arms) {
    const segs = sum.arms[a].segments, q = S.primary, opts = q ? Object.keys(S.exp.decisions[q].options) : [];
    html += `<h3>Segments · ${esc(a)}</h3><div class="panel"><table><tr><th>Segment</th><th class="num">Agents</th><th class="num">Got one</th><th class="num">Mood</th>${opts.map((o) => `<th class="num">${esc(o)}</th>`).join("")}</tr>`;
    html += Object.entries(segs).map(([s, row]) => `<tr><td>${esc(s)}</td><td class="num">${row.agents}</td><td class="num">${pct(row.acquired_share)}</td><td class="num">${fmt(row.mean_sentiment)}</td>${opts.map((o) => `<td class="num">${row[q] ? pct(row[q][o]) : "–"}</td>`).join("")}</tr>`).join("");
    html += `</table><p class="hint">${sum.arms[a].calls} calls · ${sum.arms[a].cached} cached · ${sum.arms[a].errors} errors · $${sum.arms[a].cost}</p></div>`;
  }
  el.innerHTML = html;
}
async function renderHistory() {
  const el = $("#history");
  const list = await api("/api/experiments").catch(() => []);
  el.innerHTML = `<h2>Experiments</h2>` + (list.length ? list.map((e) => `<div class="list-item"><span class="status-pill status-${esc(e.status)}">${esc(e.status)}</span>
    <div><b>${esc(e.title || e.scenario)}</b> · ${e.agents} people · ${esc((e.arms || []).join(", "))} · ${esc(e.spec?.backend)} · seeds ${e.spec?.seeds}<div class="hint">${esc(e.id)}</div></div>
    <span class="spacer"></span><button data-open="${esc(e.id)}">Open</button></div>`).join("") : '<p class="muted">No experiments yet.</p>');
  $$("[data-open]", el).forEach((b) => b.addEventListener("click", () => { openExperiment(b.dataset.open); showView("live"); }));
}
async function renderPopulation() {
  const el = $("#population");
  const configs = await api("/api/population-configs").catch(() => []);
  el.innerHTML = `<h2>Population preview</h2><div class="panel" style="display:flex;gap:10px;align-items:end;margin-bottom:12px;flex-wrap:wrap">
    <label>Config <select id="p-cfg">${configs.map((c) => `<option value="${esc(c.file)}">${esc(c.name)}</option>`).join("")}</select></label>
    <label>People <input id="p-size" type="number" value="20" min="2" max="1000"></label>
    <label>Seed <input id="p-seed" type="number" placeholder="default"></label><button id="p-go" class="primary">Preview</button></div><div id="p-out"></div>`;
  $("#p-go").addEventListener("click", async () => {
    const seed = $("#p-seed").value ? `&seed=${$("#p-seed").value}` : "";
    const pop = await api(`/api/population-configs/${$("#p-cfg").value}/preview?size=${$("#p-size").value}${seed}`);
    const labels = Object.fromEntries(Object.entries(pop.config.social_media?.platforms || {}).map(([k, v]) => [k, v.label]));
    $("#p-out").innerHTML = `<p class="hint">${pop.agents.length} people · ${pop.ties.length} ties</p><div class="panel"><table><tr><th>Person</th><th>Type</th><th>Traits R/P/T/S</th><th>Online</th><th>Life</th></tr>${pop.agents.map((a) =>
      `<tr><td><b>${esc(a.name)}</b> ${a.age}<div class="hint">${esc(a.occupation)}</div></td><td>${esc(a.personality_type)}<div class="hint">${esc(a.chronotype)}</div></td><td>${TRAITS.map(([t]) => fmt(a.traits[t])).join(" / ")}</td><td>${esc((a.platforms || []).map((p) => labels[p] || p).join(", ") || "none")}<div class="hint">posts ${esc(a.posting)}</div></td><td class="hint">${esc(a.profile || a.persona)}</td></tr>`).join("")}</table></div>`;
  });
  $("#p-go").click();
}

// ================================================================== launch
async function openLaunch() {
  $("#launch-error").textContent = "";
  const [configs, scenarios, backends] = await Promise.all([api("/api/population-configs"), api("/api/scenarios"), api("/api/backends")]);
  $("#f-pop").innerHTML = configs.map((c) => `<option value="${esc(c.file)}">${esc(c.name)}${c.error ? " (invalid)" : ""}</option>`).join("");
  $("#f-scenario").innerHTML = scenarios.length ? scenarios.map((s) => `<option value="${esc(s.file)}" ${s.error ? "disabled" : ""}>${esc(s.title || s.name)}${s.error ? " (invalid)" : ""}</option>`).join("") : '<option value="">No scenarios in scenarios/</option>';
  const setArms = () => {
    const s = scenarios.find((x) => x.file === $("#f-scenario").value);
    $("#f-arms").innerHTML = s?.arms ? s.arms.map((a) => `<label><input type="checkbox" name="arm" value="${esc(a)}" checked> ${esc(a)}</label>`).join("") : "";
    estimate();
  };
  $("#f-scenario").onchange = setArms;
  $("#f-backends").innerHTML = backends.map((b) => `<label><input type="radio" name="backend" value="${esc(b.name)}" ${b.default ? "checked" : ""}>
    <b>${esc(b.name)}</b> <span class="hint">${esc(b.description)} ${b.health.ok ? "· online" : "· offline"}</span></label>`).join("");
  setArms();
  $("#launch").showModal();
}
function estimate() {
  const f = $("#launch-form"), arms = $$("input[name=arm]:checked", f).length;
  const n = Number(f.size.value || 0), seeds = Number(f.seeds.value || 1);
  $("#launch-estimate").textContent = `About ${n * 3 * arms * seeds} decision calls, plus ~4 everyday choices per person per day for life scenarios. Repeats are cached.`;
}
async function submitLaunch(ev) {
  ev.preventDefault();
  if (ev.submitter && ev.submitter.value === "cancel") { $("#launch").close(); return; }
  const f = $("#launch-form"), backend = $("input[name=backend]:checked", f)?.value;
  if (backend === "jev" && !confirm("Jev is paid (OpenRouter). Run this experiment on Jev?")) return;
  const body = { population_config: f.population_config.value, size: Number(f.size.value), scenario: f.scenario.value, backend,
    arms: $$("input[name=arm]:checked", f).map((x) => x.value), seeds: Number(f.seeds.value), sigma: Number(f.sigma.value) };
  if (f.population_seed.value) body.population_seed = Number(f.population_seed.value);
  try {
    const exp = await api("/api/experiments", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("#launch").close(); openExperiment(exp.id); showView("live");
  } catch (e) { $("#launch-error").textContent = e.message; }
}

// ================================================================== wiring
function openExperiment(id) {
  if (source) source.close();
  S = { ...freshState(), follow: true };
  $("#drawer").hidden = true;
  source = new EventSource(`/api/experiments/${id}/events`);
  source.onmessage = (m) => handle(JSON.parse(m.data));
  source.addEventListener("end", () => { source.close(); if (S.status === "running") S.status = "stopped"; dirty(); });
  history.replaceState(null, "", `#${id}`);
}
function showView(name) {
  $$("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  if (name === "results") renderResults();
  if (name === "history") renderHistory();
  if (name === "population") renderPopulation();
}
async function refreshBackends() {
  const list = await api("/api/backends").catch(() => []);
  $("#backend-status").innerHTML = list.filter((b) => b.name !== "fake").map((b) => `<span class="pill ${b.health.ok ? "ok" : "down"}" title="${esc(b.description)}">${esc(b.name)}</span>`).join("");
}
async function openLatest() {
  const list = await api("/api/experiments").catch(() => []);
  const pick = list.find((e) => e.status === "running") || list.find((e) => e.status === "finished") || list[0];
  if (pick) openExperiment(pick.id); else $("#runbar").innerHTML = '<span class="muted">No experiments yet. Click <b>New run</b>.</span>';
}

$$("#nav button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
$("#new-run").addEventListener("click", () => openLaunch().catch((e) => alert(e.message)));
$("#launch-form").addEventListener("submit", submitLaunch);
$("#launch-form").addEventListener("input", estimate);
$("#drawer-close").addEventListener("click", () => { $("#drawer").hidden = true; S.selected = null; dirty(); });
$("#day-close").addEventListener("click", () => $("#day-dialog").close());
$("#agent-grid").addEventListener("click", (e) => { const c = e.target.closest(".card"); if (c) openDrawer(c.dataset.id); });
$("#feed").addEventListener("click", (e) => { const w = e.target.closest(".who"); if (w) openDrawer(w.dataset.id); });
$("#round-chart").addEventListener("click", (e) => { const d = e.target.closest(".daycard"); if (d) openDay(Number(d.dataset.day)); });
$("#filter-agents").addEventListener("input", dirty);
$("#sort-agents").addEventListener("change", dirty);
setInterval(() => { if (S.status === "running") renderRunbar(); }, 1000);
refreshBackends();
setInterval(refreshBackends, 30000);
if (location.hash.length > 1) openExperiment(location.hash.slice(1)); else openLatest();
window.addEventListener("hashchange", () => { const id = location.hash.slice(1); if (id && id !== S.id) openExperiment(id); });
