// Vitals: wearable/manual body data — steps, heart, sleep, blood pressure —
// with the webhook + notification setup that makes the coach ambient.
import { el, esc, api, toast, refresh, metric, CHART } from '../app.js';

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
    // ── latest numbers ──
    const L = vs.latest;
    const grid = el('<div class="cards metrics" style="margin-top:14px"></div>');
    const add = (label, entry, opts = {}) => {
      if (entry) grid.append(metric(label, entry.value, { ...opts, small: `${opts.small || ''}${opts.small ? ' · ' : ''}${entry.date}` }));
    };
    add('Steps', L.steps, { small: `goal ${vs.steps_goal}` });
    add('Resting HR', L.resting_hr, { suffix: ' bpm' });
    add('HRV', L.hrv_ms, { suffix: ' ms' });
    add('Sleep', L.sleep_h, { suffix: ' h' });
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
