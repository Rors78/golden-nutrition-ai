// Weight: daily weigh-ins, trend, goal projection, interactive chart.
import { el, esc, api, toast, refresh, metric, rowActions, barbell, CHART } from '../app.js';

export function renderWeight(root, state) {
  const w = state.stats.weight;
  const today = new Date().toISOString().slice(0, 10);

  root.append(el('<h2 class="section-title">Weight</h2>'));
  root.append(el('<p class="section-sub">One weigh-in per day — re-logging a day replaces it. Daily beats perfect.</p>'));

  const form = el(`<form class="panel form-row">
    <label>Date <input name="date" type="date" value="${today}" required></label>
    <label>Weight (lbs) <input name="weight" type="number" step="0.1" min="1"
      value="${state.profile.weight || ''}" placeholder="200.0" required></label>
    <button class="gold-btn" type="submit">Log weigh-in</button>
  </form>`);
  form.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('POST', '/weights', Object.fromEntries(new FormData(form).entries()));
      toast('Weigh-in logged');
      await refresh();
    } catch (err) { toast(err.message); }
  });
  root.append(form);

  if (!w.has_data) {
    root.append(el('<div class="empty" style="margin-top:14px">No weigh-ins yet. Log the first one above.</div>'));
    return;
  }

  const grid = el('<div class="cards metrics" style="margin-top:14px"></div>');
  const deltaCls = w.change_7d == null ? '' :
    (w.cutting ? (w.change_7d <= 0 ? 'down-good' : 'up-bad') : (w.change_7d >= 0 ? 'up-good' : 'down-bad'));
  grid.append(
    metric('Current', w.current, { suffix: ' lbs', delta: w.change_7d == null ? null :
      { cls: deltaCls, text: `${w.change_7d > 0 ? '+' : ''}${w.change_7d} lbs · 7d` } }),
    metric('To goal', w.goal ? Math.abs(w.current - w.goal).toFixed(1) : '—',
      { suffix: w.goal ? ' lbs' : '', small: w.goal ? `goal ${w.goal}` : 'set in Profile' }),
    metric('Trend', w.rate_per_week ?? '—',
      { suffix: w.rate_per_week != null ? ' lbs/wk' : '', small: '30-day' }),
    metric('Total change', `${w.total_change > 0 ? '+' : ''}${w.total_change}`,
      { suffix: ' lbs', small: `since ${w.since}` }),
  );
  if (w.bmi) {
    grid.append(metric('BMI', w.bmi.value, { small: w.bmi.category }));
  } else {
    grid.append(metric('BMI', '—', { small: 'add height in Profile' }));
  }
  const wx = state.stats.weight_extras || {};
  grid.append(metric('Weigh-in streak', wx.streak ?? 0, { suffix: 'd', small: 'daily beats perfect' }));
  root.append(grid);

  if (wx.plateau) {
    root.append(el(`<div class="callout warn" style="margin-top:14px">${esc(wx.plateau)}</div>`));
  }

  // ── the milestone road ──
  if (wx.milestones?.length) {
    const done = wx.milestones.filter(m => m.crossed).length;
    const mCard = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">The road to ${esc(w.goal)} — 5 lb plates</p>
      <div class="ms-row" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"></div>
    </div>`);
    const row = mCard.querySelector('.ms-row');
    for (const m of wx.milestones) {
      row.append(el(`<span title="${m.crossed ? `crossed ${esc(m.date)}` : 'not yet'}"
        style="display:inline-flex;flex-direction:column;align-items:center;gap:3px;min-width:64px;padding:8px 10px;border-radius:var(--radius-sm);
        border:1px solid ${m.crossed ? 'var(--gold)' : 'var(--line)'};background:${m.crossed ? 'rgba(242,193,78,.08)' : 'var(--bg)'}">
        <span style="font-family:var(--font-mono);font-weight:700;font-size:15px;color:${m.crossed ? 'var(--gold-bright)' : 'var(--muted)'}">${m.target}</span>
        <span style="font-size:10px;color:${m.crossed ? 'var(--good)' : 'var(--muted)'}">${m.crossed ? esc(m.date.slice(5)) : `${Math.abs(w.current - m.target).toFixed(1)} to go`}</span>
      </span>`));
    }
    if (wx.next_milestone) {
      mCard.append(barbell('Plates racked', done, wx.milestones.length, ''));
      mCard.append(el(`<p style="margin:8px 0 0;font-size:12px;color:var(--ink-2)">Next plate:
        <strong style="color:var(--gold-bright)">${esc(wx.next_milestone.target)} lbs</strong> —
        ${esc(wx.next_milestone.to_go)} lbs to go.</p>`));
    } else {
      mCard.append(el('<div class="callout good" style="margin-top:12px">Every plate racked — goal reached. Set the next one in Profile.</div>'));
    }
    root.append(mCard);
  }

  // ── weekly check-ins ──
  if (wx.weeks?.length > 1) {
    const wkCard = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Weekly check-ins — averages, not noise</p>
      <div class="table-wrap" style="margin-top:8px"><table>
        <thead><tr><th>Week of</th><th class="num">Avg (lbs)</th><th class="num">Change</th><th class="num">Weigh-ins</th></tr></thead>
        <tbody></tbody></table></div></div>`);
    const tb = wkCard.querySelector('tbody');
    for (const wk of [...wx.weeks].reverse()) {
      const good = wk.delta != null && (wx.cutting ? wk.delta < 0 : wk.delta > 0);
      const deltaTxt = wk.delta == null ? '—' : `${wk.delta > 0 ? '+' : ''}${wk.delta}`;
      tb.append(el(`<tr><td>${esc(wk.week_start)}</td>
        <td class="num">${wk.avg.toFixed(1)}</td>
        <td class="num" style="color:${wk.delta == null ? 'var(--muted)' : good ? 'var(--good)' : Math.abs(wk.delta) < 0.3 ? 'var(--muted)' : 'var(--warn)'};font-family:var(--font-mono)">${deltaTxt}</td>
        <td class="num" style="color:var(--muted)">${wk.n}</td></tr>`));
    }
    root.append(wkCard);
  }

  if (w.pace) {
    root.append(el(`<div class="callout ${w.pace.level === 'good' ? 'good' : w.pace.level === 'warn' ? 'warn' : ''}"
      style="margin-top:14px">${esc(w.pace.text)}</div>`));
  }

  if (w.eta) {
    root.append(el(`<div class="callout good" style="margin-top:14px">At ${w.rate_per_week > 0 ? '+' : ''}${w.rate_per_week} lbs/week
      you'll reach <strong>${esc(w.goal)} lbs around ${esc(w.eta)}</strong> (${esc(w.eta_days)} days).</div>`));
  } else if (w.off_track) {
    root.append(el(`<div class="callout warn" style="margin-top:14px">Your trend (${w.rate_per_week} lbs/week)
      is moving away from your ${esc(w.goal)} lbs goal.</div>`));
  }

  const chartCard = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">Weight over time</p>
    <p style="color:var(--muted);font-size:12px;margin:4px 0 0">
      <span style="color:var(--gold)">●</span> daily &nbsp;
      <span style="color:var(--steel)">—</span> 7-day average &nbsp;
      ${w.eta_date_iso ? '<span style="color:var(--good)">┄</span> projection to goal' : ''}</p>
    <div class="chart" id="weight-chart"></div></div>`);
  root.append(chartCard);
  const dates = w.series.map(x => x.date);
  const vals = w.series.map(x => x.weight);
  const traces = [
    { x: dates, y: vals, mode: 'markers', name: 'Daily',
      marker: { size: 6, color: CHART.gold, opacity: 0.75 },
      hovertemplate: '%{x}<br>%{y:.1f} lbs<extra>daily</extra>' },
    { x: w.series_avg.map(x => x.date), y: w.series_avg.map(x => x.avg),
      mode: 'lines', name: '7-day avg',
      line: { color: CHART.steel, width: 2, shape: 'spline' },
      hovertemplate: '%{x}<br>%{y:.1f} lbs<extra>7-day avg</extra>' },
  ];
  if (w.eta_date_iso) {
    traces.push({
      x: [dates[dates.length - 1], w.eta_date_iso], y: [w.current, w.goal],
      mode: 'lines', name: 'Projection',
      line: { color: CHART.good, width: 1.5, dash: 'dash' },
      hovertemplate: '%{x}<br>%{y:.1f} lbs<extra>projected</extra>',
    });
  }
  const layout = CHART.layout();
  if (w.goal) {
    layout.shapes = [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: w.goal, y1: w.goal,
      line: { color: CHART.good, width: 1, dash: 'dot' } }];
    layout.annotations = [{ xref: 'paper', x: 1, y: w.goal, text: `goal ${w.goal}`,
      showarrow: false, font: { size: 10, color: CHART.good }, yshift: 10, xanchor: 'right' }];
  }
  Plotly.newPlot(chartCard.querySelector('.chart'), traces, layout, CHART.config);

  // history table with inline edit
  const wrap = el(`<div class="table-wrap" style="margin-top:14px"><table>
    <thead><tr><th>Date</th><th class="num">Weight (lbs)</th><th></th></tr></thead>
    <tbody></tbody></table></div>`);
  const tbody = wrap.querySelector('tbody');
  const indexed = state.weights.map((entry, idx) => ({ entry, idx })).reverse();
  for (const { entry, idx } of indexed) {
    const tr = el(`<tr><td>${esc(entry.date)}</td><td class="num">${Number(entry.weight).toFixed(1)}</td></tr>`);
    tr.append(rowActions('weights', idx, { onEdit: () => editRow(tr, entry, idx) }));
    tbody.append(tr);
  }
  root.append(wrap);

  function editRow(tr, entry, idx) {
    tr.classList.add('editing');
    tr.innerHTML = `<td><input type="date" value="${esc(entry.date)}"></td>
      <td><input type="number" step="0.1" value="${esc(entry.weight)}"></td>
      <td class="row-actions"><button class="icon-btn" title="Save">✓</button><button class="icon-btn danger" title="Cancel">↩</button></td>`;
    const [dateIn, weightIn] = tr.querySelectorAll('input');
    tr.querySelector('.icon-btn').addEventListener('click', async () => {
      try {
        await api('PUT', `/entry/weights/${idx}`, { date: dateIn.value, weight: weightIn.value });
        toast('Saved');
        await refresh();
      } catch (e) { toast(e.message); }
    });
    tr.querySelector('.danger').addEventListener('click', () => refresh());
  }
}
