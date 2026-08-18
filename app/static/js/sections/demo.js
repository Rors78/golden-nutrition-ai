// DEMO MODE — the loop that runs on a screen in a shop window.
//
// Cycles every capability with a full, plausible dataset, then puts the real
// data back. Nothing here touches nutrition_data.json: the demo swaps the
// in-memory State object the renderers read from, so the loop can show a
// twelve-week transformation on an install that has logged nothing.
//
// Start with #demo (or the footer link). Any key or click exits.
import { State, setState, refresh, showTab, api, toast } from '../app.js';

const DAY = 86400000;
const iso = d => new Date(d).toISOString().slice(0, 10);

// A believable twelve weeks: a cut that is working, with the plateau and the
// noisy days left in. A demo of clean data would be a demo of a different app.
function demoData(base) {
  const now = Date.now();
  const weights = [];
  for (let i = 84; i >= 0; i -= 1) {
    const t = (84 - i) / 84;
    // plateau in the middle third, plus daily water noise
    const trend = 232 - 22 * (t < 0.35 ? t * 0.9 : t < 0.6 ? 0.32 : t * 1.05);
    const noise = Math.sin(i * 2.7) * 0.55 + Math.cos(i * 1.3) * 0.35;
    if (i % 1 === 0) weights.push({ date: iso(now - i * DAY), weight: +(trend + noise).toFixed(1) });
  }
  const meals = [], workouts = [];
  const dishes = [
    ['Eggs & oats', 38, 520], ['Chicken, rice, broccoli', 52, 640],
    ['Whey shake', 30, 180], ['Steak & sweet potato', 48, 700],
    ['Greek yogurt & berries', 22, 240], ['Salmon & quinoa', 44, 610],
  ];
  const split = [
    ['Push Day', [['Bench Press', 3, 5, 225], ['Overhead Press', 3, 8, 135],
                  ['Cable Fly', 3, 12, 40]]],
    ['Pull Day', [['Barbell Row', 4, 6, 205], ['Lat Pulldown', 3, 10, 160],
                  ['Barbell Curl', 3, 10, 75]]],
    ['Leg Day', [['Back Squat', 4, 5, 315], ['Romanian Deadlift', 3, 8, 245],
                 ['Leg Press', 3, 12, 400]]],
  ];
  for (let i = 27; i >= 0; i -= 1) {
    const d = iso(now - i * DAY);
    for (let k = 0; k < 3 + (i % 2); k += 1) {
      const [name, p, c] = dishes[(i * 3 + k) % dishes.length];
      meals.push({ date: d, time: `${8 + k * 4}:30`.padStart(5, '0'), name,
                   protein: p, calories: c, carbs: Math.round(c * 0.09),
                   fat: Math.round(c * 0.035), fiber: 4, notes: '' });
    }
    if (i % 7 !== 3 && i % 7 !== 6) {
      const [nm, exs] = split[i % 3];
      // progressive overload: the same lifts creep up across the block
      const bump = Math.floor((27 - i) / 9) * 5;
      workouts.push({
        date: d, time: '17:30', name: nm, duration: 62, intensity: 'Hard', notes: '',
        exercises: exs.map(([e, s, r, w]) => ({ exercise: e, sets: s, reps: r,
                                                weight: w + bump })),
      });
    }
  }
  const vitals = Array.from({ length: 28 }, (_, k) => {
    const i = 27 - k;
    return { date: iso(now - i * DAY), steps: 7200 + ((i * 733) % 4200),
             sleep_h: +(6.6 + Math.sin(i) * 0.9).toFixed(1),
             resting_hr: 54 + (i % 5), hrv_ms: 58 + ((i * 7) % 22) };
  });
  return {
    ...base,
    profile: { ...base.profile, name: 'Demo', sex: 'male', age: 34, height_in: 71,
               weight: weights[weights.length - 1].weight, goal_weight: 190,
               daily_protein_g: 190, daily_calories: 2470, notes: '' },
    weights, meals, workouts, vitals,
    measurements: [
      { date: iso(now - 84 * DAY), neck_in: 15.8, chest_in: 42.4, waist_in: 39.8,
        hips_in: 42.0, arm_in: 14.8, thigh_in: 23.0 },
      { date: iso(now - 42 * DAY), neck_in: 15.6, chest_in: 42.9, waist_in: 38.5,
        hips_in: 41.5, arm_in: 15.0, thigh_in: 23.2 },
      { date: iso(now - 2 * DAY), neck_in: 15.4, chest_in: 43.6, waist_in: 37.0,
        hips_in: 40.9, arm_in: 15.4, thigh_in: 23.5 },
    ],
    supplements: [], supplement_schedule: base.supplement_schedule || [],
  };
}

// Each stop names what it is showing, because a screen nobody is standing at
// has to explain itself.
const STOPS = [
  ['vessel', 'THE VESSEL', 'Every ring is a real tape measurement. The figure is the data.'],
  ['vessel', 'CHANGE MAP', 'Twelve weeks of change, in radial millimetres, painted on the body.'],
  ['dashboard', 'COMMAND CENTER', 'Today at a glance — rings, streaks, and the next best action.'],
  ['weight', 'THE VOYAGE', 'Trend, pace, and a projected arrival that updates itself.'],
  ['workouts', 'PROGRESSION', 'Every lift tracked, with the next target already computed.'],
  ['meals', 'FUEL', 'Macros, adaptive TDEE, and a coach that estimates from plain language.'],
  ['vitals', 'READINESS', 'Sleep, HRV, and resting heart rate, read as one number.'],
  ['coach', 'THE ROSTER', 'Twenty coaches. Ask one anything — it can log for you.'],
  ['remedies', 'THE APOTHECARY', '364 remedies from 84 traditions, graded against modern evidence.'],
];

export function startDemo() {
  const real = State;                      // put this back on exit
  let i = 0, timer = 0, alive = true;

  const chrome = document.createElement('div');
  chrome.className = 'demo-chrome';
  chrome.innerHTML = `<div class="demo-tag">
      <span class="demo-dot"></span><b class="demo-title"></b>
      <span class="demo-sub"></span>
    </div>
    <div class="demo-exit">press any key to exit demo</div>
    <div class="demo-bar"><i></i></div>`;
  document.body.append(chrome);
  document.body.classList.add('demo-on');

  const title = chrome.querySelector('.demo-title');
  const sub = chrome.querySelector('.demo-sub');
  const bar = chrome.querySelector('.demo-bar i');

  function stop() {
    if (!alive) return;
    alive = false;
    clearTimeout(timer);
    chrome.remove();
    document.body.classList.remove('demo-on');
    removeEventListener('keydown', stop);
    removeEventListener('pointerdown', stop);
    setState(real);
    if (location.hash === '#demo') location.hash = '#dashboard';
    refresh();
  }

  function advance() {
    if (!alive) return;
    const [tab, name, blurb] = STOPS[i % STOPS.length];
    title.textContent = name;
    sub.textContent = blurb;
    bar.style.transition = 'none';
    bar.style.width = '0%';
    // Force a redraw even when the tab is unchanged: two consecutive stops
    // share the vessel tab, and a hash that does not change fires no route.
    showTab(tab, true);
    // The change map is a mode inside VESSEL, not a tab — click its toggle.
    // Two frames: one for the section to mount, one for the button to exist.
    if (name === 'CHANGE MAP') {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const b = document.querySelector('.vessel-mode');
        if (b && !b.classList.contains('on')) b.click();
      }));
    }
    requestAnimationFrame(() => {
      bar.style.transition = 'width 9s linear';
      bar.style.width = '100%';
    });
    i += 1;
    timer = setTimeout(advance, 9000);
  }

  const data = demoData(real);
  addEventListener('keydown', stop);
  addEventListener('pointerdown', stop);
  title.textContent = 'LOADING';
  sub.textContent = 'Building a twelve-week dataset…';
  // #demo is not a tab. Clear it now so the router has somewhere real to land
  // and the exit path does not have to special-case it.
  history.replaceState(null, '', '#vessel');

  // Every derived number comes from the server, computed from this same demo
  // dataset — Navy BF, ACWR, the change map, the whole dashboard. Nothing is
  // re-created in JS, so the demo shows the real engines rather than a mock.
  //
  // Wait for it before the first paint: the section renderers read state.stats
  // directly, and painting demo data with the real file's stats attached
  // throws before anything reaches the screen.
  api('POST', '/vessel/preview', data)
    .then(res => {
      if (!alive) return;
      setState({ ...data, vessel_demo: res.vessel, stats: res.stats });
      advance();
    })
    .catch(() => { stop(); toast('Demo data could not be built.'); });
  return stop;
}
