// Dashboard: hero progress rings, today's numbers, recent activity.
import { el, esc, metric, ring } from '../app.js';

export function renderDashboard(root, state) {
  const p = state.profile;
  const t = state.stats.today;
  const w = state.stats.weight;

  root.append(el(`<h2 class="section-title">Today's Session</h2>`));

  if (p.weight && p.goal_weight) {
    const diff = p.weight - p.goal_weight;
    const line = diff === 0
      ? `Weight ${p.weight} lbs — at goal 🎯`
      : `Weight ${p.weight} lbs → goal ${p.goal_weight} lbs (${Math.abs(diff).toFixed(1)} lbs ${diff > 0 ? 'to lose' : 'to gain'})`;
    root.append(el(`<p class="section-sub">${esc(line)}${w.eta ? ` · on pace for ${esc(w.eta)}` : ''}</p>`));
  } else {
    root.append(el(`<p class="section-sub">Set your weight and goal in Profile to unlock pace tracking.</p>`));
  }

  // Hero: the two rings that define the day
  const hero = el('<div class="card"><div class="rings"></div></div>');
  hero.querySelector('.rings').append(
    ring('Protein', t.totals.protein, p.daily_protein_g, 'g', { size: 170 }),
    ring('Calories', t.totals.calories, p.daily_calories, '', { size: 170, steel: true }),
  );
  root.append(hero);

  const grid = el('<div class="cards metrics" style="margin-top:14px"></div>');
  grid.append(
    metric('Carbs', t.totals.carbs, { suffix: 'g' }),
    metric('Fat', t.totals.fat, { suffix: 'g' }),
    metric('Fiber', t.totals.fiber, { suffix: 'g' }),
    metric('Meals', t.meal_count, {}),
    metric('Workouts', t.workout_count, {}),
  );
  root.append(grid);

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
