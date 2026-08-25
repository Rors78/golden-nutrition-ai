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

  renderTape(root, state);
  renderPhotos(root, state);

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

// Progress photos: dated timeline, tap two to compare side by side.
// Files live in photos/ beside the data file — this machine only.
// THE MIRROR - progress photos as an instrument, not a gallery.
//
// The wipe: both photos stacked in one frame with a divider you drag.
// Side-by-side makes you compare two compositions; the wipe makes one body
// change under your thumb. Ghost mode overlays the newer photo at half
// opacity instead, for catching pose drift. Every photo is captioned with
// the nearest weigh-in (within 10 days), so a pair reads
// "2026-03-01 · 232.4 lb <-> 2026-08-24 · 200.0 lb · -32.4 lb · 176 days".

const MIRROR_MAX_PX = 1600;   // longest edge kept on upload

function nearestWeight(weights, day) {
  let best = null, bestD = 11;          // within 10 days, or say nothing
  for (const w of weights || []) {
    const d = Math.abs((new Date(w.date) - new Date(day)) / 86400000);
    if (d < bestD) { bestD = d; best = w.weight; }
  }
  return best;
}

// A phone photo is 8-12 MB of pixels the mirror never needs. Downscale in
// the browser so the photos directory does not swallow the disk. Returns
// null when the original is already small (or unreadable) - send it as-is.
async function shrinkImage(file) {
  try {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, MIRROR_MAX_PX / Math.max(bmp.width, bmp.height));
    if (k === 1 && file.size < 2500000) return null;
    const c = document.createElement('canvas');
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', 0.85);
  } catch { return null; }
}

function renderPhotos(root, state) {
  const ph = state.photos || [];
  const today = new Date().toISOString().slice(0, 10);
  const url = p => `/api/photos/${encodeURIComponent(p.file)}`;
  const card = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">The mirror</p>
    <p style="color:var(--muted);font-size:12px;margin:4px 0 10px">Same spot,
      same light, same pose — monthly beats daily. Photos stay on this machine
      (they are not inside the JSON backup). Tap two to compare, then drag the
      line across.</p>
    <div class="form-row">
      <button type="button" class="ghost-btn ph-add" style="flex:0 1 auto">Add photo</button>
      <label style="flex:0 1 auto">Taken on
        <input name="date" type="date" class="ph-date" value="${today}"></label>
      <input type="file" accept="image/*" capture="environment" hidden class="ph-input">
    </div>
    <div class="ph-strip"></div>
    <div class="mirror" hidden>
      <div class="mirror-stage">
        <img class="m-a" alt="earlier progress photo">
        <div class="m-top"><img class="m-b" alt="later progress photo"></div>
        <div class="m-line"><span></span></div>
      </div>
      <div class="mirror-caps">
        <span class="m-cap-a"></span><b class="m-delta"></b><span class="m-cap-b"></span>
      </div>
      <div class="mirror-tools">
        <button type="button" class="ghost-btn m-mode">Ghost view</button>
      </div>
    </div>
  </div>`);

  // -- capture --
  const input = card.querySelector('.ph-input');
  const addBtn = card.querySelector('.ph-add');
  addBtn.addEventListener('click', () => input.click());
  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    addBtn.disabled = true; addBtn.textContent = 'Adding…';
    try {
      const small = await shrinkImage(file);
      const image = small || await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result); r.onerror = rej;
        r.readAsDataURL(file);
      });
      const day = card.querySelector('.ph-date').value;
      await api('POST', '/photos', day ? { image, date: day } : { image });
      toast('Photo added');
      await refresh();                 // re-render resets the button
    } catch (e) {
      toast(e.message);
      addBtn.disabled = false; addBtn.textContent = 'Add photo';
    } finally { input.value = ''; }
  });

  // -- the mirror itself --
  const mirror = card.querySelector('.mirror');
  const stage = card.querySelector('.mirror-stage');
  const top = card.querySelector('.m-top');
  const line = card.querySelector('.m-line');
  const sel = [];
  let pct = 50;

  function setPct(v) {
    pct = Math.max(3, Math.min(97, v));
    top.style.clipPath = `inset(0 0 0 ${pct}%)`;
    line.style.left = pct + '%';
  }

  function caption(i) {
    const lb = nearestWeight(state.weights, ph[i].date);
    return `${ph[i].date}${lb != null ? ` · ${lb} lb` : ''}`;
  }

  function drawMirror() {
    if (sel.length < 2) { mirror.hidden = true; return; }
    // older on the left, newer revealed by the wipe — time reads rightward
    const [ia, ib] = [...sel].sort((x, y) => (ph[x].date < ph[y].date ? -1 : 1));
    card.querySelector('.m-a').src = url(ph[ia]);
    card.querySelector('.m-b').src = url(ph[ib]);
    card.querySelector('.m-cap-a').textContent = caption(ia);
    card.querySelector('.m-cap-b').textContent = caption(ib);
    const wa = nearestWeight(state.weights, ph[ia].date);
    const wb = nearestWeight(state.weights, ph[ib].date);
    const days = Math.round((new Date(ph[ib].date) - new Date(ph[ia].date)) / 86400000);
    const dlb = (wa != null && wb != null)
      ? `${wb - wa > 0 ? '+' : ''}${(wb - wa).toFixed(1)} lb · ` : '';
    card.querySelector('.m-delta').textContent = `${dlb}${days} days`;
    mirror.hidden = false;
    setPct(pct);
  }

  stage.addEventListener('pointerdown', ev => {
    if (mirror.classList.contains('ghost')) return;
    ev.preventDefault();
    stage.setPointerCapture(ev.pointerId);
    const move = e => {
      const r = stage.getBoundingClientRect();
      setPct((e.clientX - r.left) / r.width * 100);
    };
    move(ev);
    stage.addEventListener('pointermove', move);
    stage.addEventListener('pointerup',
      () => stage.removeEventListener('pointermove', move), { once: true });
  });

  const modeBtn = card.querySelector('.m-mode');
  modeBtn.addEventListener('click', () => {
    const ghost = mirror.classList.toggle('ghost');
    modeBtn.textContent = ghost ? 'Wipe view' : 'Ghost view';
  });

  // -- the strip --
  const strip = card.querySelector('.ph-strip');
  const paintSel = () => {
    [...strip.querySelectorAll('.ph-cell')].forEach((c, j) =>
      c.classList.toggle('sel', sel.includes(j)));
    drawMirror();
  };
  ph.forEach((p, i) => {
    const cell = el(`<div class="ph-cell">
      <img src="${url(p)}" alt="${esc(p.date)}" loading="lazy">
      <span>${esc(p.date)}</span>
      <button type="button" class="icon-btn danger" title="Delete"
        style="position:absolute;top:2px;right:2px">✕</button>
    </div>`);
    cell.querySelector('img').addEventListener('click', () => {
      const at = sel.indexOf(i);
      if (at >= 0) sel.splice(at, 1);
      else { sel.push(i); if (sel.length > 2) sel.shift(); }
      paintSel();
    });
    cell.querySelector('button').addEventListener('click', async ev => {
      const b = ev.target;
      if (b.dataset.armed) {
        try {
          await api('DELETE', `/photos/${i}`);
          toast('Photo deleted');
          await refresh();
        } catch (e) { toast(e.message); }
        return;
      }
      b.dataset.armed = '1';
      b.textContent = 'sure?';
      setTimeout(() => { delete b.dataset.armed; b.textContent = '✕'; }, 3000);
    });
    strip.append(cell);
  });
  if (!ph.length) {
    strip.append(el('<div class="empty" style="flex:1">No photos yet. The first one sets the baseline the rest are measured against.</div>'));
  }

  // First and latest, pre-selected: two photos in the file means the mirror
  // opens already showing the span, not an empty stage waiting for taps.
  if (ph.length >= 2) { sel.push(0, ph.length - 1); }
  paintSel();

  root.append(card);
}

const TAPE_FIELDS = [['neck_in', 'Neck'], ['chest_in', 'Chest'], ['waist_in', 'Waist'],
  ['hips_in', 'Hips'], ['arm_in', 'Arm'], ['thigh_in', 'Thigh']];

// Where to put the tape. Placement error is the whole game: a waist measured
// at the navel one week and at the narrowest point the next produces a change
// that is pure noise, and the app cannot tell the difference. These are the
// standard anthropometric sites, phrased so they land the same way every time.
const TAPE_HOWTO = {
  neck_in: 'Just below the larynx, tape sloping slightly down at the front. Do not flex.',
  chest_in: 'Across the nipples, arms relaxed at your sides, at the end of a normal breath out.',
  waist_in: 'At the navel, not the narrowest point. Relaxed — do not suck in.',
  hips_in: 'The widest point of the glutes, feet together.',
  arm_in: 'Midway between shoulder and elbow, arm hanging relaxed. Same arm every time.',
  thigh_in: 'Just below the glute fold, weight on both feet. Same leg every time.',
};

// Which sites the Navy body-fat formula actually consumes. The rest are for
// tracking shape change; they do not feed the estimate.
const NAVY_SITES = { male: ['waist_in', 'neck_in'], female: ['waist_in', 'neck_in', 'hips_in'] };

// Tape measurements + Navy body-fat estimate. Renders even before the first
// weigh-in — the tape and the scale are independent habits.
function renderTape(root, state) {
  const ms = state.measurements || [];
  const bc = state.stats.body_comp || {};
  const last = ms[ms.length - 1], prev = ms[ms.length - 2];
  const today = new Date().toISOString().slice(0, 10);
  const needed = NAVY_SITES[(state.profile.sex || '').toLowerCase()] || [];

  const card = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">Tape measurements${bc.current != null
      ? ` · <span class="bf-read ${esc(bc.confidence || '')}">~${bc.current}% body fat</span>${
        bc.change != null ? ` <span style="font-size:11px;color:${bc.change <= 0 ? 'var(--good)' : 'var(--warn)'}">(${bc.change > 0 ? '+' : ''}${bc.change} since first)</span>` : ''}`
      : ''}</p>
    ${bc.confidence && bc.confidence !== 'current' ? `<p class="tape-stale">Last measured ${
      bc.age_days} days ago — ${bc.confidence === 'stale'
        ? 'too old to describe you now. Re-tape to make this current.'
        : 'starting to age. A fresh set keeps the trend honest.'}</p>` : ''}
    <p style="color:var(--muted);font-size:12px;margin:4px 0 10px">Inches, same conditions every time — morning, relaxed, tape snug not tight. One row per day; re-logging a day updates it.${
      bc.current != null ? ' Body fat is the US Navy tape estimate — track the trend, not the decimal.' : ''}</p>
    ${bc.hint ? `<div class="callout" style="margin-bottom:10px">${esc(bc.hint)}</div>` : ''}
    <form class="tape-form">
      <label class="tape-date">Date <input name="date" type="date" value="${today}"></label>
      <div class="tape-grid">
        ${TAPE_FIELDS.map(([f, label]) => `<label class="tape-field${needed.includes(f) ? ' key' : ''}">
          <span class="tf-head">${label}${needed.includes(f)
            ? '<i class="tf-tag" title="Feeds the body-fat estimate">bf</i>' : ''}</span>
          <input name="${f}" type="number" step="0.1" min="0" max="99" inputmode="decimal"
                 placeholder="${last?.[f] ?? '—'}">
          <small class="tf-how">${esc(TAPE_HOWTO[f] || '')}</small>
        </label>`).join('')}
      </div>
      <div class="tape-submit">
        <button class="gold-btn" type="submit">Log tape</button>
        <span class="tape-note">${esc(needed.length
          ? `Waist and neck alone give the body-fat estimate — the rest track shape.`
          : 'Set your sex in Profile and waist + neck will estimate body fat.')}</span>
      </div>
    </form>
    <div class="tape-latest" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"></div>
    <div class="tape-chart-slot"></div>
  </div>`);

  card.querySelector('form').addEventListener('submit', async e => {
    e.preventDefault();
    const entries = Object.fromEntries(new FormData(e.target).entries());
    // A tape jump of >2 inches in one logging is almost always the tape in a
    // different place, not the body. Confirming beats silently recording a
    // number that will read as real change forever afterwards.
    if (last) {
      const odd = TAPE_FIELDS
        .filter(([f]) => entries[f] && last[f] && Math.abs(+entries[f] - last[f]) > 2)
        .map(([f, label]) => `${label}: ${last[f]}" → ${(+entries[f]).toFixed(1)}"`);
      if (odd.length && !confirm(
        `That is a big change since your last tape:\n\n${odd.join('\n')}\n\n`
        + `Usually this means the tape sat somewhere different. Log it anyway?`)) return;
    }
    try {
      await api('POST', '/measurements', entries);
      toast('Tape logged');
      await refresh();
    } catch (err) { toast(err.message); }
  });

  // latest values with deltas vs the previous logging
  const latest = card.querySelector('.tape-latest');
  if (last) {
    for (const [f, label] of TAPE_FIELDS) {
      if (last[f] == null) continue;
      const d = prev?.[f] != null ? Math.round((last[f] - prev[f]) * 10) / 10 : null;
      latest.append(el(`<span style="display:inline-flex;flex-direction:column;gap:2px;padding:7px 12px;border-radius:var(--radius-sm);border:1px solid var(--line);background:var(--bg)">
        <span style="font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)">${label}</span>
        <span style="font-family:var(--font-mono);font-size:14px;font-weight:700">${last[f]}″
          ${d != null && d !== 0 ? `<small style="color:var(--muted);font-weight:400">${d > 0 ? '+' : ''}${d}</small>` : ''}</span>
      </span>`));
    }
  }

  // trend chart for whichever tape line has history
  const charted = TAPE_FIELDS.filter(([f]) => ms.filter(m => m[f] != null).length >= 2);
  if (charted.length) {
    const slot = card.querySelector('.tape-chart-slot');
    slot.append(el(`<div>
      <div class="form-row" style="align-items:center;margin-top:14px">
        <p class="chart-title" style="margin:0;flex:0 1 auto">Trend</p>
        <label style="flex:0 1 200px"><select class="tape-sel">
          ${charted.map(([f, label], i) => `<option value="${f}"${i === 0 ? ' selected' : ''}>${label}</option>`).join('')}
          ${bc.series?.length >= 2 ? '<option value="bf">Body fat %</option>' : ''}
        </select></label></div>
      <div class="chart tape-chart" style="min-height:180px"></div>
    </div>`));
    const draw = f => {
      const pts = f === 'bf'
        ? bc.series.map(x => ({ date: x.date, v: x.bf }))
        : ms.filter(m => m[f] != null).map(m => ({ date: m.date, v: m[f] }));
      Plotly.newPlot(slot.querySelector('.tape-chart'),
        [{ x: pts.map(x => x.date), y: pts.map(x => x.v), mode: 'lines+markers',
           line: { color: CHART.gold, width: 2 }, marker: { size: 6, color: CHART.gold },
           hovertemplate: `%{x}<br>%{y:.1f}${f === 'bf' ? '%' : '″'}<extra></extra>` }],
        CHART.layout({ height: 180, margin: { l: 40, r: 12, t: 8, b: 28 } }),
        CHART.config);
    };
    slot.querySelector('.tape-sel').addEventListener('change', ev => draw(ev.target.value));
    draw(charted[0][0]);
  }

  // recent rows, deletable (index into the stored, date-sorted list)
  if (ms.length) {
    const wrap = el(`<div class="table-wrap" style="margin-top:12px"><table>
      <thead><tr><th>Date</th>${TAPE_FIELDS.map(([, l]) => `<th class="num">${l}</th>`).join('')}<th></th></tr></thead>
      <tbody></tbody></table></div>`);
    const tbody = wrap.querySelector('tbody');
    ms.map((m, idx) => ({ m, idx })).slice(-5).reverse().forEach(({ m, idx }) => {
      const tr = el(`<tr><td>${esc(m.date)}</td>
        ${TAPE_FIELDS.map(([f]) => `<td class="num">${m[f] ?? '—'}</td>`).join('')}</tr>`);
      tr.append(rowActions('measurements', idx));
      tbody.append(tr);
    });
    card.append(wrap);
  }

  root.append(card);
}
