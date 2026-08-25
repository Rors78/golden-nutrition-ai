// Dashboard: the command center — briefing, next actions, rings, week grid,
// streaks, today's plan, quick weigh-in, trophies, activity.
import { coachMedallion, el, esc, api, toast, refresh, metric, ring, markdown, CHART } from '../app.js';

export function renderDashboard(root, state) {
  const p = state.profile;
  const t = state.stats.today;
  const w = state.stats.weight;

  root.append(el(`<h2 class="section-title">Today's Session</h2>`));

  if (p.weight && p.goal_weight) {
    const diff = p.weight - p.goal_weight;
    const line = diff === 0
      ? `Weight ${p.weight} lbs — at goal`
      : `Weight ${p.weight} lbs → goal ${p.goal_weight} lbs (${Math.abs(diff).toFixed(1)} lbs ${diff > 0 ? 'to lose' : 'to gain'})`;
    root.append(el(`<p class="section-sub">${esc(line)}${w.eta ? ` · on pace for ${esc(w.eta)}` : ''}</p>`));
  } else {
    root.append(el(`<p class="section-sub">Set your weight and goal in Profile to unlock pace tracking.</p>`));
  }

  // ── first run: turn an empty install into a path ──────────────────────
  // A wall of zero-rings is honest and useless. Same emptiness, told as what
  // the next entry unlocks. Disappears on its own once every step is done.
  const ob = state.stats.dashboard?.onboarding;
  if (ob?.active) {
    const rows = ob.steps.map(s => `
      <li class="ob-step${s.done ? ' done' : ''}">
        <span class="ob-mark">${s.done ? '✓' : ''}</span>
        <span class="ob-body">
          <b>${esc(s.title)}</b>
          <small>${esc(s.unlocks)}</small>
        </span>
      </li>`).join('');
    const panel = el(`<div class="card onboarding">
      <div class="ob-head">
        <p class="chart-title" style="color:var(--gold-bright);margin:0">
          ${ob.cold ? 'Start here' : 'Getting set up'}
        </p>
        <span class="ob-count">${ob.complete} / ${ob.total}</span>
      </div>
      <p class="ob-lede">${esc(ob.cold
        ? 'Nothing logged yet — every number below is waiting on you. The app '
          + 'stays quiet rather than guessing, so one entry changes what it can say.'
        : 'Each step switches on a part of the app that is currently silent.')}</p>
      <div class="ob-track"><div class="ob-fill" style="width:${(ob.complete / ob.total * 100).toFixed(0)}%"></div></div>
      <ul class="ob-list">${rows}</ul>
    </div>`);
    root.append(panel);
  }

  // Morning briefing from the coach
  const briefCoach = (state.coaches || []).find(c => c.id === (state.briefing?.coach || state.coach));
  const todayIso = new Date().toISOString().slice(0, 10);
  if (ob?.cold) {
    // Deliberately no briefing button: with nothing logged the request is a
    // guaranteed 422, and offering it was the app's own first suggestion.
  } else if (state.briefing?.date === todayIso) {
    root.append(el(`<div class="card" style="margin-top:4px;border-left:4px solid var(--gold)">
      <p class="chart-title">Morning briefing · ${esc(briefCoach?.name || 'Coach')}</p>
      <div class="prose" style="font-size:14px">${markdown(state.briefing.text)}</div>
    </div>`));
  } else {
    const bb = el(`<div style="margin:4px 0 10px"><button class="ghost-btn" type="button">Get today's briefing from ${esc(briefCoach?.name || 'your coach')}</button></div>`);
    bb.querySelector('button').addEventListener('click', async ev => {
      ev.target.disabled = true;
      ev.target.textContent = 'Coach is writing…';
      try {
        await api('POST', '/briefing');
        toast('Briefing ready');
        await refresh();
      } catch (e) {
        toast(e.message);
        ev.target.disabled = false;
        ev.target.textContent = 'Get today\'s briefing';
      }
    });
    root.append(bb);
  }

  // Next best actions — what the data says to do right now
  const dash = state.stats.dashboard || {};
  if (dash.actions?.length) {
    const row = el('<div style="display:grid;gap:8px;margin:0 0 10px"></div>');
    for (const a of dash.actions) {
      const btn = el(`<button type="button" class="callout" style="text-align:left;cursor:pointer;width:100%;border:0;border-left:4px solid var(--gold);color:var(--ink);font:inherit;font-size:13px">
        <strong style="color:var(--gold-bright)">Next up:</strong> ${esc(a.text)}</button>`);
      btn.addEventListener('click', async () => {
        if (a.id === 'briefing') {
          btn.disabled = true;
          btn.textContent = 'Your coach is writing…';
          try { await api('POST', '/briefing'); toast('Briefing ready'); await refresh(); }
          catch (e) { toast(e.message); btn.disabled = false; }
        } else {
          location.hash = a.tab;
        }
      });
      row.append(btn);
    }
    root.append(row);
  }

  // Radar: cross-tab signals worth a glance
  if (dash.radar?.length) {
    const radar = el('<div style="display:grid;gap:6px;margin:0 0 10px"></div>');
    for (const r of dash.radar) {
      const line = el(`<button type="button" class="callout ${r.level === 'good' ? 'good' : 'warn'}"
        style="text-align:left;cursor:pointer;width:100%;border:0;border-left:3px solid ${r.level === 'good' ? 'var(--good)' : 'var(--warn)'};color:var(--ink-2);font:inherit;font-size:12px;padding:8px 14px">${esc(r.text)}</button>`);
      line.addEventListener('click', () => { location.hash = r.tab; });
      radar.append(line);
    }
    root.append(radar);
  }

  // Steps from the watch, if vitals are flowing
  const vsum = state.stats.vitals;

  // Hero: the two rings that define the day
  const hero = el('<div class="card"><div class="rings"></div></div>');
  const rings = hero.querySelector('.rings');
  rings.append(
    ring('Protein', t.totals.protein, p.daily_protein_g, 'g', { size: 170 }),
    ring('Calories', t.totals.calories, p.daily_calories, '', { size: 170, steel: true }),
  );
  const rd = state.stats.readiness;
  if (rd?.has_data) {
    const rdRing = ring('Readiness', rd.score, 100, '', { size: 170 });
    rdRing.classList.add('readiness');
    rdRing.querySelector('.ring-sub').textContent = `${rd.level} · ${rd.date}`;
    rings.append(rdRing);
    hero.append(el(`<p style="text-align:center;color:var(--ink-2);font-size:13px;margin:10px 0 0">${esc(rd.guidance)}</p>`));
    const rSeries = (state.stats.readiness_series || []).slice(-14);
    if (rSeries.length > 2) {
      const spark = el('<div style="height:44px;max-width:420px;margin:6px auto 0"></div>');
      hero.append(spark);
      Plotly.newPlot(spark,
        [{ x: rSeries.map(r => r.date), y: rSeries.map(r => r.score), mode: 'lines',
           line: { color: CHART.gold, width: 2, shape: 'spline' },
           hovertemplate: '%{x}<br>readiness %{y}<extra></extra>' }],
        CHART.layout({ height: 44, margin: { l: 4, r: 4, t: 2, b: 2 },
          xaxis: { visible: false, fixedrange: true },
          yaxis: { visible: false, fixedrange: true, range: [0, 105] } }),
        CHART.config);
    }
  }
  root.append(hero);

  // Week at a glance: the consistency grid
  if (dash.week_grid?.length) {
    const DOT = (on, color, label) =>
      `<span title="${esc(label)}" style="width:10px;height:10px;border-radius:3px;display:inline-block;background:${on ? color : 'var(--card-2)'}"></span>`;
    const W_COLOR = { done: 'var(--good)', missed: 'var(--warn)', rest: 'var(--muted)',
                      none: 'var(--card-2)', future: 'var(--card-2)' };
    const wk = el(`<div class="card" style="margin-top:14px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px">
        <p class="chart-title" style="margin:0">This week</p>
        <span style="font-size:11px;color:var(--muted)">
          <span style="color:var(--good)">■</span> trained ·
          <span style="color:var(--gold)">■</span> protein ·
          <span style="color:var(--steel)">■</span> weighed ·
          <span style="color:var(--ink-2)">■</span> vitals</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-top:10px" class="wk-cols"></div>
      <p class="wk-streaks" style="margin:12px 0 0;font-size:12px;color:var(--ink-2);font-family:var(--font-mono)"></p>
    </div>`);
    const cols = wk.querySelector('.wk-cols');
    for (const d of dash.week_grid) {
      cols.append(el(`<div style="text-align:center;padding:8px 2px;border-radius:8px;${
        d.is_today ? 'background:var(--card-2);outline:1px solid var(--gold-dim)' : ''}">
        <div style="font-size:10px;font-weight:800;letter-spacing:.08em;color:${d.is_today ? 'var(--gold-bright)' : 'var(--muted)'};text-transform:uppercase">${esc(d.day)}</div>
        <div style="display:flex;flex-direction:column;gap:4px;align-items:center;margin-top:6px">
          <span title="workout: ${esc(d.workout)}" style="width:10px;height:10px;border-radius:3px;display:inline-block;background:${W_COLOR[d.workout] || 'var(--card-2)'}"></span>
          ${DOT(d.protein_pct >= 80, 'var(--gold)', `protein ${d.protein_pct}%`)}
          ${DOT(d.weighed, 'var(--steel)', d.weighed ? 'weighed in' : 'no weigh-in')}
          ${DOT(d.vitals, 'var(--ink-2)', d.vitals ? 'vitals synced' : 'no vitals')}
        </div></div>`));
    }
    const s = dash.streaks || {};
    const chains = [
      ['meals logged', s.meals, 'd'],
      ['protein goal', state.stats.nutrition?.protein_streak, 'd'],
      ['weigh-ins', state.stats.weight_extras?.streak, 'd'],
      ['step goal', state.stats.step_stats?.has_goal ? state.stats.step_stats.streak : null, 'd'],
      ['vitals', s.vitals, 'd'],
      ['training', s.workout_weeks, 'wk'],
    ].filter(([, v]) => v != null);
    const strip = wk.querySelector('.wk-streaks');
    strip.style.display = 'flex';
    strip.style.flexWrap = 'wrap';
    strip.style.gap = '6px';
    strip.textContent = '';
    for (const [label, val, unit] of chains) {
      strip.append(el(`<span style="border:1px solid ${val > 0 ? 'var(--gold-dim)' : 'var(--line)'};border-radius:999px;padding:3px 10px;font-size:11px;
        color:${val > 0 ? 'var(--gold-bright)' : 'var(--muted)'}">${esc(label)} <strong>${val}${unit}</strong></span>`));
    }
    root.append(wk);
  }

  const grid = el('<div class="cards metrics" style="margin-top:14px"></div>');
  grid.append(
    metric('Carbs', t.totals.carbs, { suffix: 'g' }),
    metric('Fat', t.totals.fat, { suffix: 'g' }),
    metric('Fiber', t.totals.fiber, { suffix: 'g' }),
    metric('Meals', t.meal_count, {}),
    metric('Workouts', t.workout_count, {}),
  );
  const adh = state.stats.adherence;
  if (adh?.has_schedule) {
    grid.append(metric('Stack adherence', adh.pct, { suffix: '%', small: '7d' }));
  }
  if (vsum?.has_data && vsum.latest.steps) {
    grid.append(metric('Steps', vsum.latest.steps.value, { small: `goal ${vsum.steps_goal}` }));
  }
  const lastPr = (state.stats.recent_prs || [])[0];
  if (lastPr) {
    grid.append(metric('Latest PR', lastPr.weight, { suffix: ' lbs',
      small: `${lastPr.exercise} · ${lastPr.date.slice(5)}` }));
  }
  root.append(grid);

  // ── the consistency map: six months of showing up, one cell per day ──
  const heat = state.stats.log_heat || {};
  if (heat.has_data) {
    const hm = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">The consistency map</p>
      <p style="color:var(--muted);font-size:12px;margin:4px 0 10px">Each cell is
        a day; it burns brighter for every kind of thing logged — meals, a lift,
        the scale, vitals, the tape. Kinds, not counts: showing up is the metric.</p>
      <div class="heat-wrap"><div class="heat-grid"></div></div>
      <div class="heat-foot">
        <span><b>${heat.current_streak}</b> day streak</span>
        <span><b>${heat.longest_streak}</b> longest</span>
        <span><b>${heat.days_logged}</b> of ${heat.total_days} days logged</span>
        <span class="heat-scale">less <i class="h0"></i><i class="h1"></i><i class="h2"></i><i class="h3"></i><i class="h4"></i> more</span>
      </div></div>`);
    const gridEl = hm.querySelector('.heat-grid');
    // Column per week, row per weekday — pad the front so columns align.
    const pad = (new Date(heat.start + 'T00:00').getDay() + 6) % 7;   // Monday-first
    for (let i = 0; i < pad; i += 1) gridEl.append(el('<i class="hpad"></i>'));
    for (const c of heat.days) {
      const cell = el(`<i class="h${c.n}" title="${esc(c.date)} · ${c.n} kind${c.n === 1 ? '' : 's'}"></i>`);
      gridEl.append(cell);
    }
    root.append(hm);
  }

  // Today's plan (from the coach-generated week) + coach strip
  const coach = (state.coaches || []).find(c => c.id === state.coach);
  const week = state.plan?.plan?.week || [];
  const todayName = new Date().toLocaleDateString('en-US', { weekday: 'long' });
  const planDay = week.find(d => (d.day || '').toLowerCase().includes(todayName.toLowerCase()));

  if (planDay) {
    const card = el(`<div class="card" style="margin-top:14px">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <span class="medal-slot"></span>
        <div style="flex:1;min-width:200px">
          <p class="chart-title" style="margin:0">Today's plan · ${esc(todayName)}</p>
          <p style="margin:2px 0 0;font-weight:800;color:var(--gold-bright)">${esc(planDay.title)}
            <span style="color:var(--steel);font-weight:600;font-size:13px"> — ${esc(planDay.focus)}</span></p>
        </div>
        <button class="ghost-btn" type="button" style="flex:0 1 auto">Full week</button>
      </div>
      <ul style="margin:10px 0 0;padding-left:20px;color:var(--ink-2);font-size:13px">
        ${planDay.details.map(x => {
          const hit = (state.stats.next_targets || []).find(t =>
            String(x).toLowerCase().includes(t.exercise.toLowerCase()));
          const tag = hit ? ` <span title="${esc(hit.why)}" style="font-family:var(--font-mono);font-size:11px;color:${
            hit.action === 'increase' ? 'var(--gold-bright)' : 'var(--steel)'}">→ next ${hit.next_weight}${
            hit.action === 'increase' ? ' ▲' : ''}</span>` : '';
          return `<li style="margin:3px 0">${esc(x)}${tag}</li>`;
        }).join('')}
      </ul>
    </div>`);
    card.querySelector('button').addEventListener('click', () => { location.hash = 'coach'; });
    root.append(card);
  } else if (coach) {
    const strip = el(`<div class="card" style="margin-top:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <span class="medal-slot"></span>
      <div style="flex:1;min-width:200px">
        <p class="chart-title" style="margin:0">Coached by ${esc(coach.name)} · ${esc(coach.style)}</p>
        <p style="margin:2px 0 0;color:var(--ink-2);font-size:13px">${esc(coach.vibe)}</p>
      </div>
      <button class="ghost-btn" type="button" style="flex:0 1 auto">Build my week</button>
    </div>`);
    strip.querySelector('button').addEventListener('click', () => { location.hash = 'coach'; });
    root.append(strip);
  }

  // Body: quick weigh-in + 30-day trend sparkline
  const wt = state.stats.weight;
  const body = el(`<div class="card" style="margin-top:14px">
    <div class="form-row" style="align-items:end">
      <div style="flex:1;min-width:180px">
        <p class="chart-title" style="margin:0 0 4px">Body</p>
        ${wt.has_data
          ? `<p style="margin:0;font-family:var(--font-mono);font-size:13px;color:var(--ink-2)">
              ${wt.current} lbs${wt.rate_per_week != null ? ` · ${wt.rate_per_week > 0 ? '+' : ''}${wt.rate_per_week} lbs/wk` : ''}${wt.eta ? ` · goal ~${esc(wt.eta)}` : ''}</p>`
          : '<p style="margin:0;color:var(--muted);font-size:13px">No weigh-ins yet — start the trend right here.</p>'}
      </div>
      <label style="flex:0 1 150px">Today's weight
        <input name="qw" type="number" step="0.1" min="1" placeholder="${wt.has_data ? wt.current : '200.0'}"></label>
      <button class="gold-btn" type="button" style="flex:0 1 auto">Log</button>
    </div>
    <div class="body-spark" style="margin-top:8px"></div>
  </div>`);
  body.querySelector('button').addEventListener('click', async () => {
    const val = body.querySelector('input').value;
    if (!val) { toast('Type a weight first.'); return; }
    try {
      await api('POST', '/weights', { weight: val });
      toast('Weigh-in logged');
      await refresh();
    } catch (e) { toast(e.message); }
  });
  if (wt.has_data && wt.series_avg?.length >= 2) {
    const spark = body.querySelector('.body-spark');
    spark.style.height = '64px';
    Plotly.newPlot(spark,
      [{ x: wt.series_avg.map(x => x.date), y: wt.series_avg.map(x => x.avg),
         mode: 'lines', line: { color: CHART.gold, width: 2, shape: 'spline' },
         hovertemplate: '%{x}<br>%{y:.1f} lbs<extra>7d avg</extra>' }],
      CHART.layout({ height: 64, margin: { l: 38, r: 6, t: 4, b: 16 },
        xaxis: { visible: false, fixedrange: true },
        yaxis: { gridcolor: 'rgba(110,118,131,.12)', zeroline: false, fixedrange: true, tickfont: { size: 9 } } }),
      CHART.config);
  }
  root.append(body);

  // Trophy wall — earned by data, never by hand
  const badges = state.stats.achievements || [];
  if (badges.length) {
    const earned = badges.filter(b => b.earned).length;
    const wall = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Trophy wall · ${earned}/${badges.length}</p>
      <div class="trophy-grid" style="display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));margin-top:10px"></div>
    </div>`);
    const grid2 = wall.querySelector('.trophy-grid');
    for (const b of [...badges].sort((x, y) => y.earned - x.earned)) {
      grid2.append(el(`<div style="display:flex;gap:12px;align-items:center;opacity:${b.earned ? 1 : .55}">
        <span class="plate-disc ${b.earned ? '' : 'iron'}" style="width:40px;height:40px;font-size:13px">${esc(b.name.replace(/[^A-Za-z ]/g, '').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase())}</span>
        <span style="min-width:0">
          <span style="display:block;font-weight:800;font-size:13px">${esc(b.name)}</span>
          <span style="display:block;color:var(--muted);font-size:12px">${esc(b.desc)}${b.earned ? '' : ` · ${b.progress}/${b.target}`}</span>
        </span></div>`));
    }
    root.append(wall);
  }

  const two = el('<div class="cards two" style="margin-top:14px"></div>');

  const mealsCard = el('<div class="card"><p class="chart-title">Recent meals</p></div>');
  if (t.recent_meals.length) {
    for (const m of t.recent_meals) {
      mealsCard.append(el(`<p style="margin:6px 0"><span style="font-family:var(--font-mono);color:var(--muted)">${esc(m.time)}</span>
        &nbsp;${esc(m.name)} — <span class="note-good">${esc(m.protein)}g P</span>, ${esc(m.calories)} cal</p>`));
    }
  } else {
    mealsCard.append(el('<div class="empty">No meals yet today. Log one in Meals — or just tell the AI what you ate.</div>'));
  }

  const woCard = el('<div class="card"><p class="chart-title">Recent workouts</p></div>');
  if (t.recent_workouts.length) {
    for (const w2 of t.recent_workouts) {
      woCard.append(el(`<p style="margin:6px 0"><span style="font-family:var(--font-mono);color:var(--muted)">${esc(w2.time)}</span>
        &nbsp;${esc(w2.name)} — ${esc(w2.duration)} min, ${esc(w2.intensity)}</p>`));
    }
  } else {
    woCard.append(el('<div class="empty">Rest day so far. The plates are waiting in Workouts.</div>'));
  }

  // ── the week in iron: last 7 days, graded against your own plans ──
  const WI = state.stats.week_in_iron || {};
  if (WI.has_data) {
    const R = 34, C = 2 * Math.PI * R;
    const frac = WI.score / 100;
    const ringCol = WI.score >= 75 ? 'var(--good)' : WI.score >= 45 ? 'var(--gold)' : 'var(--warn)';
    const wi = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">The week in iron</p>
      <p style="color:var(--muted);font-size:12px;margin:4px 0 12px">The last seven
        days against your own plans — every point accounted for, so you can argue
        with any line of it.</p>
      <div class="wi-wrap">
        <svg viewBox="0 0 84 84" class="wi-ring" role="img" aria-label="week score ${WI.score} of 100">
          <circle cx="42" cy="42" r="${R}" fill="none" stroke="var(--card-2)" stroke-width="7"/>
          <circle cx="42" cy="42" r="${R}" fill="none" stroke="${ringCol}" stroke-width="7"
            stroke-linecap="round" stroke-dasharray="${(C * frac).toFixed(1)} ${C.toFixed(1)}"
            transform="rotate(-90 42 42)"/>
          <text x="42" y="47" text-anchor="middle" class="wi-score">${WI.score}</text>
        </svg>
        <div class="wi-cols">
          ${WI.columns.map(c2 => `<div class="wi-row">
            <span class="wi-key">${esc(c2.key)}</span>
            <div class="wi-bar"><i style="width:${c2.max ? c2.pts / c2.max * 100 : 0}%"></i></div>
            <span class="wi-pts">${c2.pts}/${c2.max}</span>
            <span class="wi-note">${esc(c2.note)}</span>
          </div>`).join('')}
        </div>
      </div></div>`);
    root.append(wi);
  }

  // mint the coach's coin into every slot the dashboard drew
  if (coach) root.querySelectorAll('.medal-slot').forEach(sl => {
    if (!sl.firstChild) sl.append(coachMedallion(coach, 38));
  });

  two.append(mealsCard, woCard);
  root.append(two);

  // ── the forge card: the log, struck into something you can send ──────
  const fc = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">The forge card</p>
    <p style="color:var(--muted);font-size:12px;margin:4px 0 10px">Your current
      numbers — weight, trend, composition, best lift, streak — struck into a
      single dark-and-gold card. Rendered on this machine; nothing leaves it
      until you choose to send the picture.</p>
    <button type="button" class="ghost-btn fc-btn" style="flex:0 1 auto">Forge the card</button>
    <div class="fc-out" hidden style="margin-top:12px">
      <img class="fc-img" alt="progress card" style="width:100%;max-width:420px;border-radius:8px;display:block">
      <div class="form-row" style="margin-top:10px">
        <a class="gold-btn fc-dl" download="">Download PNG</a>
        <button type="button" class="ghost-btn fc-close" style="flex:0 1 auto">Close</button>
      </div>
    </div>
  </div>`);
  fc.querySelector('.fc-btn').addEventListener('click', () => {
    const url2 = forgeCard(state);
    fc.querySelector('.fc-img').src = url2;
    const a = fc.querySelector('.fc-dl');
    a.href = url2;
    a.download = `golden-progress-${new Date().toISOString().slice(0, 10)}.png`;
    fc.querySelector('.fc-out').hidden = false;
  });
  fc.querySelector('.fc-close').addEventListener('click', () => {
    fc.querySelector('.fc-out').hidden = true;
  });
  root.append(fc);
}

// Renders the card on an offscreen canvas and returns a data URL. All
// colours come from the design tokens so the card matches the app; every
// block draws only if its data exists — a young log makes a sparse card,
// not a card full of dashes.
function forgeCard(state) {
  const css = getComputedStyle(document.documentElement);
  const tok = n => css.getPropertyValue(n).trim();
  const GOLD = tok('--gold') || '#f2c14e', BRIGHT = tok('--gold-bright') || '#ffd875';
  const BG = tok('--bg') || '#0e1013', INK = tok('--ink') || '#f2f4f6';
  const MUTED = tok('--muted') || '#6e7683', STEEL = tok('--steel') || '#6ea8d8';
  const GOOD = tok('--good') || '#7ee081', LINE = tok('--line') || '#272d36';
  const MONO = '"IBM Plex Mono", ui-monospace, monospace';
  const BODY = '"Archivo", system-ui, sans-serif';

  const W = 1080, H = 1350;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');

  g.fillStyle = BG; g.fillRect(0, 0, W, H);
  g.strokeStyle = 'rgba(143,227,242,.035)'; g.lineWidth = 1;
  for (let x = 60; x < W; x += 120) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
  for (let y = 60; y < H; y += 120) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }

  // wordmark + plate rings
  g.strokeStyle = GOLD; g.lineWidth = 6;
  g.beginPath(); g.arc(110, 110, 40, 0, 7); g.stroke();
  g.lineWidth = 3; g.beginPath(); g.arc(110, 110, 22, 0, 7); g.stroke();
  g.fillStyle = INK; g.font = `800 44px ${BODY}`;
  g.fillText('GOLDEN', 180, 100);
  g.fillStyle = GOLD; g.fillText('NUTRITION AI', 180, 148);
  g.fillStyle = MUTED; g.font = `20px ${MONO}`; g.textAlign = 'right';
  g.fillText(new Date().toISOString().slice(0, 10), W - 70, 110);
  g.textAlign = 'left';

  const w = state.stats.weight || {};
  let y = 300;
  if (w.has_data) {
    g.fillStyle = MUTED; g.font = `22px ${MONO}`;
    g.fillText('BODYWEIGHT', 70, y);
    g.fillStyle = INK; g.font = `800 150px ${BODY}`;
    g.fillText(`${w.current}`, 62, y + 150);
    const cw = g.measureText(`${w.current}`).width;
    g.fillStyle = MUTED; g.font = `700 44px ${BODY}`;
    g.fillText('lb', 74 + cw, y + 150);
    if (w.total_change != null) {
      const down = w.total_change <= 0;
      g.fillStyle = down ? GOOD : GOLD; g.font = `30px ${MONO}`;
      g.fillText(`${w.total_change > 0 ? '+' : ''}${w.total_change} lb since ${w.since}`, 70, y + 210);
    }
    y += 280;
    // sparkline of the whole voyage
    const series = w.series || [];
    if (series.length > 2) {
      const x0 = 70, x1 = W - 70, y0 = y, y1 = y + 210;
      const vals = series.map(p => p.weight);
      const lo = Math.min(...vals, w.goal || Infinity), hi = Math.max(...vals);
      const sx = i => x0 + i / (series.length - 1) * (x1 - x0);
      const sy = v => y1 - (v - lo) / Math.max(hi - lo, 0.1) * (y1 - y0);
      if (w.goal) {
        g.strokeStyle = GOOD; g.setLineDash([6, 8]); g.lineWidth = 2;
        g.beginPath(); g.moveTo(x0, sy(w.goal)); g.lineTo(x1, sy(w.goal)); g.stroke();
        g.setLineDash([]);
        g.fillStyle = GOOD; g.font = `20px ${MONO}`; g.textAlign = 'right';
        g.fillText(`goal ${w.goal}`, x1, sy(w.goal) - 10); g.textAlign = 'left';
      }
      g.strokeStyle = GOLD; g.lineWidth = 4; g.beginPath();
      series.forEach((p, i) => i ? g.lineTo(sx(i), sy(p.weight)) : g.moveTo(sx(i), sy(p.weight)));
      g.stroke();
      g.fillStyle = BRIGHT;
      g.beginPath(); g.arc(sx(series.length - 1), sy(vals[vals.length - 1]), 8, 0, 7); g.fill();
      y = y1 + 90;
    }
  } else {
    g.fillStyle = MUTED; g.font = `28px ${MONO}`;
    g.fillText('THE LOG IS YOUNG — THE NUMBERS ARE COMING', 70, y + 60);
    y += 180;
  }

  // stat chips: only what exists
  const chips = [];
  const bc = state.stats.body_comp || {};
  if (bc.current != null) chips.push(['BODY FAT', `${bc.current}%`, STEEL]);
  const heat = state.stats.log_heat || {};
  if (heat.has_data) chips.push(['STREAK', `${heat.current_streak} days`, GOLD]);
  if (heat.has_data) chips.push(['DAYS LOGGED', `${heat.days_logged}`, INK]);
  const ss = state.stats.strength_standards || {};
  if (ss.has_data && ss.lifts.length) {
    const best = [...ss.lifts].sort((a, b) => b.bw_ratio - a.bw_ratio)[0];
    chips.push([best.lift.toUpperCase(), `${best.e1rm} lb · ${best.rank}`, BRIGHT]);
  }
  const rd = state.stats.readiness || {};
  if (rd.has_data) chips.push(['READINESS', `${rd.score}`, GOOD]);

  let cxp = 70;
  for (const [lab, val, col] of chips.slice(0, 5)) {
    g.font = `700 34px ${BODY}`;
    const wch = Math.max(g.measureText(val).width, g.measureText(lab).width * 0.62) + 56;
    if (cxp + wch > W - 70) { cxp = 70; y += 140; }   // wrap, never drop
    g.strokeStyle = LINE; g.lineWidth = 2;
    g.beginPath(); g.roundRect(cxp, y, wch, 118, 14); g.stroke();
    g.fillStyle = MUTED; g.font = `17px ${MONO}`;
    g.fillText(lab, cxp + 26, y + 40);
    g.fillStyle = col; g.font = `700 34px ${BODY}`;
    g.fillText(val, cxp + 26, y + 88);
    cxp += wch + 22;
  }

  g.fillStyle = MUTED; g.font = `22px ${MONO}`;
  g.fillText('the iron doesn\'t lie. neither does the log.', 70, H - 70);
  g.strokeStyle = GOLD; g.lineWidth = 3;
  g.beginPath(); g.moveTo(70, H - 110); g.lineTo(W - 70, H - 110); g.stroke();

  return c.toDataURL('image/png');
}
