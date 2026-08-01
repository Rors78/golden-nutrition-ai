// Workouts: structured exercise logging + per-exercise progression charts.
import { el, esc, api, toast, refresh, metric, rowActions, CHART } from '../app.js';

const TYPES = ['Push Day A (Cutler Mode)', 'Pull Day A (Cutler Mode)', 'Leg Day A (Cutler Mode)',
  'Push Day B', 'Pull Day B', 'Leg Day B', 'Cardio', 'Custom'];
const INTENSITIES = ['Light', 'Moderate', 'Hard', 'Very Hard'];

export function renderWorkouts(root, state) {
  root.append(el('<h2 class="section-title">Workouts</h2>'));
  root.append(el('<p class="section-sub">Log sets, reps, and weight per exercise — that\'s what powers the progression charts.</p>'));

  // ── log form ──
  const now = new Date();
  const form = el(`<form class="panel">
    <div class="grid-3">
      <label>Date <input name="date" type="date" value="${now.toISOString().slice(0, 10)}"></label>
      <label>Time <input name="time" type="time" value="${now.toTimeString().slice(0, 5)}"></label>
      <label>Type <select name="name">${TYPES.map(t => `<option>${t}</option>`).join('')}</select></label>
      <label>Duration (min) <input name="duration" type="number" min="0" value="60"></label>
      <label>Intensity <select name="intensity">${INTENSITIES.map(i => `<option${i === 'Hard' ? ' selected' : ''}>${i}</option>`).join('')}</select></label>
      <label>Notes <input name="notes" type="text" placeholder="Optional"></label>
    </div>
    <p class="chart-title" style="margin:14px 0 8px">Exercises</p>
    <div class="ex-rows" style="display:grid;gap:8px"></div>
    <div class="form-row" style="margin-top:10px">
      <button type="button" class="ghost-btn add-ex" style="flex:0 1 auto">＋ Add exercise</button>
      <button class="gold-btn" type="submit" style="flex:0 1 auto">Log workout</button>
    </div>
  </form>`);
  const exRows = form.querySelector('.ex-rows');

  function addExRow(vals = {}) {
    const row = el(`<div class="form-row ex-row">
      <label style="flex:3 1 160px">Exercise <input data-f="exercise" type="text" list="exercise-names" value="${esc(vals.exercise || '')}" placeholder="Incline Dumbbell Press"></label>
      <label>Sets <input data-f="sets" type="number" min="0" value="${vals.sets ?? 3}"></label>
      <label>Reps <input data-f="reps" type="number" min="0" value="${vals.reps ?? 10}"></label>
      <label>Weight (lbs) <input data-f="weight" type="number" min="0" step="2.5" value="${vals.weight ?? 0}"></label>
      <button type="button" class="icon-btn danger" title="Remove" style="flex:0">✕</button>
    </div>`);
    row.querySelector('.danger').addEventListener('click', () => row.remove());
    exRows.append(row);
  }
  addExRow();
  form.querySelector('.add-ex').addEventListener('click', () => addExRow());

  const progression = state.stats.progression;
  const knownNames = Object.keys(progression).sort();
  root.append(el(`<datalist id="exercise-names">${knownNames.map(n => `<option value="${esc(n)}">`).join('')}</datalist>`));

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(form).entries());
    body.exercises = [...exRows.querySelectorAll('.ex-row')].map(r => {
      const get = f => r.querySelector(`[data-f="${f}"]`).value;
      return { exercise: get('exercise'), sets: get('sets'), reps: get('reps'), weight: get('weight') };
    }).filter(x => x.exercise.trim());
    try {
      await api('POST', '/workouts', body);
      toast('Workout logged');
      await refresh();
    } catch (err) { toast(err.message); }
  });
  root.append(form);

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
        yaxis: { gridcolor: 'rgba(133,122,96,.14)', zeroline: false, fixedrange: true, title: { text: 'top weight', font: { size: 10 } } } }),
      CHART.config);

    Plotly.newPlot(card.querySelector('#prog-volume'),
      [{ x: series.map(s => s.date), y: series.map(s => s.volume), type: 'bar',
         marker: { color: CHART.steel, cornerradius: 4 },
         hovertemplate: '%{x}<br>volume %{y:,.0f} lbs<extra></extra>' }],
      CHART.layout({ margin: { l: 44, r: 16, t: 4, b: 30 }, height: 200, bargap: .45,
        yaxis: { gridcolor: 'rgba(133,122,96,.14)', zeroline: false, fixedrange: true, title: { text: 'volume', font: { size: 10 } } } }),
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
    const tr = el(`<tr><td>${esc(w.date)}</td><td>${esc(w.name)}</td>
      <td style="max-width:340px">${exs}</td><td class="num">${w.duration ?? 0}</td><td>${esc(w.intensity || '')}</td></tr>`);
    tr.append(rowActions('workouts', idx));
    tbody.append(tr);
  }
  root.append(wrap);
}
