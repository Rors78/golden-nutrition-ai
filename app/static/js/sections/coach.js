// Coach: pick from the 10-coach roster, generate a weekly plan in their style,
// get a persona-voiced review of your week, plus the rule-based numbers.
import { el, esc, api, toast, refresh, metric, markdown, CHART } from '../app.js';

export function renderCoach(root, state) {
  const ins = state.stats.insights;
  const coaches = state.coaches || [];
  const selected = coaches.find(c => c.id === state.coach) || coaches[0];

  root.append(el('<h2 class="section-title">Coach</h2>'));
  root.append(el('<p class="section-sub">Pick your coach — every plan and review comes in their style. Personas are inspired by each figure\'s public training philosophy.</p>'));

  // ── fit line + roster filters ──
  const fit = state.stats.coach_fit || { ids: [] };
  const fitIds = new Set(fit.ids || []);
  if (fit.ids?.length) {
    const names = fit.ids.map(id => coaches.find(c => c.id === id)?.name).filter(Boolean);
    root.append(el(`<div class="callout" style="margin-bottom:12px">You're <strong>${esc(fit.label)}</strong> right now —
      a natural fit: ${names.map(esc).join(', ')}. But the best coach is the one whose voice you'll actually listen to.</div>`));
  }
  const CATS = {
    'Muscle': ['cutler', 'arnold', 'nippard', 'hall', 'heria', 'serena'],
    'Fat loss': ['wicks', 'simmons', 'casseyho', 'austin', 'goggins', 'phelps'],
    'Conditioning': ['fraser', 'tyson', 'bolt', 'phelps', 'goggins'],
    'Mobility & recovery': ['adriene', 'jetli', 'biles', 'casseyho'],
    'Strength & longevity': ['hall', 'pavel', 'lalanne'],
  };
  const filterBar = el(`<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px">
    <input type="search" placeholder="Search 20 coaches…" style="flex:1 1 180px;max-width:260px;min-height:36px;padding:6px 12px;font-size:13px">
    ${['All', ...Object.keys(CATS)].map((k, i) =>
      `<button type="button" class="ghost-btn cat-chip${i === 0 ? ' active' : ''}" data-cat="${esc(k)}"
        style="min-height:32px;padding:5px 12px;font-size:12px">${esc(k)}</button>`).join('')}
  </div>`);
  root.append(filterBar);

  const grid = el('<div class="coach-grid"></div>');
  const cardById = {};
  for (const c of coaches) {
    const initials = c.name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
    const card = el(`<button type="button" class="coach-card${c.id === selected?.id ? ' selected' : ''}">
      <span class="plate-disc" style="width:44px;height:44px;font-size:14px">${esc(initials)}</span>
      <span class="coach-name">${esc(c.name)}
        ${fitIds.has(c.id) ? '<span style="font-size:9px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--good);border:1px solid var(--good);border-radius:999px;padding:2px 7px;margin-left:6px;vertical-align:middle">good fit</span>' : ''}</span>
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
    cardById[c.id] = card;
    grid.append(card);
  }
  root.append(grid);

  let activeCat = 'All';
  const searchBox = filterBar.querySelector('input');
  const applyFilter = () => {
    const q = searchBox.value.trim().toLowerCase();
    for (const c of coaches) {
      const inCat = activeCat === 'All' || (CATS[activeCat] || []).includes(c.id);
      const inSearch = !q || `${c.name} ${c.goal} ${c.style} ${c.vibe}`.toLowerCase().includes(q);
      cardById[c.id].style.display = inCat && inSearch ? '' : 'none';
    }
  };
  searchBox.addEventListener('input', applyFilter);
  const paintChips = () => filterBar.querySelectorAll('.cat-chip').forEach(x => {
    const on = x.dataset.cat === activeCat;
    x.style.borderColor = on ? 'var(--gold)' : '';
    x.style.color = on ? 'var(--gold-bright)' : '';
  });
  paintChips();
  filterBar.querySelectorAll('.cat-chip').forEach(chip => chip.addEventListener('click', () => {
    activeCat = chip.dataset.cat;
    paintChips();
    applyFilter();
  }));

  // ── the dossier: the research behind the selected coach ──
  if (selected) {
    root.append(el(`<details class="card" style="margin-top:14px">
      <summary style="cursor:pointer;list-style:none">
        <span class="chart-title">${esc(selected.name)}'s dossier — how this persona coaches</span>
        <span style="color:var(--muted);font-size:12px;margin-left:8px">click to open</span></summary>
      <div style="display:grid;gap:12px;margin-top:12px;font-size:13px;color:var(--ink-2);line-height:1.65">
        <div><strong style="color:var(--gold-bright)">Training</strong><br>${esc(selected.workout || '')}</div>
        <div><strong style="color:var(--gold-bright)">Nutrition</strong><br>${esc(selected.nutrition || '')}</div>
        <div><strong style="color:var(--gold-bright)">Supplements</strong><br>${esc(selected.supplements || '')}</div>
        <div><strong style="color:var(--steel)">Voice</strong><br>${esc(selected.voice || '')}</div>
        <div style="border-left:3px solid var(--warn);padding-left:12px;color:var(--muted)">
          <strong style="color:var(--warn)">The fine print</strong><br>${esc(selected.caveats || '')}</div>
      </div>
    </details>`));
  }

  // ── live chat with your coach ──
  const chatCard = el(`<div class="card" style="margin-top:14px">
    <div class="form-row" style="align-items:center">
      <p class="chart-title" style="margin:0;flex:1">Talk to ${esc(selected?.name || 'your coach')} ${state.ai_backend ? `· ${esc(state.ai_backend)}` : ''}</p>
      ${(state.coach_chat || []).length ? '<button class="ghost-btn chat-clear" type="button" style="flex:0 1 auto;min-height:34px;padding:6px 12px;font-size:12px">Clear thread</button>' : ''}
    </div>
    <div class="chat-log"></div>
    <div class="quick-asks" style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 4px">
      ${['Should I train today?', 'What do I eat before the gym?', 'How is my week looking?', 'I need a push — talk to me']
        .map(q => `<button type="button" class="ghost-btn qa-chip" style="min-height:30px;padding:4px 12px;font-size:12px">${q}</button>`).join('')}
    </div>
    <form class="form-row">
      <label style="flex:1 1 260px"><input name="message" type="text" autocomplete="off"
        placeholder="should I still train today? · what do I eat before the gym? · my knee felt off on squats"></label>
      <button class="gold-btn" type="submit" style="flex:0 1 auto">Send</button>
    </form>
  </div>`);
  const log = chatCard.querySelector('.chat-log');
  const coachById = id => (state.coaches || []).find(c => c.id === id);

  // A coach-proposed write, shown for confirmation. The model never touches
  // the data file directly — this card is the only path from proposal to save,
  // and it always states exactly what will be written.
  const ACTION_LABEL = {
    log_meal: 'Log this meal', log_weight: 'Log this weigh-in',
    log_workout: 'Log this session', log_measurement: 'Log these measurements',
    set_calorie_goal: 'Change your calorie goal',
  };

  function actionSummary(a) {
    const i = a.input || {};
    switch (a.tool) {
      case 'log_meal':
        return `${i.name} — ${i.protein}g protein · ${i.calories} cal`;
      case 'log_weight':
        return `${i.weight} lbs today`;
      case 'log_workout':
        return `${i.name} — ${(i.exercises || []).map(e =>
          `${e.exercise} ${e.sets}×${e.reps} @ ${e.weight}`).join(' · ')}`;
      case 'log_measurement':
        return Object.entries(i).map(([k, v]) => `${k.replace('_in', '')} ${v}"`).join(' · ');
      case 'set_calorie_goal':
        return `${i.calories} cal/day — ${i.why}`;
      default:
        return JSON.stringify(i);
    }
  }

  function actionCard(a) {
    const card = el(`<div class="coach-action">
      <div class="ca-head">${esc(ACTION_LABEL[a.tool] || a.tool)}</div>
      <div class="ca-body">${esc(actionSummary(a))}</div>
      <div class="ca-btns">
        <button type="button" class="gold-btn ca-yes">Save it</button>
        <button type="button" class="ghost-btn ca-no">Dismiss</button>
      </div>
    </div>`);
    card.querySelector('.ca-no').addEventListener('click', () => card.remove());
    card.querySelector('.ca-yes').addEventListener('click', async ev => {
      ev.target.disabled = true;
      try {
        await api('POST', '/coach/act', { tool: a.tool, input: a.input });
        card.classList.add('done');
        card.querySelector('.ca-btns').innerHTML = '<span class="ca-ok">✓ Saved</span>';
        await refresh();
      } catch (e) { ev.target.disabled = false; toast(e.message); }
    });
    return card;
  }

  function bubble(m) {
    if (m.role === 'user') {
      return el(`<div class="chat-msg user">${esc(m.text)}<span class="chat-ts">${esc(m.ts || '')}</span></div>`);
    }
    const who = coachById(m.coach)?.name || 'Coach';
    return el(`<div class="chat-msg coach"><div class="prose" style="font-size:14px">${markdown(m.text)}</div>
      <span class="chat-ts">${esc(who)} · ${esc(m.ts || '')}</span></div>`);
  }
  const existing = state.coach_chat || [];
  if (existing.length) {
    existing.forEach(m => log.append(bubble(m)));
  } else {
    log.append(el(`<div class="empty" style="padding:16px">Your coach is here around the clock — training calls,
      food questions, motivation. They can see today's numbers and your readiness.</div>`));
  }
  requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });

  const chatForm = chatCard.querySelector('form');
  chatForm.addEventListener('submit', async e => {
    e.preventDefault();
    const message = chatForm.message.value.trim();
    if (!message) return;
    const btn = chatForm.querySelector('button');
    btn.disabled = true;
    chatForm.message.value = '';
    if (log.querySelector('.empty')) log.innerHTML = '';
    log.append(bubble({ role: 'user', text: message, ts: '' }));
    const thinking = el(`<div class="chat-msg coach"><span class="spinner"></span>${esc(selected?.name || 'Coach')} is thinking…</div>`);
    log.append(thinking);
    log.scrollTop = log.scrollHeight;
    try {
      const { reply, actions } = await api('POST', '/coach/chat', { message });
      const said = bubble({ role: 'coach', text: reply, coach: state.coach, ts: 'now' });
      thinking.replaceWith(said);
      // The coach proposes; nothing is written until the athlete confirms.
      (actions || []).forEach(a => said.after(actionCard(a)));
    } catch (err) {
      thinking.remove();
      toast(err.message);
    } finally {
      btn.disabled = false;
      log.scrollTop = log.scrollHeight;
      chatForm.message.focus();
    }
  });
  chatCard.querySelectorAll('.qa-chip').forEach(chip => chip.addEventListener('click', () => {
    chatForm.message.value = chip.textContent;
    chatForm.requestSubmit();
  }));
  const clearBtn = chatCard.querySelector('.chat-clear');
  if (clearBtn) clearBtn.addEventListener('click', async () => {
    try { await api('DELETE', '/coach/chat'); toast('Thread cleared'); await refresh(); }
    catch (e) { toast(e.message); }
  });
  root.append(chatCard);

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
    const prog = state.stats.plan_progress;
    const adherence = prog?.has_plan && prog.pct != null
      ? ` · <span style="color:${prog.pct >= 80 ? 'var(--good)' : prog.pct >= 50 ? 'var(--ink-2)' : 'var(--warn)'}">${prog.done}/${prog.due} sessions done this week (${prog.pct}%)</span>`
      : '';
    planOut.append(el(`<p class="section-sub" style="margin:12px 0 8px">By ${esc(coach?.name || 'your coach')} · ${esc(cached.generated_at)}${adherence}</p>`));

    const statusByDay = {};
    if (prog?.has_plan) for (const x of prog.days) statusByDay[(x.day || '').toLowerCase()] = x.status;

    const week = el('<div class="plan-week"></div>');
    for (const d of plan.week) {
      const status = statusByDay[(d.day || '').toLowerCase()];
      week.append(el(`<div class="plan-day${/rest|recovery/i.test(d.title + d.focus) ? ' rest' : ''}">
        <div class="plan-day-head"><span class="plan-dow">${esc(d.day)}</span>
          ${status ? `<span class="plan-status ${status}">${status}</span>` : ''}</div>
        <div class="plan-day-head"><span class="plan-title">${esc(d.title)}</span></div>
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
  // past reviews archive
  const reviews = (state.reviews || []).slice().reverse();
  if (reviews.length) {
    const arch = el('<div style="margin-top:10px"></div>');
    for (const r of reviews) {
      const by = coaches.find(c => c.id === r.coach)?.name || 'Coach';
      arch.append(el(`<details style="border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--bg);margin-top:6px">
        <summary style="padding:10px 14px;cursor:pointer;list-style:none;font-size:13px;color:var(--ink-2)">
          Review · ${esc(r.date)} · ${esc(by)}</summary>
        <div class="prose" style="padding:0 14px 12px;font-size:13px">${markdown(r.summary)}</div>
      </details>`));
    }
    aiCard.append(arch);
  }
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
