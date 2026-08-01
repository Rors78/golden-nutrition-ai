// Workouts: weekly training load, coach-plan loading, structured logging with
// last-time hints + PR detection, rest timer, progression charts, history.
import { el, esc, api, toast, refresh, metric, rowActions, CHART } from '../app.js';

const TYPES = ['Push Day A (Cutler Mode)', 'Pull Day A (Cutler Mode)', 'Leg Day A (Cutler Mode)',
  'Push Day B', 'Pull Day B', 'Leg Day B', 'Cardio', 'Custom'];
const INTENSITIES = ['Light', 'Moderate', 'Hard', 'Very Hard'];

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
    return `Last time (${last.date}): top ${Number(last.top).toLocaleString()} lbs · ${Math.round(last.volume).toLocaleString()} lbs volume — beat it.`;
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
  const week = state.plan?.plan?.week || [];
  const todayName = new Date().toLocaleDateString('en-US', { weekday: 'long' });
  const planDay = week.find(d => (d.day || '').toLowerCase().includes(todayName.toLowerCase()));
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
  const beep = () => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = 880; gain.gain.value = 0.08;
      osc.start(); osc.stop(ctx.currentTime + 0.35);
    } catch { /* no audio available */ }
    if (navigator.vibrate) navigator.vibrate([180, 90, 180]);
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
    card.querySelector('.prog-stats').append(
      metric('All-time PR', pr, { suffix: ' lbs' }),
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
