// Workouts: live set-by-set sessions with auto rest timer, weekly training
// load, coach-plan loading, structured logging with last-time hints + PR
// detection, rest timer, progression charts, history.
import { el, esc, api, toast, refresh, metric, rowActions, CHART } from '../app.js';

const TYPES = ['Push Day A (Cutler Mode)', 'Pull Day A (Cutler Mode)', 'Leg Day A (Cutler Mode)',
  'Push Day B', 'Pull Day B', 'Leg Day B', 'Cardio', 'Custom'];
const INTENSITIES = ['Light', 'Moderate', 'Hard', 'Very Hard'];

// Cutler Mode A-day templates for one-tap live sessions (mirrors the README).
const CUTLER_TEMPLATES = {
  'Push Day A (Cutler Mode)': [
    ['Incline Dumbbell Press', 4, 10], ['Overhead Shoulder Press', 4, 12],
    ['Rope Triceps Extensions', 3, 15], ['Side Laterals', 3, 12], ['Cable Flys', 3, 12]],
  'Pull Day A (Cutler Mode)': [
    ['Barbell Rows', 4, 10], ['Lat Pulldowns', 4, 12], ['Face Pulls', 3, 15],
    ['Hammer Curls', 3, 12], ['Cable Curls', 3, 12]],
  'Leg Day A (Cutler Mode)': [
    ['Squats', 4, 10], ['Romanian Deadlifts', 4, 10], ['Leg Press', 3, 15],
    ['Leg Curls', 3, 12], ['Calf Raises', 4, 15]],
};

// Live session survives refreshes/phone sleep via localStorage.
const LIVE_KEY = 'gna-live-session';
const loadLive = () => { try { return JSON.parse(localStorage.getItem(LIVE_KEY)); } catch { return null; } };
const saveLive = s => localStorage.setItem(LIVE_KEY, JSON.stringify(s));
const clearLive = () => localStorage.removeItem(LIVE_KEY);

// Plate math: what to slide on each side of a 45 lb bar. Rounds to the
// nearest 2.5-achievable load; caller compares achieved vs asked.
const PLATE_SIZES = [45, 35, 25, 10, 5, 2.5];
function platesPerSide(total, bar = 45) {
  if (total < bar) return null;
  let left = Math.round((total - bar) / 2 / 2.5) * 2.5;
  const out = [];
  for (const s of PLATE_SIZES) {
    while (left >= s) { out.push(s); left = Math.round((left - s) * 100) / 100; }
  }
  return out;
}

// Plate math only makes sense for barbell moves — hide it for everything else.
const NOT_BARBELL = /dumbbell|\bdb\b|cable|machine|band|lateral|fly|flye|pulldown|pushdown|face pull|raise|bodyweight|smith|leg (press|curl|extension)/i;
const barbellish = name => !NOT_BARBELL.test(name);

const e1rm = (w, r) => (w > 0 && r > 0 ? Math.round(w * (1 + r / 30)) : 0);

const fmtClock = sec => sec >= 3600
  ? `${Math.floor(sec / 3600)}:${String(Math.floor(sec / 60) % 60).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`
  : `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator(), gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = 880; gain.gain.value = 0.08;
    osc.start(); osc.stop(ctx.currentTime + 0.35);
  } catch { /* no audio available */ }
  if (navigator.vibrate) navigator.vibrate([180, 90, 180]);
}

// "Incline Dumbbell Press: 4×10 @ 70 lbs" → {exercise, sets, reps, weight}
function parsePlanLine(line) {
  const m = line.match(/^(.*?)[\s:—-]*?(\d+)\s*[x×]\s*(\d+)(?:[^\d]*?([\d.]+)\s*(?:lbs?|kg|#)?)?\s*$/i);
  if (!m) return null;
  const name = m[1].replace(/[:—-]+$/, '').trim();
  if (!name || name.length > 60) return null;
  return { exercise: name, sets: Number(m[2]), reps: Number(m[3]), weight: Number(m[4] || 0) };
}

export function renderWorkouts(root, state) {
  root.append(el('<h2 class="section-title">Workouts</h2>'));
  root.append(el('<p class="section-sub">Log sets, reps, and weight per exercise — that\'s what powers the progression charts.</p>'));

  const progression = state.stats.progression;
  const knownNames = Object.keys(progression).sort();

  const week = state.plan?.plan?.week || [];
  const todayName = new Date().toLocaleDateString('en-US', { weekday: 'long' });
  const planDay = week.find(d => (d.day || '').toLowerCase().includes(todayName.toLowerCase()));

  // ── live session — set-by-set logging, elapsed clock, auto rest timer ──
  const prevTopOf = name => {
    const s = progression[String(name || '').trim()];
    return s?.length ? Math.max(...s.map(x => x.top)) : 0;
  };
  const liveWrap = el('<div class="live-wrap"></div>');
  root.append(liveWrap);

  function startSession(name, exList) {
    saveLive({
      name, startedAt: Date.now(), rest: 90, restEndsAt: null,
      exercises: exList.map(x => ({
        name: x.exercise, targetSets: x.sets || 0, targetReps: x.reps || 0,
        targetWeight: x.weight || 0, sets: [],
      })),
    });
    drawLive();
  }

  function drawStart() {
    const card = el(`<div class="card">
      <p class="chart-title">Live session</p>
      <p style="color:var(--muted);font-size:12px;margin:6px 0 10px">Train with the clock running — log each set as you rack it, and the rest timer starts itself. A session in progress survives refreshes.</p>
      <div class="form-row" style="align-items:flex-end">
        ${planDay ? `<button type="button" class="gold-btn lv-plan" style="flex:0 1 auto;min-height:38px;padding:8px 16px;font-size:13px">Start today's plan — ${esc(planDay.title)}</button>` : ''}
        <label style="flex:0 1 260px">Template <select class="lv-tpl">
          ${Object.keys(CUTLER_TEMPLATES).map(t => `<option>${t}</option>`).join('')}
          <option>Empty session</option></select></label>
        <button type="button" class="ghost-btn lv-go" style="flex:0 1 auto;min-height:38px;padding:8px 16px">Start</button>
      </div></div>`);
    card.querySelector('.lv-plan')?.addEventListener('click', () => {
      const exs = planDay.details.map(parsePlanLine).filter(Boolean);
      startSession((planDay.title || 'Custom').slice(0, 60), exs);
    });
    card.querySelector('.lv-go').addEventListener('click', () => {
      const tpl = card.querySelector('.lv-tpl').value;
      const exs = (CUTLER_TEMPLATES[tpl] || []).map(([n, s2, r]) => ({ exercise: n, sets: s2, reps: r }));
      startSession(tpl === 'Empty session' ? 'Custom' : tpl, exs);
    });
    liveWrap.append(card);
  }

  function drawSession(s) {
    const panel = el(`<div class="panel" style="border:1px solid var(--gold)">
      <div class="form-row" style="align-items:center">
        <span class="chart-title" style="margin:0;flex:1;min-width:160px">LIVE — ${esc(s.name)}</span>
        <span class="lv-elapsed" style="font-family:var(--font-mono);font-size:22px;font-weight:700"></span>
        <span class="lv-rest" style="font-family:var(--font-mono);font-size:14px;color:var(--gold-bright);min-width:88px;text-align:right"></span>
        <label style="flex:0 1 110px">Rest <select class="lv-rest-sel">
          ${[60, 90, 120, 180].map(x => `<option value="${x}"${x === s.rest ? ' selected' : ''}>${fmtClock(x)}</option>`).join('')}
        </select></label>
        <button type="button" class="gold-btn lv-finish" style="flex:0 1 auto;min-height:38px;padding:8px 16px">Finish &amp; save</button>
        <button type="button" class="ghost-btn lv-discard" style="flex:0 1 auto;min-height:38px;padding:8px 12px">Discard</button>
      </div>
      <div class="lv-exs" style="display:grid;gap:10px;margin-top:12px"></div>
      <div class="form-row" style="margin-top:10px">
        <label style="flex:2 1 200px">Add exercise <input class="lv-add-name" type="text" list="exercise-names" placeholder="Cable Flys"></label>
        <button type="button" class="ghost-btn lv-add" style="flex:0 1 auto;min-height:38px;padding:8px 14px">Add</button>
      </div></div>`);

    const exsBox = panel.querySelector('.lv-exs');
    s.exercises.forEach((ex, i) => {
      const prevTop = prevTopOf(ex.name);
      const lastSet = ex.sets[ex.sets.length - 1];
      const done = ex.targetSets && ex.sets.length >= ex.targetSets;
      const chips = ex.sets.map(t =>
        `<span title="est 1RM ${e1rm(t.w, t.r)}" style="font-family:var(--font-mono);font-size:12px;padding:2px 8px;border-radius:3px;background:var(--bg);${prevTop && t.w > prevTop ? 'color:var(--gold-bright);font-weight:700' : 'color:var(--ink-2)'}">${t.w}×${t.r}${prevTop && t.w > prevTop ? ' PR' : ''}</span>`).join('');
      const rowEl = el(`<div style="border-left:3px solid ${done ? 'var(--good)' : 'var(--steel)'};padding:6px 12px;display:grid;gap:6px">
        <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
          <strong style="font-size:14px">${esc(ex.name)}</strong>
          ${ex.targetSets ? `<span style="font-family:var(--font-mono);font-size:11px;color:var(--muted)">target ${ex.targetSets}×${ex.targetReps}</span>` : ''}
          ${prevTop ? `<span style="font-family:var(--font-mono);font-size:11px;color:var(--muted)">PR ${prevTop} lbs</span>` : ''}
          <span style="display:flex;gap:6px;flex-wrap:wrap">${chips}</span>
        </div>
        <div class="form-row" style="align-items:flex-end">
          <label style="flex:0 1 130px">Weight <input data-f="w" type="number" min="0" step="2.5" value="${lastSet ? lastSet.w : (ex.targetWeight || prevTop || 0)}"></label>
          <label style="flex:0 1 110px">Reps <input data-f="r" type="number" min="1" value="${lastSet ? lastSet.r : (ex.targetReps || 10)}"></label>
          <button type="button" class="gold-btn lv-log" data-i="${i}" style="flex:0 1 auto;min-height:38px;padding:8px 16px">Log set ${ex.sets.length + 1}</button>
          ${ex.sets.length ? '' : `<button type="button" class="icon-btn danger lv-rm" data-i="${i}" title="Remove" style="flex:0">✕</button>`}
        </div>
        <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:baseline;font-family:var(--font-mono);font-size:11px;color:var(--muted)">
          <span class="lv-plates"></span>
          <a href="#" class="lv-warm" style="color:var(--steel)">warm-up ramp</a>
          <span class="lv-warm-sets" style="color:var(--ink-2)" hidden></span>
        </div>
      </div>`);

      const wInput = rowEl.querySelector('[data-f="w"]');
      const platesEl = rowEl.querySelector('.lv-plates');
      const updPlates = () => {
        const w = Number(wInput.value) || 0;
        if (!barbellish(ex.name) || w < 65) { platesEl.textContent = ''; return; }
        const plates = platesPerSide(w);
        const achieved = 45 + 2 * plates.reduce((s2, p) => s2 + p, 0);
        platesEl.textContent = plates.length
          ? `${achieved !== w ? `≈${achieved} ` : ''}per side: ${plates.join(' · ')}`
          : 'empty bar';
      };
      wInput.addEventListener('input', updPlates);
      updPlates();

      rowEl.querySelector('.lv-warm').addEventListener('click', ev => {
        ev.preventDefault();
        const box = rowEl.querySelector('.lv-warm-sets');
        if (!box.hidden) { box.hidden = true; return; }
        const tgt = Number(wInput.value) || 0;
        if (tgt < 95) { toast('Warm-up ramps kick in from ~95 lbs.'); return; }
        const r5 = x => Math.max(45, Math.round(x / 5) * 5);
        box.textContent = `bar×10 → ${r5(tgt * .4)}×8 → ${r5(tgt * .6)}×5 → ${r5(tgt * .8)}×3 → ${tgt} work`;
        box.hidden = false;
      });

      exsBox.append(rowEl);
    });
    if (!s.exercises.length) exsBox.append(el('<div class="empty">Add your first exercise below.</div>'));

    panel.addEventListener('click', ev => {
      const log = ev.target.closest('.lv-log');
      if (log) {
        const i = Number(log.dataset.i);
        const row = log.closest('.form-row');
        const w = Number(row.querySelector('[data-f="w"]').value) || 0;
        const r = Number(row.querySelector('[data-f="r"]').value) || 0;
        if (r <= 0) { toast('Reps first.'); return; }
        const ex = s.exercises[i];
        const prevTop = prevTopOf(ex.name);
        ex.sets.push({ w, r });
        s.restEndsAt = Date.now() + s.rest * 1000;
        saveLive(s);
        if (prevTop && w > prevTop) toast(`NEW PR — ${ex.name} @ ${w} lbs`);
        drawLive();
        return;
      }
      const rm = ev.target.closest('.lv-rm');
      if (rm) { s.exercises.splice(Number(rm.dataset.i), 1); saveLive(s); drawLive(); }
    });

    panel.querySelector('.lv-rest-sel').addEventListener('change', ev => {
      s.rest = Number(ev.target.value); saveLive(s);
    });

    panel.querySelector('.lv-add').addEventListener('click', () => {
      const name = panel.querySelector('.lv-add-name').value.trim();
      if (!name) return;
      s.exercises.push({ name, targetSets: 0, targetReps: 0, targetWeight: 0, sets: [] });
      saveLive(s); drawLive();
    });

    panel.querySelector('.lv-discard').addEventListener('click', ev => {
      if (ev.target.dataset.armed) { clearLive(); drawLive(); toast('Session discarded'); return; }
      ev.target.dataset.armed = '1'; ev.target.textContent = 'Really discard?';
      setTimeout(() => { delete ev.target.dataset.armed; ev.target.textContent = 'Discard'; }, 4000);
    });

    panel.querySelector('.lv-finish').addEventListener('click', () => finishSession(s));

    liveWrap.append(panel);
    const elapsedEl = panel.querySelector('.lv-elapsed');
    const restEl = panel.querySelector('.lv-rest');
    let wasConnected = false;
    const tick = () => {
      // Kill the interval only after the panel has been mounted then replaced
      // (a re-render) — never on early ticks while the section is still mounting.
      if (panel.isConnected) wasConnected = true;
      else { if (wasConnected) clearInterval(iv); return; }
      elapsedEl.textContent = fmtClock(Math.max(0, Math.floor((Date.now() - s.startedAt) / 1000)));
      if (s.restEndsAt) {
        const left = Math.ceil((s.restEndsAt - Date.now()) / 1000);
        if (left <= 0) {
          s.restEndsAt = null; saveLive(s); restEl.textContent = '';
          beep(); toast('Rest over — back under the bar');
        } else restEl.textContent = `REST ${fmtClock(left)}`;
      } else restEl.textContent = '';
    };
    const iv = setInterval(tick, 1000);
    tick();
  }

  async function finishSession(s) {
    // One row per (exercise, weight, reps) group — progression stats merge
    // same-day rows, so nothing is lost.
    const grouped = [];
    for (const ex of s.exercises) for (const t of ex.sets) {
      const g = grouped.find(x => x.exercise === ex.name && x.weight === t.w && x.reps === t.r);
      if (g) g.sets += 1;
      else grouped.push({ exercise: ex.name, sets: 1, reps: t.r, weight: t.w });
    }
    if (!grouped.length) { toast('Log at least one set first.'); return; }
    const maxW = {};
    for (const g of grouped) maxW[g.exercise] = Math.max(maxW[g.exercise] || 0, g.weight);
    const prs = Object.entries(maxW)
      .filter(([name, w]) => { const pt = prevTopOf(name); return pt && w > pt; })
      .map(([name, w]) => `${name} @ ${w} lbs`);
    const started = new Date(s.startedAt);
    const mins = Math.max(1, Math.round((Date.now() - s.startedAt) / 60000));
    const volume = Math.round(grouped.reduce((s2, g) => s2 + g.sets * g.reps * g.weight, 0));
    try {
      await api('POST', '/workouts', {
        date: started.toISOString().slice(0, 10),
        time: started.toTimeString().slice(0, 5),
        name: s.name, duration: mins,
        intensity: 'Hard', notes: 'Live session', exercises: grouped,
      });
      clearLive();
      toast(`Session saved — ${volume.toLocaleString()} lbs in ${mins} min` +
        (prs.length ? `. NEW PR: ${prs.join(', ')}` : ''));
      await refresh();
    } catch (err) { toast(err.message); }
  }

  function drawLive() {
    liveWrap.innerHTML = '';
    const s = loadLive();
    if (s) drawSession(s); else drawStart();
  }
  drawLive();

  // ── weekly training load ──
  const tr = state.stats.training;
  if (tr) {
    const grid = el('<div class="cards metrics"></div>');
    grid.append(
      metric('Sessions', tr.sessions_7d, { small: '7d' }),
      metric('Minutes', tr.minutes_7d, { small: '7d' }),
      metric('Volume', tr.volume_7d, { suffix: ' lbs', small: 'sets×reps×wt, 7d' }),
      metric('Week streak', tr.streak_weeks, { small: '3+ sessions/wk' }),
    );
    root.append(grid);
  }

  // ── recent PRs ──
  const prsFeed = state.stats.recent_prs || [];
  if (prsFeed.length) {
    const prCard = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Recent PRs — the trophy shelf</p>
      <div class="pr-list" style="display:grid;gap:6px;margin-top:10px"></div></div>`);
    const list = prCard.querySelector('.pr-list');
    for (const pr of prsFeed) {
      list.append(el(`<div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;border-left:3px solid var(--gold);padding:4px 12px">
        <span style="font-family:var(--font-mono);font-size:11px;color:var(--muted)">${esc(pr.date)}</span>
        <span style="flex:1;min-width:160px;font-weight:600;font-size:13px">${esc(pr.exercise)}</span>
        <span style="font-family:var(--font-mono);font-size:13px;color:var(--gold-bright);font-weight:700">${pr.weight} lbs</span>
        <span style="font-family:var(--font-mono);font-size:11px;color:var(--good)">▲ up from ${pr.prev}</span>
      </div>`));
    }
    root.append(prCard);
  }

  // ── training load & balance ──
  const mb = state.stats.muscle_balance || { groups: [] };
  const wv = state.stats.weekly_volume || [];
  if (mb.groups.length || wv.some(w => w.volume > 0)) {
    const loadCard = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Training load &amp; balance</p>
      <div class="grid-2" style="margin-top:8px;align-items:start">
        <div class="chart wv-chart" style="min-height:180px"></div>
        <div class="mb-split">
          <p style="margin:0 0 8px;font-size:11px;color:var(--muted);font-family:var(--font-mono)">Volume by muscle group · ${mb.days}d</p>
        </div>
      </div></div>`);
    root.append(loadCard);
    if (mb.warning) {
      loadCard.querySelector('.chart-title').insertAdjacentElement('afterend',
        el(`<div class="callout warn" style="margin-top:10px">${esc(mb.warning)}</div>`));
    }
    const split = loadCard.querySelector('.mb-split');
    const maxPct = Math.max(1, ...mb.groups.map(g => g.pct));
    mb.groups.forEach((g, i) => {
      split.append(el(`<div style="display:flex;align-items:center;gap:10px;margin:6px 0">
        <span style="flex:0 0 82px;font-size:12px;color:var(--ink-2)">${esc(g.group)}</span>
        <span style="flex:1;height:10px;background:var(--bg);border-radius:3px;overflow:hidden">
          <span style="display:block;height:100%;width:${Math.round(g.pct / maxPct * 100)}%;border-radius:3px;background:${i === 0 ? 'var(--gold)' : 'var(--steel)'}"></span></span>
        <span style="flex:0 0 74px;text-align:right;font-family:var(--font-mono);font-size:11px;color:var(--muted)">${g.pct}% · ${g.volume.toLocaleString()}</span>
      </div>`));
    });
    if (!mb.groups.length) split.append(el('<div class="empty">Log sets with weight to see your split.</div>'));
    Plotly.newPlot(loadCard.querySelector('.wv-chart'),
      [{ x: wv.map(w => w.week_start), y: wv.map(w => w.volume), type: 'bar',
         marker: { color: CHART.gold, cornerradius: 3 },
         customdata: wv.map(w => w.sessions),
         hovertemplate: 'week of %{x}<br>%{y:,.0f} lbs · %{customdata} sessions<extra></extra>' }],
      CHART.layout({ height: 180, bargap: .35, margin: { l: 48, r: 8, t: 20, b: 30 },
        title: { text: 'Weekly volume · 8 weeks', font: { size: 11, color: '#8b93a1' }, x: 0 } }),
      CHART.config);
  }

  // ── log form ──
  const now = new Date();
  const form = el(`<form class="panel" style="margin-top:14px">
    <div class="plan-load-slot"></div>
    <div class="grid-3">
      <label>Date <input name="date" type="date" value="${now.toISOString().slice(0, 10)}"></label>
      <label>Time <input name="time" type="time" value="${now.toTimeString().slice(0, 5)}"></label>
      <label>Type <select name="name">${TYPES.map(t => `<option>${t}</option>`).join('')}</select></label>
      <label>Duration (min) <input name="duration" type="number" min="0" value="60"></label>
      <label>Intensity <select name="intensity">${INTENSITIES.map(i => `<option${i === 'Hard' ? ' selected' : ''}>${i}</option>`).join('')}</select></label>
      <label>Notes <input name="notes" type="text" placeholder="Optional" data-f="notes-input"></label>
    </div>
    <p class="chart-title" style="margin:14px 0 8px">Exercises</p>
    <div class="ex-rows" style="display:grid;gap:8px"></div>
    <div class="form-row" style="margin-top:10px">
      <button type="button" class="ghost-btn add-ex" style="flex:0 1 auto">Add exercise</button>
      <button class="gold-btn" type="submit" style="flex:0 1 auto">Log workout</button>
    </div>
  </form>`);
  const exRows = form.querySelector('.ex-rows');

  function lastTimeHint(name) {
    const series = progression[name];
    if (!series?.length) return '';
    const last = series[series.length - 1];
    const allTimeTop = Math.max(...series.map(s => s.top));
    const target = allTimeTop > 0 ? ` Target: ${allTimeTop + 2.5}+ lbs for a PR.` : '';
    return `Last time (${last.date}): top ${Number(last.top).toLocaleString()} lbs · ${Math.round(last.volume).toLocaleString()} lbs volume.${target}`;
  }

  function addExRow(vals = {}) {
    const row = el(`<div class="ex-row" style="display:grid;gap:4px">
      <div class="form-row">
        <label style="flex:3 1 160px">Exercise <input data-f="exercise" type="text" list="exercise-names" value="${esc(vals.exercise || '')}" placeholder="Incline Dumbbell Press"></label>
        <label>Sets <input data-f="sets" type="number" min="0" value="${vals.sets ?? 3}"></label>
        <label>Reps <input data-f="reps" type="number" min="0" value="${vals.reps ?? 10}"></label>
        <label>Weight (lbs) <input data-f="weight" type="number" min="0" step="2.5" value="${vals.weight ?? 0}"></label>
        <button type="button" class="icon-btn danger" title="Remove" style="flex:0">✕</button>
      </div>
      <p class="ex-hint" style="margin:0;font-size:12px;color:var(--steel);min-height:0"></p>
    </div>`);
    const nameInput = row.querySelector('[data-f="exercise"]');
    const hint = row.querySelector('.ex-hint');
    const syncHint = () => { hint.textContent = lastTimeHint(nameInput.value.trim()); };
    nameInput.addEventListener('change', syncHint);
    nameInput.addEventListener('blur', syncHint);
    if (vals.exercise) syncHint();
    row.querySelector('.danger').addEventListener('click', () => row.remove());
    exRows.append(row);
    return row;
  }
  addExRow();
  form.querySelector('.add-ex').addEventListener('click', () => addExRow());

  root.append(el(`<datalist id="exercise-names">${knownNames.map(n => `<option value="${esc(n)}">`).join('')}</datalist>`));

  // ── load today's coach plan into the form ──
  if (planDay) {
    const coach = (state.coaches || []).find(c => c.id === state.plan.coach);
    const slot = form.querySelector('.plan-load-slot');
    const loader = el(`<div class="callout good" style="margin-bottom:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <span style="flex:1;min-width:200px"><strong>${esc(coach?.name || 'Your coach')} programmed today:</strong>
        ${esc(planDay.title)} — ${esc(planDay.focus)}</span>
      <button type="button" class="gold-btn" style="flex:0 1 auto;min-height:38px;padding:8px 16px;font-size:13px">Load today's plan</button>
    </div>`);
    loader.querySelector('button').addEventListener('click', () => {
      exRows.innerHTML = '';
      const unparsed = [];
      for (const line of planDay.details) {
        const ex = parsePlanLine(line);
        if (ex) addExRow(ex);
        else unparsed.push(line);
      }
      if (!exRows.children.length) addExRow();
      form.name.value = 'Custom';
      form.notes.value = [planDay.title, ...unparsed].join(' · ').slice(0, 300);
      toast(`Loaded: ${planDay.title}`);
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    slot.append(loader);
  }

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(form).entries());
    body.exercises = [...exRows.querySelectorAll('.ex-row')].map(r => {
      const get = f => r.querySelector(`[data-f="${f}"]`).value;
      return { exercise: get('exercise'), sets: get('sets'), reps: get('reps'), weight: get('weight') };
    }).filter(x => x.exercise.trim());

    // PR detection: compare against the previous all-time top per exercise
    const prs = [];
    for (const ex of body.exercises) {
      const series = progression[ex.exercise.trim()];
      const prevTop = series?.length ? Math.max(...series.map(s => s.top)) : 0;
      const w = Number(ex.weight) || 0;
      if (series && w > prevTop) prs.push(`${ex.exercise.trim()} @ ${w} lbs`);
    }
    try {
      await api('POST', '/workouts', body);
      toast(prs.length ? `NEW PR — ${prs.join(', ')}` : 'Workout logged');
      await refresh();
    } catch (err) { toast(err.message); }
  });
  root.append(form);

  // ── rest timer ──
  const timer = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">Rest timer</p>
    <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-top:8px">
      <span class="rt-display" style="font-family:var(--font-display);font-weight:900;font-size:44px;letter-spacing:-.02em;min-width:130px">1:30</span>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${[60, 90, 120, 180].map(s => `<button type="button" class="ghost-btn rt-preset" data-s="${s}" style="min-height:38px;padding:8px 14px">${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}</button>`).join('')}
      </div>
      <div style="display:flex;gap:8px;margin-left:auto">
        <button type="button" class="gold-btn rt-start" style="min-height:38px;padding:8px 18px">Start</button>
        <button type="button" class="ghost-btn rt-reset" style="min-height:38px;padding:8px 14px">Reset</button>
      </div>
    </div>
    <p style="color:var(--muted);font-size:12px;margin:8px 0 0">Cutler rests ~60–90s between sets; strength work earns the full 3:00.</p>
  </div>`);
  const display = timer.querySelector('.rt-display');
  let restTotal = 90, remaining = 90, ticking = null;
  const draw = () => {
    display.textContent = `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}`;
    display.style.color = remaining === 0 ? 'var(--good)' : remaining <= 5 ? 'var(--gold-bright)' : '';
  };
  const stopTick = () => { clearInterval(ticking); ticking = null; timer.querySelector('.rt-start').textContent = 'Start'; };
  timer.querySelectorAll('.rt-preset').forEach(b => b.addEventListener('click', () => {
    restTotal = remaining = Number(b.dataset.s); stopTick(); draw();
  }));
  timer.querySelector('.rt-start').addEventListener('click', ev => {
    if (ticking) { stopTick(); return; }
    if (remaining === 0) remaining = restTotal;
    ev.target.textContent = 'Pause';
    ticking = setInterval(() => {
      remaining = Math.max(0, remaining - 1);
      draw();
      if (remaining === 0) { stopTick(); beep(); toast('Rest over — back under the bar'); }
    }, 1000);
  });
  timer.querySelector('.rt-reset').addEventListener('click', () => { stopTick(); remaining = restTotal; draw(); });
  draw();
  root.append(timer);

  // ── progression ──
  if (knownNames.length) {
    const sel = location.hash.includes(':') ? decodeURIComponent(location.hash.split(':')[1]) : knownNames[0];
    const chosen = knownNames.includes(sel) ? sel : knownNames[0];
    const card = el(`<div class="card" style="margin-top:14px">
      <div class="form-row" style="align-items:center">
        <p class="chart-title" style="margin:0;flex:0 1 auto">Progression</p>
        <label style="flex:0 1 280px"><select>${knownNames.map(n =>
          `<option${n === chosen ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select></label>
      </div>
      <div class="cards metrics prog-stats" style="margin:12px 0"></div>
      <div class="chart" id="prog-weight"></div>
      <div class="chart" id="prog-volume" style="margin-top:8px"></div>
    </div>`);
    card.querySelector('select').addEventListener('change', ev => {
      location.hash = `workouts:${encodeURIComponent(ev.target.value)}`;
      refresh();
    });
    root.append(card);

    const series = progression[chosen];
    const pr = Math.max(...series.map(s => s.top));
    const bestVol = Math.max(...series.map(s => s.volume));
    const bestE1rm = Math.max(...series.map(s => s.e1rm ?? 0));
    card.querySelector('.prog-stats').append(
      metric('All-time PR', pr, { suffix: ' lbs' }),
      metric('Est. 1RM', Math.round(bestE1rm), { suffix: ' lbs', small: 'Epley, best set' }),
      metric('Best day volume', Math.round(bestVol), { suffix: ' lbs', small: 'sets×reps×wt' }),
      metric('Sessions', series.length, {}),
    );

    Plotly.newPlot(card.querySelector('#prog-weight'),
      [{ x: series.map(s => s.date), y: series.map(s => s.top), mode: 'lines+markers',
         line: { color: CHART.gold, width: 2 }, marker: { size: 7, color: CHART.gold },
         hovertemplate: '%{x}<br>top set %{y:g} lbs<extra></extra>' }],
      CHART.layout({ margin: { l: 44, r: 16, t: 4, b: 30 }, height: 220,
        yaxis: { gridcolor: 'rgba(110,118,131,.16)', zeroline: false, fixedrange: true, title: { text: 'top weight', font: { size: 10 } } } }),
      CHART.config);

    Plotly.newPlot(card.querySelector('#prog-volume'),
      [{ x: series.map(s => s.date), y: series.map(s => s.volume), type: 'bar',
         marker: { color: CHART.steel, cornerradius: 4 },
         hovertemplate: '%{x}<br>volume %{y:,.0f} lbs<extra></extra>' }],
      CHART.layout({ margin: { l: 44, r: 16, t: 4, b: 30 }, height: 200, bargap: .45,
        yaxis: { gridcolor: 'rgba(110,118,131,.16)', zeroline: false, fixedrange: true, title: { text: 'volume', font: { size: 10 } } } }),
      CHART.config);
  }

  // ── recent history ──
  root.append(el('<p class="chart-title" style="margin:18px 0 8px">Last 7 days</p>'));
  const weekAgo = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
  const rows = state.workouts.map((w, idx) => ({ w, idx })).filter(({ w }) => w.date >= weekAgo).reverse();
  if (!rows.length) {
    root.append(el('<div class="empty">No workouts in the last 7 days. The bar misses you.</div>'));
    return;
  }
  const wrap = el(`<div class="table-wrap"><table>
    <thead><tr><th>Date</th><th>Workout</th><th>Exercises</th><th class="num">Min</th><th>Intensity</th><th></th></tr></thead>
    <tbody></tbody></table></div>`);
  const tbody = wrap.querySelector('tbody');
  for (const { w, idx } of rows) {
    const exs = (w.exercises || []).map(x =>
      `${esc(x.exercise)} ${x.sets}×${x.reps}@${x.weight}`).join(', ') || '—';
    const tr2 = el(`<tr><td>${esc(w.date)}</td><td>${esc(w.name)}</td>
      <td style="max-width:340px">${exs}</td><td class="num">${w.duration ?? 0}</td><td>${esc(w.intensity || '')}</td></tr>`);
    tr2.append(rowActions('workouts', idx));
    tbody.append(tr2);
  }
  root.append(wrap);
}
