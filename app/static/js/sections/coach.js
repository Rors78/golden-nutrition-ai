// Coach: rule-based weekly insights + Claude coaching summary + protein chart.
import { el, esc, api, toast, metric, markdown, CHART } from '../app.js';

export function renderCoach(root, state) {
  const ins = state.stats.insights;

  root.append(el('<h2 class="section-title">Coach</h2>'));
  root.append(el('<p class="section-sub">Your last 7 days, reviewed — by the numbers and by Claude.</p>'));

  // ── Claude coaching summary ──
  const aiCard = el(`<div class="card">
    <p class="chart-title">Claude coaching summary ${state.ai_backend ? `· ${esc(state.ai_backend)}` : ''}</p>
    <p style="color:var(--ink-2);font-size:13px;margin:8px 0">What went well, what to fix, and the one change for next week — from your actual data.</p>
    <button class="gold-btn" type="button">Review my week</button>
    <div class="coach-result"></div>
  </div>`);
  const btn = aiCard.querySelector('button');
  const out = aiCard.querySelector('.coach-result');
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    out.innerHTML = '<p style="margin-top:12px"><span class="spinner"></span>Claude is reviewing your week — 30–60 seconds…</p>';
    try {
      const { summary } = await api('POST', '/coach');
      out.innerHTML = `<div class="prose" style="margin-top:12px">${markdown(summary)}</div>`;
    } catch (e) {
      out.innerHTML = '';
      toast(e.message);
    } finally { btn.disabled = false; }
  });
  root.append(aiCard);

  if (!ins.has_data) {
    root.append(el('<div class="empty" style="margin-top:14px">Log meals for a few days and the weekly numbers show up here.</div>'));
    return;
  }

  // ── weekly averages ──
  const grid = el('<div class="cards metrics" style="margin-top:14px"></div>');
  grid.append(
    metric('Avg protein/day', ins.avg_daily_protein, { suffix: 'g', small: `goal ${ins.protein_goal}g` }),
    metric('Avg protein/meal', ins.avg_protein_meal, { suffix: 'g' }),
    metric('Avg cal/meal', ins.avg_calories_meal, {}),
    metric('Meals/day', ins.meals_per_day, { small: `${ins.days_logged}d logged` }),
    metric('Carbs/day', ins.avg_carbs_day, { suffix: 'g' }),
    metric('Fat/day', ins.avg_fat_day, { suffix: 'g' }),
    metric('Fiber/day', ins.avg_fiber_day, { suffix: 'g' }),
  );
  root.append(grid);

  // ── verdicts ──
  const v = ins.verdict;
  root.append(el(`<div class="callout ${v.level === 'warn' ? 'warn' : v.level === 'good' ? 'good' : ''}"
    style="margin-top:14px">${esc(v.text)}</div>`));

  const wc = ins.workout_count;
  const wText = wc < 3 ? `${wc} workout${wc === 1 ? '' : 's'} this week — aim for at least 3–4.`
    : wc >= 5 ? `${wc} workouts this week — excellent consistency.`
    : `${wc} workouts this week — solid frequency.`;
  root.append(el(`<div class="callout ${wc < 3 ? 'warn' : wc >= 5 ? 'good' : ''}" style="margin-top:8px">${esc(wText)}</div>`));

  if (ins.missed_supps.length) {
    root.append(el(`<div class="callout warn" style="margin-top:8px">Missed supplements: ${ins.missed_supps.map(s =>
      `${esc(s.name)} (${esc(s.date)})`).join(', ')}</div>`));
  }

  // ── daily protein chart ──
  const chartCard = el('<div class="card" style="margin-top:14px"><p class="chart-title">Daily protein · last 7 days</p><div class="chart"></div></div>');
  root.append(chartCard);
  const days = Object.keys(ins.protein_by_day);
  const vals = Object.values(ins.protein_by_day);
  const layout = CHART.layout({
    bargap: .45,
    shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: ins.protein_goal, y1: ins.protein_goal,
      line: { color: CHART.good, width: 1, dash: 'dot' } }],
    annotations: [{ xref: 'paper', x: 1, y: ins.protein_goal, text: `goal ${ins.protein_goal}g`,
      showarrow: false, font: { size: 10, color: CHART.good }, yshift: 10, xanchor: 'right' }],
  });
  Plotly.newPlot(chartCard.querySelector('.chart'),
    [{ x: days, y: vals, type: 'bar', marker: { color: CHART.gold, cornerradius: 4 },
       hovertemplate: '%{x}<br>%{y}g protein<extra></extra>' }],
    layout, CHART.config);
}
