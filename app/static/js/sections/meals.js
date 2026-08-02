// Meals: macros-left, AI quick log + suggestions, coach meal plan, quick add,
// manual entry, editable history.
import { el, esc, api, toast, refresh, metric, rowActions, CHART } from '../app.js';

const MACROS = ['protein', 'calories', 'carbs', 'fat', 'fiber'];

async function logMeal(fields, note) {
  await api('POST', '/meals', { ...fields, date: undefined, time: undefined, notes: note });
}

export function renderMeals(root, state) {
  root.append(el('<h2 class="section-title">Meals</h2>'));
  root.append(el('<p class="section-sub">Tell Claude what you ate, ask it what to eat, or enter it by hand.</p>'));

  // ── what's left today ──
  const p = state.profile;
  const totals = state.stats.today.totals;
  const leftP = Math.max(0, (p.daily_protein_g || 0) - totals.protein);
  const leftC = Math.max(0, (p.daily_calories || 0) - totals.calories);
  const nut = state.stats.nutrition || {};
  const today = new Date().toISOString().slice(0, 10);
  const feedings = state.meals.filter(m => m.date === today && (m.protein ?? 0) >= 25).length;
  const grid = el('<div class="cards metrics"></div>');
  grid.append(
    metric('Protein left', leftP, { suffix: 'g', small: `of ${p.daily_protein_g}g` }),
    metric('Calories left', leftC, { small: `of ${p.daily_calories}` }),
    metric('Protein streak', nut.protein_streak ?? 0, { suffix: 'd', small: `${nut.hit_days_14 ?? 0}/14 days on target` }),
    metric('Feedings ≥25g', feedings, { small: 'spread protein across the day' }),
  );
  root.append(grid);

  // calorie-source split: protein / carbs / fat
  const pCal = totals.protein * 4, cCal = totals.carbs * 4, fCal = totals.fat * 9;
  const sumCal = pCal + cCal + fCal;
  if (sumCal > 0) {
    const seg = (val, color) => `<span style="flex:${val};background:${color};border-radius:3px;min-width:${val > 0 ? 6 : 0}px"></span>`;
    const pct = v => Math.round(v / sumCal * 100);
    root.append(el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Where today's calories came from</p>
      <div style="display:flex;gap:2px;height:14px;margin:10px 0 8px">${
        seg(pCal, 'var(--gold)')}${seg(cCal, 'var(--steel)')}${seg(fCal, 'var(--muted)')}</div>
      <div style="display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--ink-2)">
        <span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:var(--gold);margin-right:6px"></span>Protein ${pct(pCal)}% · ${Math.round(pCal)} cal</span>
        <span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:var(--steel);margin-right:6px"></span>Carbs ${pct(cCal)}% · ${Math.round(cCal)} cal</span>
        <span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:var(--muted);margin-right:6px"></span>Fat ${pct(fCal)}% · ${Math.round(fCal)} cal</span>
      </div>
    </div>`));
  }

  // ── 14-day trend: protein + calories vs goals ──
  const series = nut.series || [];
  if (series.some(s => s.protein > 0 || s.calories > 0)) {
    const trend = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Last 14 days vs your goals</p>
      <div class="grid-2" style="margin-top:8px">
        <div class="chart chart-p" style="min-height:170px"></div>
        <div class="chart chart-c" style="min-height:170px"></div>
      </div></div>`);
    root.append(trend);
    const dates = series.map(s => s.date);
    const goalLine = goal => goal ? [{ type: 'line', xref: 'paper', x0: 0, x1: 1,
      y0: goal, y1: goal, line: { color: 'rgba(242,193,78,.55)', width: 1, dash: 'dot' } }] : [];
    Plotly.newPlot(trend.querySelector('.chart-p'),
      [{ x: dates, y: series.map(s => s.protein), type: 'bar',
         marker: { color: series.map(s => nut.protein_goal && s.protein >= nut.protein_goal ? '#f2c14e' : '#6e7683'), cornerradius: 3 },
         hovertemplate: '%{x}<br>%{y}g protein<extra></extra>' }],
      CHART.layout({ height: 170, bargap: .35, margin: { l: 40, r: 8, t: 22, b: 28 },
        title: { text: `Protein (goal ${nut.protein_goal}g)`, font: { size: 11, color: '#8b93a1' }, x: 0 },
        shapes: goalLine(nut.protein_goal) }),
      CHART.config);
    Plotly.newPlot(trend.querySelector('.chart-c'),
      [{ x: dates, y: series.map(s => s.calories), type: 'bar',
         marker: { color: '#6ea8d8', cornerradius: 3 },
         hovertemplate: '%{x}<br>%{y} calories<extra></extra>' }],
      CHART.layout({ height: 170, bargap: .35, margin: { l: 44, r: 8, t: 22, b: 28 },
        title: { text: `Calories (target ${nut.calorie_goal})`, font: { size: 11, color: '#8b93a1' }, x: 0 },
        shapes: goalLine(nut.calorie_goal) }),
      CHART.config);
  }

  // ── adaptive TDEE — the app's real read on your metabolism ──
  const en = state.stats.energy;
  if (en?.has_data) {
    const dir = en.target_rate < 0 ? 'lose' : en.target_rate > 0 ? 'gain' : 'hold';
    const eCard = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Metabolism — adaptive TDEE <span style="font-size:11px;color:var(--muted);font-weight:400">confidence: ${en.confidence}</span></p>
      <p style="color:var(--muted);font-size:12px;margin:4px 0 0">Estimated from ${en.logged_days} fully-logged days and ${en.weigh_ins} weigh-ins over three weeks — your measured burn, not a formula guess.</p>
      <div class="cards metrics" style="margin-top:10px"></div>
      <div class="eb-advice"></div>
    </div>`);
    eCard.querySelector('.cards').append(
      metric('TDEE', en.tdee, { small: 'est. maintenance' }),
      metric('Avg intake', en.avg_intake, { small: `${en.logged_days} logged days` }),
      metric('Weight trend', `${en.rate_wk > 0 ? '+' : ''}${en.rate_wk}`, { suffix: ' lbs/wk', small: '21-day slope' }),
      metric('Suggested cals', en.recommended_calories,
        { small: en.target_rate ? `to ${dir} ${Math.abs(en.target_rate)} lb/wk` : 'to hold steady' }),
    );
    const adv = eCard.querySelector('.eb-advice');
    if (Math.abs(en.delta) >= 100) {
      const row = el(`<div class="callout ${en.delta > 0 ? 'good' : 'warn'}" style="margin-top:10px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <span style="flex:1;min-width:220px">Your goal is set to ${en.current_goal}, but the math says <strong>${en.recommended_calories}</strong>${en.delta > 0 ? ' — you can eat more and still hit pace.' : ' — tighten up to hit pace.'}</span>
        <button type="button" class="gold-btn" style="flex:0 1 auto;min-height:36px;padding:8px 16px;font-size:13px">Set ${en.recommended_calories} as my goal</button>
      </div>`);
      row.querySelector('button').addEventListener('click', async () => {
        try {
          await api('POST', '/profile/calorie-goal', { calories: en.recommended_calories });
          toast(`Calorie goal set to ${en.recommended_calories}`);
          await refresh();
        } catch (e) { toast(e.message); }
      });
      adv.append(row);
    } else {
      adv.append(el('<div class="callout good" style="margin-top:10px">Your calorie goal already matches the math. Keep logging — the estimate sharpens with every day.</div>'));
    }
    root.append(eCard);
  }

  // ── AI quick log ──
  const aiCard = el(`<div class="card">
    <p class="chart-title">AI quick log ${state.ai_backend ? `· ${esc(state.ai_backend)}` : ''}</p>
    <form class="form-row">
      <label style="flex:3 1 260px">What did you eat?
        <input name="description" type="text" placeholder="chicken burrito with rice and beans, and a protein shake" autocomplete="off"></label>
      <button class="gold-btn" type="submit">Estimate with AI</button>
      <button class="ghost-btn photo-btn" type="button" style="flex:0 1 auto">Snap the plate</button>
      <button class="ghost-btn scan-btn" type="button" style="flex:0 1 auto">Scan barcode</button>
      <input type="file" accept="image/*" capture="environment" hidden class="photo-input">
    </form>
    <div class="ai-result"></div>
  </div>`);
  const aiForm = aiCard.querySelector('form');
  const aiResult = aiCard.querySelector('.ai-result');
  aiForm.addEventListener('submit', async e => {
    e.preventDefault();
    const description = aiForm.description.value.trim();
    if (!description) { toast('Describe what you ate first.'); return; }
    const btn = aiForm.querySelector('button');
    btn.disabled = true;
    aiResult.innerHTML = '<p style="margin:12px 0 0"><span class="spinner"></span>Claude is estimating the macros…</p>';
    try {
      const { meals } = await api('POST', '/meals/ai/parse', { description });
      showParsed(meals);
    } catch (err) {
      aiResult.innerHTML = '';
      toast(err.message);
    } finally { btn.disabled = false; }
  });

  const photoBtn = aiCard.querySelector('.photo-btn');
  const photoInput = aiCard.querySelector('.photo-input');
  photoBtn.addEventListener('click', () => photoInput.click());
  photoInput.addEventListener('change', () => {
    const file = photoInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      photoBtn.disabled = true;
      aiResult.innerHTML = '<p style="margin:12px 0 0"><span class="spinner"></span>Claude is looking at your plate — about a minute…</p>';
      try {
        const { meals } = await api('POST', '/meals/photo', { image: reader.result });
        showParsed(meals);
      } catch (err) {
        aiResult.innerHTML = '';
        toast(err.message);
      } finally {
        photoBtn.disabled = false;
        photoInput.value = '';
      }
    };
    reader.readAsDataURL(file);
  });

  // ── barcode scan → Open Food Facts lookup ──
  let scanStream = null;
  const stopScan = () => {
    scanStream?.getTracks().forEach(t => t.stop());
    scanStream = null;
  };

  async function lookupBarcode(code) {
    aiResult.innerHTML = '<p style="margin:12px 0 0"><span class="spinner"></span>Looking it up on Open Food Facts…</p>';
    try {
      const hit = await api('GET', `/food/barcode/${encodeURIComponent(code)}`);
      showProduct(hit, code);
    } catch (err) {
      aiResult.innerHTML = '';
      toast(err.message);
    }
  }

  function showProduct(hit, code) {
    const basisLabel = hit.basis === 'serving'
      ? `per serving${hit.serving_size ? ` (${hit.serving_size})` : ''}`
      : 'per 100 g';
    const m = hit.macros;
    aiResult.innerHTML = '';
    const wrap = el(`<div style="margin-top:12px">
      <div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap">
        <strong style="font-size:14px">${esc(hit.name)}</strong>
        ${hit.brand ? `<span style="font-size:12px;color:var(--muted)">${esc(hit.brand)}</span>` : ''}
        <span style="font-family:var(--font-mono);font-size:11px;color:var(--steel)">${esc(basisLabel)}</span>
      </div>
      <p style="font-family:var(--font-mono);font-size:13px;color:var(--ink-2);margin:8px 0">
        ${m.protein}g P · ${m.calories} cal · ${m.carbs}g C · ${m.fat}g F · ${m.fiber}g fiber</p>
      <div class="form-row" style="align-items:flex-end">
        <label style="flex:0 1 170px">${hit.basis === 'serving' ? 'Servings' : 'Amount (×100 g)'}
          <input class="bc-mult" type="number" min="0.25" step="0.25" value="1"></label>
        <button class="gold-btn bc-add" type="button" style="flex:0 1 auto">Add to log</button>
        <button class="ghost-btn bc-discard" type="button" style="flex:0 1 auto">Discard</button>
      </div></div>`);
    wrap.querySelector('.bc-add').addEventListener('click', async () => {
      const mult = Number(wrap.querySelector('.bc-mult').value) || 1;
      const scale = f => Math.round((m[f] || 0) * mult * 10) / 10;
      try {
        await logMeal({ name: [hit.brand, hit.name].filter(Boolean).join(' ').slice(0, 120),
                        protein: scale('protein'), calories: Math.round((m.calories || 0) * mult),
                        carbs: scale('carbs'), fat: scale('fat'), fiber: scale('fiber') },
                      `Barcode ${code}`);
        toast(`Logged: ${hit.name}`);
        await refresh();
      } catch (e) { toast(e.message); }
    });
    wrap.querySelector('.bc-discard').addEventListener('click', () => { aiResult.innerHTML = ''; });
    aiResult.append(wrap);
  }

  aiCard.querySelector('.scan-btn').addEventListener('click', async () => {
    stopScan();
    aiResult.innerHTML = '';
    const pane = el(`<div style="margin-top:12px">
      <div class="bc-cam-slot"></div>
      <form class="form-row" style="align-items:flex-end">
        <label style="flex:0 1 240px">Barcode digits
          <input class="bc-code" type="text" inputmode="numeric" placeholder="e.g. 3017624010701" autocomplete="off"></label>
        <button class="ghost-btn" type="submit" style="flex:0 1 auto">Look up</button>
        <button class="ghost-btn bc-cancel" type="button" style="flex:0 1 auto">Cancel</button>
      </form></div>`);
    pane.querySelector('form').addEventListener('submit', ev => {
      ev.preventDefault();
      const code = pane.querySelector('.bc-code').value.trim();
      if (!code) { toast('Type the digits under the barcode.'); return; }
      stopScan();
      lookupBarcode(code);
    });
    pane.querySelector('.bc-cancel').addEventListener('click', () => { stopScan(); aiResult.innerHTML = ''; });
    aiResult.append(pane);

    // Live camera scanning where the browser supports it (Chrome/Android);
    // everywhere else the digits field above still works.
    if (!('BarcodeDetector' in window) || !navigator.mediaDevices?.getUserMedia) return;
    try {
      scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    } catch { return; /* camera denied — manual entry remains */ }
    const video = el('<video muted playsinline style="width:100%;max-width:420px;border-radius:6px;margin-bottom:10px"></video>');
    pane.querySelector('.bc-cam-slot').append(video);
    video.srcObject = scanStream;
    await video.play().catch(() => {});
    const detector = new BarcodeDetector({
      formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'] });
    const poll = setInterval(async () => {
      if (!scanStream || !video.isConnected) { clearInterval(poll); stopScan(); return; }
      try {
        const codes = await detector.detect(video);
        if (codes.length) {
          clearInterval(poll);
          stopScan();
          if (navigator.vibrate) navigator.vibrate(120);
          lookupBarcode(codes[0].rawValue);
        }
      } catch { /* detector hiccup — keep polling */ }
    }, 350);
  });

  function showParsed(meals) {
    const totalP = meals.reduce((s, m) => s + m.protein, 0);
    const totalC = meals.reduce((s, m) => s + m.calories, 0);
    aiResult.innerHTML = '';
    const wrap = el(`<div style="margin-top:12px">
      <div class="table-wrap"><table>
        <thead><tr><th>Item</th><th class="num">Protein</th><th class="num">Cal</th><th class="num">Carbs</th><th class="num">Fat</th><th class="num">Fiber</th></tr></thead>
        <tbody>${meals.map(m => `<tr><td>${esc(m.name)}</td><td class="num">${m.protein}g</td><td class="num">${m.calories}</td>
          <td class="num">${m.carbs}g</td><td class="num">${m.fat}g</td><td class="num">${m.fiber}g</td></tr>`).join('')}</tbody>
      </table></div>
      <p style="color:var(--ink-2);font-size:13px;margin:10px 0">Total: <strong style="color:var(--gold-bright)">${totalP}g protein, ${totalC} calories</strong></p>
      <div class="form-row">
        <button class="gold-btn add-all" type="button">Add all to log</button>
        <button class="ghost-btn discard" type="button">Discard estimate</button>
      </div></div>`);
    wrap.querySelector('.add-all').addEventListener('click', async () => {
      try {
        await api('POST', '/meals/ai/add', { meals });
        toast(`Added ${meals.length} meal${meals.length > 1 ? 's' : ''}`);
        await refresh();
      } catch (e) { toast(e.message); }
    });
    wrap.querySelector('.discard').addEventListener('click', () => { aiResult.innerHTML = ''; });
    aiResult.append(wrap);
  }

  root.append(aiCard);

  // ── "what should I eat next?" ──
  const coach = (state.coaches || []).find(c => c.id === state.coach);
  const sugCard = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">What should I eat next?</p>
    <p style="color:var(--ink-2);font-size:13px;margin:8px 0">${esc(coach?.name || 'Your coach')} looks at your
      ${leftP}g protein / ${leftC} cal remaining, what you've eaten today, and their nutrition philosophy —
      then suggests three real options you can log in one tap.</p>
    <button class="gold-btn" type="button">Suggest my next meal</button>
    <div class="sug-result"></div>
  </div>`);
  const sugBtn = sugCard.querySelector('button');
  const sugOut = sugCard.querySelector('.sug-result');
  sugBtn.addEventListener('click', async () => {
    sugBtn.disabled = true;
    sugOut.innerHTML = `<p style="margin-top:12px"><span class="spinner"></span>${esc(coach?.name || 'Coach')} is checking the fridge — about a minute…</p>`;
    try {
      const { suggestions } = await api('POST', '/meals/suggest');
      sugOut.innerHTML = '';
      for (const s of suggestions) {
        const row = el(`<div class="deal" style="margin-top:8px">
          <div class="deal-top"><span class="deal-item">${esc(s.name)}</span>
            <span style="font-family:var(--font-mono);font-size:12px;color:var(--gold-bright);white-space:nowrap">${s.protein}g P · ${s.calories} cal</span></div>
          <div class="deal-meta">${esc(s.items)}</div>
          <div class="deal-meta" style="color:var(--steel)">${esc(s.why)}</div>
          <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
            <span style="font-family:var(--font-mono);font-size:11px;color:var(--muted)">${s.carbs}g C · ${s.fat}g F · ${s.fiber}g fiber</span>
            <button class="ghost-btn" type="button" style="min-height:34px;padding:6px 14px;font-size:12px">Log it</button>
          </div></div>`);
        row.querySelector('button').addEventListener('click', async () => {
          try {
            await logMeal(s, 'Suggested by Claude');
            toast(`Logged: ${s.name}`);
            await refresh();
          } catch (e) { toast(e.message); }
        });
        sugOut.append(row);
      }
    } catch (e) {
      sugOut.innerHTML = '';
      toast(e.message);
    } finally { sugBtn.disabled = false; }
  });
  root.append(sugCard);

  // ── coach's sample meal day from the weekly plan ──
  const planMeals = state.plan?.plan?.meals || [];
  if (planMeals.length) {
    const planCoach = (state.coaches || []).find(c => c.id === state.plan.coach);
    const pm = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">${esc(planCoach?.name || 'Coach')}'s sample meal day</p>
      <div class="table-wrap" style="margin-top:8px"><table>
        <thead><tr><th>Meal</th><th>What</th><th class="num">Protein</th><th class="num">Cal</th><th></th></tr></thead>
        <tbody></tbody></table></div></div>`);
    const tbody = pm.querySelector('tbody');
    for (const m of planMeals) {
      const tr = el(`<tr><td>${esc(m.meal)}</td><td>${esc(m.items)}</td>
        <td class="num">${m.protein}g</td><td class="num">${m.calories}</td>
        <td class="row-actions"><button class="icon-btn" title="Log this meal">＋</button></td></tr>`);
      tr.querySelector('button').addEventListener('click', async () => {
        try {
          await logMeal({ name: `${m.meal}: ${m.items}`.slice(0, 120),
                          protein: m.protein, calories: m.calories },
                        'From the coach plan');
          toast(`Logged: ${m.meal}`);
          await refresh();
        } catch (e) { toast(e.message); }
      });
      tbody.append(tr);
    }
    root.append(pm);
  }

  // ── quick add ──
  const quick = state.stats.quick_meals;
  if (quick.length) {
    const qCard = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Quick add — your regulars</p>
      <form class="form-row">
        <label style="flex:3 1 240px">Recent meals<select name="idx">
          ${quick.map((m, i) => `<option value="${i}">${esc(m.name)} — ${m.protein ?? 0}g P / ${m.calories ?? 0} cal</option>`).join('')}
        </select></label>
        <button class="gold-btn" type="submit">＋ Log it again</button>
      </form></div>`);
    qCard.querySelector('form').addEventListener('submit', async e => {
      e.preventDefault();
      const src = quick[Number(qCard.querySelector('select').value)];
      try {
        await api('POST', '/meals', { ...src, date: undefined, time: undefined });
        toast(`Added: ${src.name}`);
        await refresh();
      } catch (err) { toast(err.message); }
    });
    root.append(qCard);
  }

  // ── manual entry ──
  const now = new Date();
  const manual = el(`<form class="panel" style="margin-top:14px">
    <p class="chart-title">Manual entry</p>
    <div class="grid-3">
      <label>Date <input name="date" type="date" value="${now.toISOString().slice(0, 10)}"></label>
      <label>Time <input name="time" type="time" value="${now.toTimeString().slice(0, 5)}"></label>
      <label>Meal name <input name="name" type="text" placeholder="Chicken & rice" required></label>
      <label>Protein (g) <input name="protein" type="number" min="0" value="30"></label>
      <label>Calories <input name="calories" type="number" min="0" value="400"></label>
      <label>Carbs (g) <input name="carbs" type="number" min="0" value="0"></label>
      <label>Fat (g) <input name="fat" type="number" min="0" value="0"></label>
      <label>Fiber (g) <input name="fiber" type="number" min="0" value="0"></label>
      <label>Notes <input name="notes" type="text" placeholder="Optional"></label>
    </div>
    <div style="margin-top:12px"><button class="gold-btn" type="submit">Add meal</button></div>
  </form>`);
  manual.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('POST', '/meals', Object.fromEntries(new FormData(manual).entries()));
      toast('Meal added');
      await refresh();
    } catch (err) { toast(err.message); }
  });
  root.append(manual);

  // ── last 7 days, grouped by day, editable ──
  const yday = new Date(Date.now() - 864e5).toISOString().slice(0, 10);
  const hasYday = state.meals.some(m => m.date === yday);
  const histHead = el(`<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:18px 0 8px">
    <p class="chart-title" style="margin:0">Last 7 days</p>
    ${hasYday ? '<button class="ghost-btn" type="button" style="min-height:32px;padding:5px 12px;font-size:12px">Repeat yesterday</button>' : ''}
  </div>`);
  if (hasYday) {
    histHead.querySelector('button').addEventListener('click', async () => {
      try {
        const { count } = await api('POST', '/meals/repeat-yesterday');
        toast(`Logged yesterday's ${count} meal${count > 1 ? 's' : ''} again`);
        await refresh();
      } catch (e) { toast(e.message); }
    });
  }
  root.append(histHead);
  const weekAgo = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
  const rows = state.meals.map((m, idx) => ({ m, idx }))
    .filter(({ m }) => m.date >= weekAgo)
    .sort((a, b) => (b.m.date + (b.m.time || '')).localeCompare(a.m.date + (a.m.time || '')));
  if (!rows.length) {
    root.append(el('<div class="empty">No meals in the last 7 days.</div>'));
    return;
  }
  const wrap = el(`<div class="table-wrap"><table>
    <thead><tr><th>Time</th><th>Meal</th>
      <th class="num">P</th><th class="num">Cal</th><th class="num">C</th><th class="num">F</th><th class="num">Fib</th><th></th></tr></thead>
    <tbody></tbody></table></div>`);
  const tbody = wrap.querySelector('tbody');
  const dayLabel = iso => iso === today ? 'Today' : iso === yday ? 'Yesterday'
    : new Date(iso + 'T12:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  let curDay = null;
  for (const { m, idx } of rows) {
    if (m.date !== curDay) {
      curDay = m.date;
      const dayMeals = rows.filter(r => r.m.date === curDay).map(r => r.m);
      const sum = f => Math.round(dayMeals.reduce((s, x) => s + (x[f] ?? 0), 0));
      tbody.append(el(`<tr style="background:var(--bg)">
        <td colspan="2" style="font-weight:800;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--steel)">${dayLabel(curDay)}</td>
        <td class="num" style="color:var(--gold-bright);font-family:var(--font-mono);font-size:12px">${sum('protein')}g</td>
        <td class="num" style="font-family:var(--font-mono);font-size:12px">${sum('calories')}</td>
        <td class="num" style="color:var(--muted);font-family:var(--font-mono);font-size:12px">${sum('carbs')}</td>
        <td class="num" style="color:var(--muted);font-family:var(--font-mono);font-size:12px">${sum('fat')}</td>
        <td class="num" style="color:var(--muted);font-family:var(--font-mono);font-size:12px">${sum('fiber')}</td>
        <td></td></tr>`));
    }
    const tr = el(`<tr><td>${esc(m.time)}</td><td title="${esc(m.notes || '')}">${esc(m.name)}</td>
      <td class="num">${m.protein ?? 0}</td><td class="num">${m.calories ?? 0}</td>
      <td class="num">${m.carbs ?? 0}</td><td class="num">${m.fat ?? 0}</td><td class="num">${m.fiber ?? 0}</td></tr>`);
    tr.append(rowActions('meals', idx, { onEdit: () => editRow(tr, m, idx) }));
    tbody.append(tr);
  }
  root.append(wrap);

  function editRow(tr, m, idx) {
    tr.classList.add('editing');
    tr.innerHTML = `<td style="min-width:170px"><input type="date" value="${esc(m.date)}" style="width:120px"><input type="time" value="${esc(m.time)}" style="width:90px;margin-top:4px"></td>
      <td><input type="text" value="${esc(m.name)}"></td>
      ${MACROS.map(f => `<td><input type="number" min="0" value="${m[f] ?? 0}"></td>`).join('')}
      <td class="row-actions"><button class="icon-btn" title="Save">✓</button><button class="icon-btn danger" title="Cancel">↩</button></td>`;
    const inputs = tr.querySelectorAll('input');
    tr.querySelector('.icon-btn').addEventListener('click', async () => {
      const body = { date: inputs[0].value, time: inputs[1].value, name: inputs[2].value };
      MACROS.forEach((f, i) => { body[f] = inputs[3 + i].value; });
      try {
        await api('PUT', `/entry/meals/${idx}`, body);
        toast('Saved');
        await refresh();
      } catch (e) { toast(e.message); }
    });
    tr.querySelector('.danger').addEventListener('click', () => refresh());
  }
}
