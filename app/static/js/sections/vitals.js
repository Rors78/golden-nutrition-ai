// Vitals: wearable/manual body data — steps, heart, sleep, blood pressure —
// readiness breakdown, early-warning signals, and the device/notify setup.
import { el, esc, api, toast, refresh, metric, rowActions, CHART } from '../app.js';

const VITAL_FIELDS = ['steps', 'resting_hr', 'hrv_ms', 'sleep_h', 'bp_sys', 'bp_dia'];
const FIELD_LABELS = { steps: 'Steps', resting_hr: 'RHR', hrv_ms: 'HRV',
                       sleep_h: 'Sleep', bp_sys: 'Sys', bp_dia: 'Dia' };

export function renderVitals(root, state) {
  const vs = state.stats.vitals;
  const settings = state.settings || {};

  root.append(el('<h2 class="section-title">Vitals</h2>'));
  root.append(el('<p class="section-sub">Steps, heart, sleep, and blood pressure — synced from your watch or logged by hand. Informational, not medical advice.</p>'));

  // ── manual entry ──
  const today = new Date().toISOString().slice(0, 10);
  const form = el(`<form class="panel">
    <p class="chart-title">Log a day</p>
    <div class="grid-3" style="margin-top:8px">
      <label>Date <input name="date" type="date" value="${today}"></label>
      <label>Steps <input name="steps" type="number" min="0" placeholder="8500"></label>
      <label>Resting HR (bpm) <input name="resting_hr" type="number" min="0" placeholder="58"></label>
      <label>HRV (ms) <input name="hrv_ms" type="number" min="0" step="0.1" placeholder="45"></label>
      <label>Sleep (hours) <input name="sleep_h" type="number" min="0" step="0.1" placeholder="7.5"></label>
      <label style="flex-direction:row;gap:8px;align-items:end">
        <span style="display:flex;flex-direction:column;gap:6px;flex:1">BP systolic <input name="bp_sys" type="number" min="0" placeholder="120"></span>
        <span style="display:flex;flex-direction:column;gap:6px;flex:1">diastolic <input name="bp_dia" type="number" min="0" placeholder="80"></span>
      </label>
    </div>
    <div style="margin-top:12px"><button class="gold-btn" type="submit">Save vitals</button>
      <span style="color:var(--muted);font-size:12px;margin-left:10px">Fill any subset — a re-log for the same day merges.</span></div>
  </form>`);
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const body = Object.fromEntries([...new FormData(form).entries()].filter(([, v]) => v !== ''));
    try {
      await api('POST', '/vitals', body);
      toast('Vitals saved');
      await refresh();
    } catch (err) { toast(err.message); }
  });
  root.append(form);

  if (vs.has_data) {
    // ── readiness breakdown ──
    const rd = state.stats.readiness;
    if (rd?.has_data) {
      const card = el(`<div class="card" style="margin-top:14px">
        <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
          <span class="plate-disc ${rd.score >= 80 ? '' : rd.score >= 60 ? 'steel' : rd.score >= 40 ? 'iron' : 'rust'}"
            style="width:64px;height:64px;font-size:22px">${rd.score}</span>
          <div style="flex:1;min-width:220px">
            <p class="chart-title" style="margin:0">Readiness · ${esc(rd.level)} · ${esc(rd.date)}</p>
            <p style="margin:4px 0 0;color:var(--ink-2);font-size:13px">${esc(rd.guidance)}</p>
          </div>
        </div>
        <div class="rd-comps" style="display:grid;gap:8px;margin-top:14px"></div>
      </div>`);
      const comps = card.querySelector('.rd-comps');
      const NAMES = { sleep: 'Sleep', hrv: 'HRV', resting_hr: 'Resting HR' };
      const UNITS = { sleep: 'h', hrv: ' ms', resting_hr: ' bpm' };
      for (const [key, c] of Object.entries(rd.components)) {
        comps.append(el(`<div>
          <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ink-2);margin-bottom:4px">
            <span>${NAMES[key] || key}</span>
            <span style="font-family:var(--font-mono)">${c.value}${UNITS[key] || ''} vs baseline ${c.baseline}${UNITS[key] || ''} · ${c.score}</span>
          </div>
          <div style="height:6px;border-radius:3px;background:var(--card-2)">
            <div style="height:6px;border-radius:3px;width:${c.score}%;background:${c.score >= 80 ? 'var(--good)' : c.score >= 60 ? 'var(--gold)' : 'var(--warn)'}"></div>
          </div></div>`));
      }
      root.append(card);
    }

    // ── readiness trend, 28 days ──
    const rSeries = state.stats.readiness_series || [];
    if (rSeries.length > 2) {
      const rtCard = el(`<div class="card" style="margin-top:14px">
        <p class="chart-title">Readiness · last 28 days</p>
        <div class="chart" style="min-height:190px"></div></div>`);
      root.append(rtCard);
      const band = (y0, y1, color) => ({ type: 'rect', xref: 'paper', x0: 0, x1: 1, y0, y1,
        fillcolor: color, opacity: 0.06, line: { width: 0 }, layer: 'below' });
      Plotly.newPlot(rtCard.querySelector('.chart'),
        [{ x: rSeries.map(r => r.date), y: rSeries.map(r => r.score),
           mode: 'lines+markers', line: { color: CHART.gold, width: 2, shape: 'spline' },
           marker: { size: 6, color: rSeries.map(r => r.score >= 80 ? '#3ec97e' : r.score >= 60 ? '#f2c14e' : r.score >= 40 ? '#8b93a1' : '#e07a4f') },
           hovertemplate: '%{x}<br>readiness %{y}<extra></extra>' }],
        CHART.layout({ height: 190, margin: { l: 38, r: 10, t: 6, b: 30 },
          yaxis: { range: [0, 105], gridcolor: 'rgba(110,118,131,.14)', zeroline: false, fixedrange: true },
          shapes: [band(80, 105, '#3ec97e'), band(60, 80, '#f2c14e'), band(0, 40, '#e07a4f')] }),
        CHART.config);
    }

    // ── early-warning signals ──
    for (const s of vs.signals || []) {
      root.append(el(`<div class="callout ${s.level === 'good' ? 'good' : 'warn'}" style="margin-top:10px">${esc(s.text)}</div>`));
    }

    // ── latest numbers with trend deltas ──
    const L = vs.latest;
    const grid = el('<div class="cards metrics" style="margin-top:14px"></div>');
    const add = (label, entry, field, opts = {}) => {
      if (!entry) return;
      const dl = vs.deltas?.[field];
      const delta = dl && dl.diff !== 0
        ? { cls: dl.good ? (dl.diff > 0 ? 'up-good' : 'down-good') : (dl.diff > 0 ? 'up-bad' : 'down-bad'),
            text: `${dl.diff > 0 ? '+' : ''}${dl.diff} vs 7d avg` }
        : null;
      grid.append(metric(label, entry.value,
        { ...opts, delta, small: `${opts.small || ''}${opts.small ? ' · ' : ''}${entry.date}` }));
    };
    add('Steps', L.steps, 'steps', { small: `goal ${vs.steps_goal}` });
    const ss = state.stats.step_stats;
    if (ss?.has_goal) {
      grid.append(metric('Step-goal streak', ss.streak, { suffix: 'd', small: `${ss.hits_14}/14 days hit` }));
    }
    add('Resting HR', L.resting_hr, 'resting_hr', { suffix: ' bpm' });
    add('HRV', L.hrv_ms, 'hrv_ms', { suffix: ' ms' });
    add('Sleep', L.sleep_h, 'sleep_h', { suffix: ' h' });
    if (vs.sleep_debt) {
      grid.append(metric('Sleep debt', vs.sleep_debt.hours,
        { suffix: 'h', small: `${vs.sleep_debt.days} nights vs ${vs.sleep_debt.target}h` }));
    }
    if (vs.bp) grid.append(metric('Blood pressure', `${vs.bp.sys}/${vs.bp.dia}`, { small: vs.bp.date }));
    root.append(grid);

    // BP context callout — informational only
    if (vs.bp && vs.bp.level !== 'normal') {
      const msg = {
        elevated: `Latest reading ${vs.bp.sys}/${vs.bp.dia} sits in the elevated range. Worth tracking daily and mentioning at your next checkup.`,
        high: `Latest reading ${vs.bp.sys}/${vs.bp.dia} is in the high range. This app is not a medical device — bring these numbers to a doctor or pharmacist.`,
        urgent: `Latest reading ${vs.bp.sys}/${vs.bp.dia} is very high. If this reading is accurate and repeated, seek medical care promptly.`,
      }[vs.bp.level];
      root.append(el(`<div class="callout warn" style="margin-top:14px">${esc(msg)}</div>`));
    }

    // ── charts ──
    const series = vs.series;
    const chart = (title, traces, extra = {}) => {
      const c = el(`<div class="card" style="margin-top:14px"><p class="chart-title">${title}</p><div class="chart" style="min-height:200px"></div></div>`);
      root.append(c);
      Plotly.newPlot(c.querySelector('.chart'), traces,
        CHART.layout({ margin: { l: 44, r: 16, t: 6, b: 30 }, height: 200, ...extra }), CHART.config);
    };
    const pts = f => series.filter(v => v[f] != null);

    if (pts('steps').length) {
      chart('Steps',
        [{ x: pts('steps').map(v => v.date), y: pts('steps').map(v => v.steps), type: 'bar',
           marker: { color: CHART.gold, cornerradius: 4 },
           hovertemplate: '%{x}<br>%{y:,} steps<extra></extra>' }],
        { bargap: .45,
          shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: vs.steps_goal, y1: vs.steps_goal,
            line: { color: CHART.good, width: 1, dash: 'dot' } }] });
    }
    if (pts('resting_hr').length || pts('hrv_ms').length) {
      const traces = [];
      if (pts('resting_hr').length) traces.push({
        x: pts('resting_hr').map(v => v.date), y: pts('resting_hr').map(v => v.resting_hr),
        mode: 'lines+markers', line: { color: CHART.steel, width: 2 }, marker: { size: 6 },
        hovertemplate: '%{x}<br>%{y} bpm<extra>resting HR</extra>' });
      if (pts('hrv_ms').length) traces.push({
        x: pts('hrv_ms').map(v => v.date), y: pts('hrv_ms').map(v => v.hrv_ms),
        mode: 'lines+markers', line: { color: CHART.gold, width: 2 }, marker: { size: 6 },
        hovertemplate: '%{x}<br>%{y} ms<extra>HRV</extra>' });
      chart(`Heart — <span style="color:var(--steel)">resting HR</span>${pts('hrv_ms').length ? ' · <span style="color:var(--gold)">HRV</span>' : ''}`, traces);
    }
    if (pts('sleep_h').length) {
      chart('Sleep hours',
        [{ x: pts('sleep_h').map(v => v.date), y: pts('sleep_h').map(v => v.sleep_h), type: 'bar',
           marker: { color: CHART.steel, cornerradius: 4 },
           hovertemplate: '%{x}<br>%{y} h<extra></extra>' }], { bargap: .45 });
    }
    if (pts('bp_sys').length) {
      chart('Blood pressure — <span style="color:var(--gold)">systolic</span> · <span style="color:var(--steel)">diastolic</span>',
        [{ x: pts('bp_sys').map(v => v.date), y: pts('bp_sys').map(v => v.bp_sys),
           mode: 'lines+markers', line: { color: CHART.gold, width: 2 }, marker: { size: 6 },
           hovertemplate: '%{x}<br>%{y} mmHg<extra>systolic</extra>' },
         { x: pts('bp_dia').map(v => v.date), y: pts('bp_dia').map(v => v.bp_dia),
           mode: 'lines+markers', line: { color: CHART.steel, width: 2 }, marker: { size: 6 },
           hovertemplate: '%{x}<br>%{y} mmHg<extra>diastolic</extra>' }]);
    }
    // ── weekly recovery report ──
    const vweeks = state.stats.vitals_weeks || [];
    if (vweeks.length > 1) {
      const GOODUP = { steps: true, resting_hr: false, hrv_ms: true, sleep_h: true };
      const rep = el(`<div class="card" style="margin-top:14px">
        <p class="chart-title">Weekly recovery report</p>
        <div class="table-wrap" style="margin-top:8px"><table>
          <thead><tr><th>Week of</th><th class="num">Steps</th><th class="num">RHR</th>
            <th class="num">HRV</th><th class="num">Sleep</th><th class="num">Days</th></tr></thead>
          <tbody></tbody></table></div></div>`);
      const tb = rep.querySelector('tbody');
      const cell = (row, f, fmt = x => x) => {
        if (row[f] == null) return '<td class="num" style="color:var(--muted)">—</td>';
        const d = row[`${f}_delta`];
        let deltaHtml = '';
        if (d != null && d !== 0) {
          const good = (d > 0) === GOODUP[f];
          deltaHtml = ` <span style="font-size:10px;color:${good ? 'var(--good)' : 'var(--warn)'}">${d > 0 ? '▲' : '▼'}${Math.abs(d)}</span>`;
        }
        return `<td class="num">${fmt(row[f])}${deltaHtml}</td>`;
      };
      for (const row of [...vweeks].reverse()) {
        tb.append(el(`<tr><td>${esc(row.week_start)}</td>
          ${cell(row, 'steps', x => Math.round(x).toLocaleString())}
          ${cell(row, 'resting_hr')}${cell(row, 'hrv_ms')}${cell(row, 'sleep_h')}
          <td class="num" style="color:var(--muted)">${row.n}</td></tr>`));
      }
      root.append(rep);
    }

    // ── history, editable ──
    root.append(el('<p class="chart-title" style="margin:18px 0 8px">History · last 14 days</p>'));
    const indexed = state.vitals.map((v, idx) => ({ v, idx })).slice(-14).reverse();
    const wrap = el(`<div class="table-wrap"><table>
      <thead><tr><th>Date</th>${VITAL_FIELDS.map(f => `<th class="num">${FIELD_LABELS[f]}</th>`).join('')}<th></th></tr></thead>
      <tbody></tbody></table></div>`);
    const tbody = wrap.querySelector('tbody');
    for (const { v, idx } of indexed) {
      const tr = el(`<tr><td>${esc(v.date)}</td>${VITAL_FIELDS.map(f =>
        `<td class="num">${v[f] ?? '—'}</td>`).join('')}</tr>`);
      tr.append(rowActions('vitals', idx, { onEdit: () => editRow(tr, v, idx) }));
      tbody.append(tr);
    }
    root.append(wrap);

    function editRow(tr, v, idx) {
      tr.classList.add('editing');
      tr.innerHTML = `<td><input type="date" value="${esc(v.date)}"></td>
        ${VITAL_FIELDS.map(f => `<td><input type="number" step="0.1" value="${v[f] ?? ''}" data-f="${f}"></td>`).join('')}
        <td class="row-actions"><button class="icon-btn" title="Save">✓</button><button class="icon-btn danger" title="Cancel">↩</button></td>`;
      tr.querySelector('.icon-btn').addEventListener('click', async () => {
        const body = { date: tr.querySelector('input[type=date]').value };
        tr.querySelectorAll('input[data-f]').forEach(inp => { body[inp.dataset.f] = inp.value; });
        try {
          await api('PUT', `/entry/vitals/${idx}`, body);
          toast('Saved');
          await refresh();
        } catch (e) { toast(e.message); }
      });
      tr.querySelector('.danger').addEventListener('click', () => refresh());
    }
  } else {
    root.append(el('<div class="empty" style="margin-top:14px">No vitals yet. Log a day above, or wire up your watch below — either works.</div>'));
  }

  // ── device + notification setup ──
  const origin = location.origin;
  const setup = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">Connect your Samsung watch & phone</p>
    <div style="font-size:13px;color:var(--ink-2);line-height:1.7;margin-top:8px">
      <p style="margin:0 0 8px"><strong style="color:var(--ink)">1 · Data in (watch → app).</strong>
        Your Galaxy Watch syncs into <em>Samsung Health</em>, which shares with Android's
        <em>Health Connect</em>. Install a Health Connect exporter app (e.g. “Health Connect Sync”
        or any exporter that can POST JSON to a URL) and point it at this webhook — one row per day,
        any of: steps, resting_hr, hrv_ms, sleep_h, bp_sys, bp_dia.</p>
      <p style="margin:0 0 8px;font-family:var(--font-mono);font-size:12px;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;overflow-wrap:anywhere">
        POST ${esc(origin)}/api/ingest?token=${esc(settings.ingest_token || '…')}</p>
      <p style="margin:0 0 14px;color:var(--muted)">Phone and server must share a network (or a tunnel). The token is the lock — regenerating it is a data-file edit away.</p>
      <p style="margin:0 0 8px"><strong style="color:var(--ink)">2 · Coach out (app → wrist).</strong>
        Install the free <em>ntfy</em> app on your phone, subscribe to a topic, enter it here —
        pushes land on the phone and mirror to the watch.</p>
    </div>
    <form class="form-row" style="margin-top:6px">
      <label style="flex:2 1 200px">ntfy topic <input name="ntfy_topic" type="text"
        value="${esc(settings.ntfy_topic || '')}" placeholder="golden-nutrition-x7k2p9"></label>
      <label>Daily step goal <input name="daily_steps" type="number" min="0"
        value="${esc(settings.daily_steps || 8000)}"></label>
      <label>Sleep target (h) <input name="sleep_target" type="number" min="4" max="12" step="0.5"
        value="${esc(settings.sleep_target || 7.5)}"></label>
      <button class="gold-btn" type="submit" style="flex:0 1 auto">Save</button>
      <button class="ghost-btn test-push" type="button" style="flex:0 1 auto">Send test push</button>
    </form>
  </div>`);
  setup.querySelector('form').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('POST', '/settings', Object.fromEntries(new FormData(e.target).entries()));
      toast('Settings saved');
      await refresh();
    } catch (err) { toast(err.message); }
  });
  setup.querySelector('.test-push').addEventListener('click', async () => {
    try {
      await api('POST', '/notify/test');
      toast('Test push sent — check your phone');
    } catch (e) { toast(e.message); }
  });
  root.append(setup);
}
