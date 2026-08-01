// Coach: pick from the 10-coach roster, generate a weekly plan in their style,
// get a persona-voiced review of your week, plus the rule-based numbers.
import { el, esc, api, toast, refresh, metric, markdown, CHART } from '../app.js';

export function renderCoach(root, state) {
  const ins = state.stats.insights;
  const coaches = state.coaches || [];
  const selected = coaches.find(c => c.id === state.coach) || coaches[0];

  root.append(el('<h2 class="section-title">Coach</h2>'));
  root.append(el('<p class="section-sub">Pick your coach — every plan and review comes in their style. Personas are inspired by each figure\'s public training philosophy.</p>'));

  // ── roster ──
  const grid = el('<div class="coach-grid"></div>');
  for (const c of coaches) {
    const card = el(`<button type="button" class="coach-card${c.id === selected?.id ? ' selected' : ''}">
      <span class="coach-emoji">${c.emoji}</span>
      <span class="coach-name">${esc(c.name)}</span>
      <span class="coach-style">${esc(c.style)}</span>
      <span class="coach-goal">${esc(c.goal)}</span>
      <span class="coach-vibe">${esc(c.vibe)}</span>
    </button>`);
    card.addEventListener('click', async () => {
      if (c.id === state.coach) return;
      try {
        await api('POST', '/coach/select', { id: c.id });
        toast(`${c.name} is your coach now`);
        await refresh();
      } catch (e) { toast(e.message); }
    });
    grid.append(card);
  }
  root.append(grid);

  // ── weekly plan ──
  const planCard = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">Your week, ${esc(selected?.style || 'planned')}</p>
    <p style="color:var(--ink-2);font-size:13px;margin:8px 0">A 7-day plan in ${esc(selected?.name || 'your coach')}'s style —
      workouts, a sample meal day matched to your macro goals, and their supplement take.</p>
    <button class="gold-btn" type="button">Build my week</button>
    <div class="plan-result"></div>
  </div>`);
  const planBtn = planCard.querySelector('button');
  const planOut = planCard.querySelector('.plan-result');
  planBtn.addEventListener('click', async () => {
    planBtn.disabled = true;
    planOut.innerHTML = `<p style="margin-top:12px"><span class="spinner"></span>${esc(selected?.name || 'Coach')} is writing your week — 1–2 minutes…</p>`;
    try {
      const cached = await api('POST', '/plan');
      renderPlan(cached);
    } catch (e) {
      planOut.innerHTML = '';
      toast(e.message);
    } finally { planBtn.disabled = false; }
  });
  root.append(planCard);

  function renderPlan(cached) {
    const plan = cached.plan;
    const coach = coaches.find(c => c.id === cached.coach);
    planOut.innerHTML = '';
    planOut.append(el(`<p class="section-sub" style="margin:12px 0 8px">By ${esc(coach?.name || 'your coach')} · ${esc(cached.generated_at)}</p>`));

    const week = el('<div class="plan-week"></div>');
    for (const d of plan.week) {
      week.append(el(`<div class="plan-day${/rest|recovery/i.test(d.title + d.focus) ? ' rest' : ''}">
        <div class="plan-day-head"><span class="plan-dow">${esc(d.day)}</span><span class="plan-title">${esc(d.title)}</span></div>
        <div class="plan-focus">${esc(d.focus)}</div>
        <ul>${d.details.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      </div>`));
    }
    planOut.append(week);

    if (plan.meals?.length) {
      const totalP = plan.meals.reduce((s, m) => s + (m.protein || 0), 0);
      const totalC = plan.meals.reduce((s, m) => s + (m.calories || 0), 0);
      const mealsWrap = el(`<div style="margin-top:14px">
        <p class="chart-title">Sample meal day · ${totalP}g protein / ${totalC} cal</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Meal</th><th>What</th><th class="num">Protein</th><th class="num">Cal</th></tr></thead>
          <tbody>${plan.meals.map(m => `<tr><td>${esc(m.meal)}</td><td>${esc(m.items)}</td>
            <td class="num">${m.protein}g</td><td class="num">${m.calories}</td></tr>`).join('')}</tbody>
        </table></div></div>`);
      planOut.append(mealsWrap);
    }

    if (plan.supplements?.length) {
      planOut.append(el(`<div style="margin-top:14px"><p class="chart-title">Supplements</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">${plan.supplements.map(s =>
          `<span class="badge" style="color:var(--ink-2)">${esc(s)}</span>`).join('')}</div></div>`));
    }

    if (plan.coach_note) {
      planOut.append(el(`<div class="callout good" style="margin-top:14px">${esc(plan.coach_note)}</div>`));
    }
  }

  if (state.plan?.plan) renderPlan(state.plan);

  // ── Claude coaching summary ──
  const aiCard = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">Weekly review by ${esc(selected?.name || 'your coach')} ${state.ai_backend ? `· ${esc(state.ai_backend)}` : ''}</p>
    <p style="color:var(--ink-2);font-size:13px;margin:8px 0">What went well, what to fix, and the one change for next week — in ${esc(selected?.style || 'coach')} voice, from your actual data.</p>
    <button class="gold-btn" type="button">Review my week</button>
    <div class="coach-result"></div>
  </div>`);
  const btn = aiCard.querySelector('button');
  const out = aiCard.querySelector('.coach-result');
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    out.innerHTML = `<p style="margin-top:12px"><span class="spinner"></span>${esc(selected?.name || 'Coach')} is reviewing your week — 30–60 seconds…</p>`;
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
  const grid2 = el('<div class="cards metrics" style="margin-top:14px"></div>');
  grid2.append(
    metric('Avg protein/day', ins.avg_daily_protein, { suffix: 'g', small: `goal ${ins.protein_goal}g` }),
    metric('Avg protein/meal', ins.avg_protein_meal, { suffix: 'g' }),
    metric('Avg cal/meal', ins.avg_calories_meal, {}),
    metric('Meals/day', ins.meals_per_day, { small: `${ins.days_logged}d logged` }),
    metric('Carbs/day', ins.avg_carbs_day, { suffix: 'g' }),
    metric('Fat/day', ins.avg_fat_day, { suffix: 'g' }),
    metric('Fiber/day', ins.avg_fiber_day, { suffix: 'g' }),
  );
  root.append(grid2);

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
