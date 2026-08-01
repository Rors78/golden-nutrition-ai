// Dashboard: morning briefing, hero rings, today's plan, numbers, activity.
import { el, esc, api, toast, refresh, metric, ring, markdown } from '../app.js';

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

  // Morning briefing from the coach
  const briefCoach = (state.coaches || []).find(c => c.id === (state.briefing?.coach || state.coach));
  const todayIso = new Date().toISOString().slice(0, 10);
  if (state.briefing?.date === todayIso) {
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
  }
  root.append(hero);

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
  root.append(grid);

  // Today's plan (from the coach-generated week) + coach strip
  const coach = (state.coaches || []).find(c => c.id === state.coach);
  const week = state.plan?.plan?.week || [];
  const todayName = new Date().toLocaleDateString('en-US', { weekday: 'long' });
  const planDay = week.find(d => (d.day || '').toLowerCase().includes(todayName.toLowerCase()));

  if (planDay) {
    const card = el(`<div class="card" style="margin-top:14px">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <span class="plate-disc" style="width:38px;height:38px;font-size:12px">${esc((coach?.name || 'C').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase())}</span>
        <div style="flex:1;min-width:200px">
          <p class="chart-title" style="margin:0">Today's plan · ${esc(todayName)}</p>
          <p style="margin:2px 0 0;font-weight:800;color:var(--gold-bright)">${esc(planDay.title)}
            <span style="color:var(--steel);font-weight:600;font-size:13px"> — ${esc(planDay.focus)}</span></p>
        </div>
        <button class="ghost-btn" type="button" style="flex:0 1 auto">Full week</button>
      </div>
      <ul style="margin:10px 0 0;padding-left:20px;color:var(--ink-2);font-size:13px">
        ${planDay.details.map(x => `<li style="margin:3px 0">${esc(x)}</li>`).join('')}
      </ul>
    </div>`);
    card.querySelector('button').addEventListener('click', () => { location.hash = 'coach'; });
    root.append(card);
  } else if (coach) {
    const strip = el(`<div class="card" style="margin-top:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <span class="plate-disc" style="width:38px;height:38px;font-size:12px">${esc(coach.name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase())}</span>
      <div style="flex:1;min-width:200px">
        <p class="chart-title" style="margin:0">Coached by ${esc(coach.name)} · ${esc(coach.style)}</p>
        <p style="margin:2px 0 0;color:var(--ink-2);font-size:13px">${esc(coach.vibe)}</p>
      </div>
      <button class="ghost-btn" type="button" style="flex:0 1 auto">Build my week</button>
    </div>`);
    strip.querySelector('button').addEventListener('click', () => { location.hash = 'coach'; });
    root.append(strip);
  }

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

  two.append(mealsCard, woCard);
  root.append(two);
}
