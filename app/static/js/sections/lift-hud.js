// LIFT HUD — the live session, readable from arm's length.
//
// This is a presentation layer, NOT a second implementation. It reads and
// writes the same localStorage session the Workouts panel owns (LIVE_KEY), so
// the two are always the same set: log a set here, switch tabs, and it is
// already there. Duplicating the session model would create two sources of
// truth that diverge mid-workout, which is the worst possible time.
//
// The dense panel stays. It is better for editing, adding exercises, and
// reviewing. This is better for the 90 seconds when you are holding a bar.
import { el, esc, toast } from '../app.js';
import { LIVE_KEY, loadLive, saveLive, platesPerSide, barbellish, e1rm }
  from './workouts.js';

const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

export function openLiftHud(onClose) {
  let s = loadLive();
  if (!s) { toast('Start a session first.'); return; }
  let idx = s.exercises.findIndex(e => !e.targetSets || e.sets.length < e.targetSets);
  if (idx < 0) idx = 0;

  const hud = el(`<div class="lift-hud" role="dialog" aria-label="Live lift">
    <button class="lh-close" type="button" aria-label="Exit lift view">✕</button>
    <div class="lh-body">
      <div class="lh-name" data-f="name">—</div>
      <div class="lh-target" data-f="target">—</div>
      <div class="lh-unit" data-f="unit">LBS · TARGET</div>
      <div class="lh-plates" data-f="plates"></div>
      <div class="lh-e1" data-f="e1"></div>
      <div class="lh-sets" data-f="sets"></div>
      <div class="lh-rest" data-f="rest">READY</div>
    </div>
    <div class="lh-controls">
      <button type="button" class="lh-btn" data-a="prev">◀ exercise</button>
      <button type="button" class="lh-btn" data-a="minus">− 5</button>
      <button type="button" class="lh-btn lh-primary" data-a="log">Log set</button>
      <button type="button" class="lh-btn" data-a="plus">+ 5</button>
      <button type="button" class="lh-btn" data-a="next">exercise ▶</button>
    </div>
    <div class="lh-hint">space · log set &nbsp;|&nbsp; ← → · exercise &nbsp;|&nbsp; ↑ ↓ · weight &nbsp;|&nbsp; esc · exit</div>
  </div>`);

  const F = {};
  hud.querySelectorAll('[data-f]').forEach(n => { F[n.dataset.f] = n; });

  // Working weight per exercise: last set this session, else the plan's target,
  // else the bar. Never left at zero — an unloadable number strands you here
  // with nothing to log and no way to fix it without leaving.
  const working = s.exercises.map(ex => {
    const last = ex.sets[ex.sets.length - 1];
    if (last) return last.w;
    if (ex.targetWeight) return ex.targetWeight;
    return barbellish(ex.name) ? 45 : 10;
  });
  const reps = s.exercises.map(ex => ex.targetReps || 10);

  function paint() {
    const ex = s.exercises[idx];
    if (!ex) return;
    const w = working[idx];
    F.name.textContent = ex.name;
    F.target.textContent = w || '—';
    F.unit.textContent = ex.targetSets
      ? `LBS · SET ${Math.min(ex.sets.length + 1, ex.targetSets)} OF ${ex.targetSets}`
      : 'LBS · TARGET';

    if (barbellish(ex.name) && w >= 65) {
      const p = platesPerSide(w);
      const achieved = p ? 45 + 2 * p.reduce((a, b) => a + b, 0) : 0;
      F.plates.textContent = p && p.length
        ? `${achieved !== w ? `≈${achieved}  ` : ''}PER SIDE  ${p.join(' · ')}`
        : 'EMPTY BAR';
    } else F.plates.textContent = '';

    const est = e1rm(w, reps[idx]);
    F.e1.textContent = est ? `EST 1RM  ${est} LB` : '';

    // Set dots: done, PR (beat every previous top set), or pending.
    const best = Math.max(0, ...s.exercises[idx].sets.map(t => t.w));
    const total = Math.max(ex.targetSets || 0, ex.sets.length);
    F.sets.innerHTML = Array.from({ length: total || ex.sets.length + 1 }, (_, i) => {
      const t = ex.sets[i];
      const cls = !t ? '' : (t.w >= best && t.w > 0 && ex.sets.length > 1) ? ' pr' : ' done';
      return `<i class="lh-dot${cls}"></i>`;
    }).join('');
  }

  function restLeft() {
    if (!s.restEndsAt) return 0;
    return Math.max(0, Math.ceil((s.restEndsAt - Date.now()) / 1000));
  }

  function logSet() {
    const ex = s.exercises[idx];
    const w = working[idx], r = reps[idx];
    if (!(w > 0 && r > 0)) { toast('Set a weight first.'); return; }
    const prevBest = Math.max(0, ...ex.sets.map(t => t.w));
    ex.sets.push({ w, r });
    s.restEndsAt = Date.now() + (s.rest || 90) * 1000;
    saveLive(s);
    if (w > prevBest && ex.sets.length > 1) {
      hud.classList.add('pr');
      setTimeout(() => hud.classList.remove('pr'), 1400);
    }
    paint();
  }

  function step(d) {
    idx = (idx + d + s.exercises.length) % s.exercises.length;
    paint();
  }
  // 5 lb steps throughout (2.5 per side on a bar). The floor differs: a
  // barbell cannot go below the bar, a dumbbell can.
  function weigh(dir) {
    const floor = barbellish(s.exercises[idx].name) ? 45 : 5;
    working[idx] = Math.max(floor, (working[idx] || floor) + dir * 5);
    paint();
  }

  hud.addEventListener('click', ev => {
    const b = ev.target.closest('[data-a]');
    if (b) {
      ({ log: logSet, prev: () => step(-1), next: () => step(1),
         plus: () => weigh(1), minus: () => weigh(-1) })[b.dataset.a]();
      return;
    }
    if (ev.target.closest('.lh-close')) close();
  });

  function keys(ev) {
    const k = ev.key;
    if (k === 'Escape') { close(); return; }
    if (k === ' ') { ev.preventDefault(); logSet(); }
    else if (k === 'ArrowLeft') step(-1);
    else if (k === 'ArrowRight') step(1);
    else if (k === 'ArrowUp') { ev.preventDefault(); weigh(1); }
    else if (k === 'ArrowDown') { ev.preventDefault(); weigh(-1); }
  }
  document.addEventListener('keydown', keys);

  // Re-read the session if the Workouts panel edits it in another tab.
  function sync(ev) {
    if (ev.key !== LIVE_KEY) return;
    const next = loadLive();
    if (!next) { close(); return; }
    s = next; paint();
  }
  addEventListener('storage', sync);

  const tick = setInterval(() => {
    const left = restLeft();
    F.rest.textContent = left ? `REST  ${fmt(left)}` : 'READY';
    F.rest.classList.toggle('ready', !left);
  }, 250);

  function close() {
    clearInterval(tick);
    document.removeEventListener('keydown', keys);
    removeEventListener('storage', sync);
    hud.remove();
    document.body.classList.remove('lift-open');
    onClose?.();
  }

  document.body.append(hud);
  document.body.classList.add('lift-open');
  paint();
  return close;
}
