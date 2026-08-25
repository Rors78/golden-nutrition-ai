// Golden Nutrition AI — SPA core: state, router, helpers.
import { renderDashboard } from './sections/dashboard.js';
import { renderWeight } from './sections/weight.js';
import { renderVitals } from './sections/vitals.js';
import { renderMeals } from './sections/meals.js';
import { renderWorkouts } from './sections/workouts.js';
import { renderSupplements } from './sections/supplements.js';
import { renderDeals } from './sections/deals.js';
import { renderCoach } from './sections/coach.js';
import { renderRemedies } from './sections/remedies.js';
import { renderVessel } from './sections/vessel.js';

const SECTIONS = {
  dashboard: renderDashboard,
  vessel: renderVessel,
  weight: renderWeight,
  vitals: renderVitals,
  meals: renderMeals,
  workouts: renderWorkouts,
  supplements: renderSupplements,
  deals: renderDeals,
  remedies: renderRemedies,
  coach: renderCoach,
};

export let State = null;
const view = document.getElementById('view');

// ── helpers ─────────────────────────────────────────────────────────────
export function el(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  // Adopt into the main document: template content lives in an inert document,
  // and Plotly refuses to render into nodes owned by it.
  return document.adoptNode(t.content.firstElementChild);
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
}

export async function api(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || `${res.status} ${res.statusText}`);
  return json;
}

export function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 2600);
}

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

export function countUp(node, target, suffix = '') {
  const end = Number(target) || 0;
  if (reducedMotion || Math.abs(end) < 1) { node.textContent = `${target}${suffix}`; return; }
  const dur = 600, t0 = performance.now();
  const isFloat = !Number.isInteger(end);
  (function tick(now) {
    const p = Math.min(1, (now - t0) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    node.textContent = `${(end * eased).toFixed(isFloat ? 1 : 0)}${suffix}`;
    if (p < 1) requestAnimationFrame(tick);
  })(t0);
}

export function metric(label, value, { suffix = '', small = '', delta = null } = {}) {
  const card = el(`<div class="card metric">
    <div class="label">${esc(label)}</div>
    <div class="value"><span class="count"></span>${small ? ` <small>${esc(small)}</small>` : ''}</div>
    ${delta ? `<div class="delta ${delta.cls}">${esc(delta.text)}</div>` : ''}
  </div>`);
  countUp(card.querySelector('.count'), value, suffix);
  return card;
}

// Signature element: the barbell progress bar
export function barbell(label, current, goal, unit) {
  const pct = goal > 0 ? Math.min(100, current / goal * 100) : 0;
  const bar = el(`<div class="barbell">
    <div class="bb-head"><span>${esc(label)}</span>
      <span class="bb-num">${esc(current)}${esc(unit)} / ${esc(goal)}${esc(unit)} · ${pct.toFixed(0)}%</span></div>
    <div class="bb-track">
      <div class="bb-fill" style="width:0%"></div>
      <div class="bb-plates" style="left:0%"><i></i><i></i><i></i></div>
    </div>
  </div>`);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    bar.querySelector('.bb-fill').style.width = `${pct}%`;
    bar.querySelector('.bb-plates').style.left = `${pct}%`;
  }));
  return bar;
}

// Shared Plotly styling: recessive grid, brand fonts, transparent surfaces.
export const CHART = {
  gold: '#f2c14e', steel: '#6ea8d8', good: '#7ee081',
  layout(extra = {}) {
    return {
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'IBM Plex Mono, monospace', size: 11, color: '#aab2bd' },
      margin: { l: 44, r: 16, t: 8, b: 36 },
      xaxis: { gridcolor: 'rgba(110,118,131,.16)', zeroline: false, fixedrange: true },
      yaxis: { gridcolor: 'rgba(110,118,131,.16)', zeroline: false, fixedrange: true },
      hoverlabel: { bgcolor: '#1f242b', bordercolor: '#272d36',
                    font: { family: 'IBM Plex Mono, monospace', size: 12, color: '#f2f4f6' } },
      showlegend: false,
      ...extra,
    };
  },
  config: { displayModeBar: false, responsive: true },
};

// Fitness-app progress ring: animated SVG stroke with a big number inside.
export function ring(label, current, goal, unit, { size = 150, steel = false } = {}) {
  const pct = goal > 0 ? Math.min(1, current / goal) : 0;
  const stroke = Math.round(size * 0.075);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const node = el(`<div class="ring${steel ? ' steel' : ''}" role="img"
      aria-label="${esc(label)}: ${esc(current)}${esc(unit)} of ${esc(goal)}${esc(unit)}">
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <circle class="track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"/>
      <circle class="fill" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"
        stroke-dasharray="${c}" stroke-dashoffset="${c}"/>
    </svg>
    <div class="ring-center"><div>
      <div class="ring-num"><span class="count"></span><small style="font-size:.5em"> ${esc(unit)}</small></div>
      <div class="ring-sub">${esc(label)} · ${esc(goal)}${esc(unit)} goal</div>
    </div></div>
  </div>`);
  countUp(node.querySelector('.count'), current);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    node.querySelector('.fill').style.strokeDashoffset = `${c * (1 - pct)}`;
  }));
  return node;
}

export function markdown(md) {
  // Minimal renderer for coach summaries: headings, bold, lists, paragraphs.
  const blocks = esc(md).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').split(/\n{2,}/);
  return blocks.map(b => {
    const t = b.trim();
    if (/^#{1,3} /.test(t)) return `<h3>${t.replace(/^#+ /, '')}</h3>`;
    if (/^[-*] /m.test(t)) {
      const items = t.split('\n').filter(l => /^[-*] /.test(l))
        .map(l => `<li>${l.replace(/^[-*] /, '')}</li>`).join('');
      return `<ul>${items}</ul>`;
    }
    return `<p>${t.replace(/\n/g, '<br>')}</p>`;
  }).join('');
}

// Generic editable/deletable row actions used by every section's table.
export function rowActions(kind, idx, { onEdit } = {}) {
  const td = el(`<td class="row-actions">
    ${onEdit ? '<button class="icon-btn" title="Edit" aria-label="Edit row">✎</button>' : ''}
    <button class="icon-btn danger" title="Delete" aria-label="Delete row">✕</button>
  </td>`);
  if (onEdit) td.querySelector('.icon-btn:not(.danger)').addEventListener('click', onEdit);
  td.querySelector('.danger').addEventListener('click', async () => {
    try {
      await api('DELETE', `/entry/${kind}/${idx}`);
      toast('Deleted');
      await refresh();
    } catch (e) { toast(e.message); }
  });
  return td;
}

// ── router + state ──────────────────────────────────────────────────────
function currentTab() {
  const h = location.hash.replace('#', '');
  return SECTIONS[h] ? h : 'dashboard';
}

// Swap the in-memory state and redraw, without touching the server. Demo mode
// uses this to show a full dataset on an install that has logged nothing —
// the data file is never written, so exiting restores the real state.
export function setState(next) {
  State = next;
  render();
}

// Navigate to a tab programmatically. The hash is the router's source of
// truth, so go through it rather than calling a renderer directly.
export function showTab(name, force = false) {
  if (force || location.hash.replace('#', '') === name) {
    if (location.hash.replace('#', '') !== name) {
      // Set the hash without waiting for the hashchange round-trip, so a
      // caller that needs the section mounted this frame gets it.
      history.replaceState(null, '', `#${name}`);
    }
    render();
  } else location.hash = name;
}

export async function refresh() {
  State = await api('GET', '/state');
  const badge = document.getElementById('ai-badge');
  badge.hidden = false;
  if (State.ai_backend) {
    badge.textContent = `AI: ${State.ai_backend}`;
    badge.classList.remove('off');
  } else {
    badge.textContent = 'AI: not configured';
    badge.classList.add('off');
  }
  if (State.recovery_note) toast(State.recovery_note);
  render();
}

function render() {
  const tab = currentTab();
  document.querySelectorAll('.tabs button').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
    b.setAttribute('aria-selected', b.dataset.tab === tab);
  });
  view.innerHTML = '';
  // Section renderers read State.stats directly. Guard rather than let each
  // one crash: #demo is not a tab, so landing on it routes here before the
  // demo dataset has been derived.
  if (!State || !State.stats) return;
  SECTIONS[tab](view, State);
}

document.querySelectorAll('.tabs button').forEach(b =>
  b.addEventListener('click', () => { location.hash = b.dataset.tab; }));
addEventListener('hashchange', render);

// ── profile dialog ──────────────────────────────────────────────────────
const dialog = document.getElementById('profile-dialog');
const form = document.getElementById('profile-form');
// ── live sync: an open tab stays current on its own ─────────────────────
// Without this a tab left open is frozen: the day rolls over, entries land
// from the phone, a coach action lands in another window, and the screen
// never notices. Polls a small endpoint and only re-fetches state when the
// data file has actually changed.
(function initLiveSync() {
  const SLOW = 30000, FAST = 6000;
  let rev = null, day = null, code = null, timer = 0, busy = false;

  // The sentinel computes these and pushes them to a phone. On this machine
  // there is no ntfy topic, so they reach nobody — and a screen that is
  // already open is the obvious second place to say it. Same pure function
  // server-side, so the two can never disagree.
  function paintAlerts(list) {
    let bar = document.getElementById('alert-bar');
    if (!list.length) { bar?.remove(); return; }
    if (!bar) {
      bar = el(`<div id="alert-bar" class="alert-bar"></div>`);
      document.querySelector('.tabs').after(bar);
    }
    const text = list.join(' · ');
    if (bar.dataset.text === text) return;   // don't re-paint identical content
    bar.dataset.text = text;
    bar.innerHTML = '';
    bar.append(el(`<div class="ab-in"><span class="ab-dot"></span>
      <span class="ab-text">${esc(text)}</span></div>`));
  }

  async function beat(force = false) {
    // Never poll a hidden tab on the interval — a background tab hammering the
    // server for hours is the same battery complaint as an unpaused canvas
    // loop. `force` is for the first beat, which must land even when the tab
    // is restored in the background: otherwise the alert bar never appears
    // until the user happens to focus the window.
    if (busy) return;
    if (document.hidden && !force) return;
    busy = true;
    try {
      const p = await api('GET', '/pulse');
      // A deploy landed: the JS this tab is running is no longer the JS the
      // server ships. Data-refresh can't fix that — only a reload can, and
      // waiting for a human to press F5 is how a fix "doesn't work" on a
      // screen that has been open since before it shipped. This check runs
      // even while the demo loop is on — a floor-model screen spends its
      // life in the demo, and skipping it there would strand exactly the
      // screen this exists for.
      if (code !== null && p.code_rev && p.code_rev !== code) { location.reload(); return; }
      if (p.code_rev) code = p.code_rev;
      // The demo is showing synthetic state; repainting real data or alerts
      // over it would tear the illusion. Data sync resumes on exit.
      if (document.body.classList.contains('demo-on')) return;
      // Day rollover: "today" is now a different day, so every today-scoped
      // panel on screen is stale even though no data changed.
      if (day && p.server_date !== day) { day = p.server_date; await refresh(); }
      else if (rev !== null && p.rev !== rev) await refresh();
      rev = p.rev; day = p.server_date;
      window.LivePulse = p;
      paintAlerts(p.alerts || []);
    } catch { /* offline or server restarting — try again next beat */ }
    finally { busy = false; }
  }

  function schedule() {
    clearInterval(timer);
    // Poll faster while a live session is running: the rest timer and set
    // dots are the one place a few seconds of staleness is visible.
    const live = !!localStorage.getItem('gna-live-session');
    timer = setInterval(beat, live ? FAST : SLOW);
  }

  document.addEventListener('visibilitychange', () => { if (!document.hidden) beat(); });
  // Another tab logged something — react immediately rather than waiting.
  addEventListener('storage', ev => { if (ev.key === 'gna-live-session') schedule(); });
  schedule();
  beat(true);
})();

// ── demo mode: the shop-window loop ─────────────────────────────────────
// Lazily imported so the demo dataset never loads for normal use.
let stopDemo = null;
export async function enterDemo() {
  if (stopDemo) return;
  // The initial refresh() is fire-and-forget at the bottom of this file, and
  // `load` beats it — so State can still be null here. The demo captures the
  // real state to restore on exit, and capturing null loses it.
  if (!State) await refresh().catch(() => {});
  const { startDemo } = await import('./sections/demo.js');
  // The demo exits through its own key/click listeners, so it reports its
  // exit back — otherwise stopDemo goes stale and the loop can run only once.
  stopDemo = startDemo(() => { stopDemo = null; });
}
if (location.hash === '#demo') addEventListener('load', enterDemo);
addEventListener('hashchange', () => {
  if (location.hash === '#demo') enterDemo();
});

// ── floor model: the switch that makes this the display unit ────────────
// Like a TV in a shop: the demo loop starts on its own and comes back after
// the customer walks away. Interaction exits the demo as always; ~90 s of
// idle brings it back. Persisted per-browser, so an opted-in screen stays a
// display unit across reloads without ever touching the data file.
(function initFloorModel() {
  const KEY = 'gna-floor-model';
  const link = document.getElementById('floor-toggle');
  if (!link) return;
  const IDLE = 90000, BOOT = 2500;
  let timer = 0;
  // Default ON: this install is a display unit until someone says otherwise.
  // The demo costs nothing (in-memory swap only) and any key or click exits,
  // so the surprising state is a dead screen, not a running one.
  const on = () => localStorage.getItem(KEY) !== '0';

  function label() {
    link.textContent = `floor model: ${on() ? 'on' : 'off'}`;
    link.classList.toggle('on', on());
  }
  function arm(delay) {
    clearTimeout(timer);
    if (!on()) return;
    timer = setTimeout(() => {
      // A hidden tab must not start a canvas loop; re-arm and wait.
      if (document.hidden) { arm(IDLE); return; }
      if (!document.body.classList.contains('demo-on')) enterDemo();
    }, delay);
  }
  // Any interaction restarts the countdown — including the very key or click
  // that exits a running demo, which is what makes the loop come back.
  ['pointerdown', 'keydown'].forEach(ev =>
    addEventListener(ev, () => arm(IDLE), true));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) arm(IDLE);
  });
  link.addEventListener('click', ev => {
    ev.preventDefault();
    localStorage.setItem(KEY, on() ? '0' : '1');
    label();
    if (on()) { toast('Floor model on — the demo loops whenever the screen is idle.'); arm(BOOT); }
    else { toast('Floor model off.'); clearTimeout(timer); }
  });
  label();
  arm(BOOT);
})();

// ── quick log: one box, reachable from every tab ────────────────────────
// The analytics are all dormant until data exists, and what kept the file
// empty was that every entry cost a tab change and a form. Common shapes are
// parsed server-side by regex — instant, offline, no API key — with AI only
// as the fallback for prose.
(function initQuickLog() {
  const form = document.getElementById('quick-form');
  const input = document.getElementById('quick-input');
  if (!form) return;
  form.addEventListener('submit', async ev => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.disabled = true;
    try {
      const res = await api('POST', '/quick', { text });
      input.value = '';
      toast(res.message);
      await refresh();
    } catch (e) { toast(e.message); }
    finally { input.disabled = false; input.focus(); }
  });
  // "/" focuses the box from anywhere, unless you are already typing.
  document.addEventListener('keydown', ev => {
    if (ev.key !== '/' || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) return;
    ev.preventDefault();
    input.focus();
  });

  // ── repeat chips: most of real logging is the same meals again ────────
  // Focus the box and the recent distinct meals appear as one-tap chips,
  // macros included. Tapping one re-logs it for today through the ordinary
  // meals endpoint — no parsing, no AI, no typing the same breakfast twice.
  const chips = document.getElementById('quick-chips');
  function recentMeals() {
    const seen = new Map();
    for (const m of [...(State?.meals || [])].reverse()) {
      const key = (m.name || '').trim().toLowerCase();
      if (key && !seen.has(key)) seen.set(key, m);
      if (seen.size >= 6) break;
    }
    return [...seen.values()];
  }
  function paintChips() {
    const rm = recentMeals();
    chips.innerHTML = '';
    if (!rm.length || input.value.trim()) { chips.hidden = true; return; }
    chips.append(el('<span class="qc-lab">again today:</span>'));
    for (const m of rm) {
      const b = el(`<button type="button" class="qc-chip">${esc(m.name)}
        <i>${Math.round(m.protein || 0)}p · ${Math.round(m.calories || 0)} kcal</i></button>`);
      b.addEventListener('click', async () => {
        chips.hidden = true;
        try {
          await api('POST', '/meals', {
            name: m.name, protein: m.protein, calories: m.calories,
            carbs: m.carbs, fat: m.fat, fiber: m.fiber,
          });
          toast(`${m.name} — logged again`);
          await refresh();
        } catch (e) { toast(e.message); }
      });
      chips.append(b);
    }
    chips.hidden = false;
  }
  input.addEventListener('focus', paintChips);
  input.addEventListener('input', paintChips);
  // Delay so a tap on a chip lands before the panel hides under it.
  input.addEventListener('blur', () => setTimeout(() => { chips.hidden = true; }, 250));
})();

document.getElementById('profile-btn').addEventListener('click', () => {
  const p = State?.profile || {};
  for (const f of form.elements) if (f.name) f.value = p[f.name] ?? '';
  dialog.showModal();
});
document.getElementById('profile-cancel').addEventListener('click', () => dialog.close());
form.addEventListener('submit', async () => {
  const body = Object.fromEntries(new FormData(form).entries());
  try { await api('POST', '/profile', body); toast('Profile saved'); await refresh(); }
  catch (e) { toast(e.message); }
});

// ── 3D brand plate (Three.js) — a machined gold weight plate ────────────
function initBrandPlate() {
  const canvas = document.getElementById('brand-3d');
  if (!canvas || typeof THREE === 'undefined') return;
  try {
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(52, 52, false);
    const scene = new THREE.Scene();
    const cam = new THREE.PerspectiveCamera(32, 1, 0.1, 10);
    cam.position.z = 3.4;

    const gold = new THREE.MeshStandardMaterial({ color: 0xf2c14e, metalness: 0.85, roughness: 0.32 });
    const goldBright = new THREE.MeshStandardMaterial({ color: 0xffd875, metalness: 0.9, roughness: 0.22 });
    const dark = new THREE.MeshStandardMaterial({ color: 0x171a1f, metalness: 0.6, roughness: 0.5 });

    const plate = new THREE.Group();
    plate.add(new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 0.22, 64), gold));
    const rim = new THREE.Mesh(new THREE.TorusGeometry(1, 0.09, 20, 64), goldBright);
    rim.rotation.x = Math.PI / 2;
    plate.add(rim);
    const groove = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.03, 12, 64), dark);
    groove.rotation.x = Math.PI / 2;
    groove.position.y = 0.11;
    plate.add(groove);
    plate.add(new THREE.Mesh(new THREE.CylinderGeometry(0.26, 0.26, 0.3, 48), dark));
    plate.rotation.x = 1.05;
    scene.add(plate);

    scene.add(new THREE.AmbientLight(0xfff6e0, 0.55));
    const key = new THREE.DirectionalLight(0xfff2cc, 1.4);
    key.position.set(2, 3, 4);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x6ea8d8, 0.35);
    fill.position.set(-3, -1, 2);
    scene.add(fill);

    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    (function spin() {
      plate.rotation.y += 0.012;
      renderer.render(scene, cam);
      if (!reduced) requestAnimationFrame(spin);
    })();
  } catch { /* WebGL unavailable — the CSS plate underneath still shows */ }
}
initBrandPlate();

// PWA: installable app + offline shell
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// Import history from another app's CSV export (footer)
const importDialog = document.getElementById('import-dialog');
document.getElementById('import-btn')?.addEventListener('click', () => importDialog.showModal());
document.getElementById('import-go')?.addEventListener('click', async () => {
  const file = document.getElementById('import-file').files[0];
  if (!file) { toast('Pick a CSV file first.'); return; }
  const btn = document.getElementById('import-go');
  btn.disabled = true;
  try {
    const res = await api('POST', '/import/csv', {
      kind: document.getElementById('import-kind').value,
      csv: await file.text(),
    });
    importDialog.close();
    toast(`Imported ${res.imported} · skipped ${res.skipped} (duplicates/unparsable)`);
    await refresh();
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    document.getElementById('import-file').value = '';
  }
});

// System pulse (footer): is the machinery guarding your data still running?
const pulseDialog = document.getElementById('pulse-dialog');
document.getElementById('pulse-btn')?.addEventListener('click', async () => {
  const body = pulseDialog.querySelector('.pulse-body');
  body.innerHTML = '<p style="margin:10px 0"><span class="spinner"></span>Checking…</p>';
  pulseDialog.showModal();
  try {
    const s = await api('GET', '/system');
    const fmtSize = b => b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`;
    const row = (label, val) => `<div style="display:flex;gap:14px;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--line);padding:7px 0">
      <span style="color:var(--muted);font-size:12px;white-space:nowrap">${label}</span>
      <span style="text-align:right;font-family:var(--font-mono);font-size:12px">${val}</span></div>`;
    const c = s.data_file.counts;
    body.innerHTML = `
      ${s.warnings.map(w => `<div class="callout warn" style="margin:10px 0">${esc(w)}</div>`).join('')}
      ${row('AI backend', esc(s.ai_backend || 'none'))}
      ${row('Server', esc(s.server))}
      ${row('Runtime', esc(s.platform))}
      ${row('Data file', `${fmtSize(s.data_file.bytes)} · updated ${esc((s.data_file.modified || 'never').replace('T', ' '))}`)}
      ${row('Entries', `${c.meals} meals · ${c.workouts} workouts · ${c.weights} weigh-ins · ${c.vitals} vitals`)}
      ${row('Backups', s.backups.count
        ? `${s.backups.count} kept · newest ${s.backups.age_days}d ago`
        : 'none yet')}
      ${row("Today's briefing", s.briefing_date === new Date().toISOString().slice(0, 10)
        ? '<span style="color:var(--good)">delivered</span>' : 'not yet')}
      ${row('Push channel', s.push_channel
        ? '<span style="color:var(--good)">configured</span>'
        : '<span style="color:var(--warn)">none — jobs cannot reach you</span>')}
      ${row('Last logged', s.days_since_entry == null ? 'never'
        : s.days_since_entry === 0 ? '<span style="color:var(--good)">today</span>'
        : `${s.days_since_entry}d ago`)}`;
  } catch (e) {
    body.innerHTML = '';
    toast(e.message);
  }
});

// Restore from a full-backup JSON (footer). The server snapshots the current
// file before replacing it, so a bad pick is recoverable.
document.getElementById('restore-input')?.addEventListener('change', async ev => {
  const file = ev.target.files[0];
  ev.target.value = '';
  if (!file) return;
  try {
    const body = JSON.parse(await file.text());
    const res = await api('POST', '/import/backup', body);
    const counts = `${res.meals} meals, ${res.workouts} workouts, ${res.weights} weigh-ins`;
    await refresh();
    const missing = res.secrets_need_reentry || [];
    if (missing.length) {
      // Restores happen after disk failures and migrations — exactly when
      // nobody audits a settings panel. This is a step in the flow, not amber
      // on a badge that gets read next week.
      const names = { ntfy_topic: 'notification topic (Vitals tab)' };
      alert(`Restored: ${counts}\n\n`
        + `${missing.length} machine-local setting needs re-entry — backups do `
        + `not carry credentials:\n\n`
        + missing.map(k => `  • ${names[k] || k}`).join('\n')
        + `\n\nUntil it is set, the sentinel, briefing, and price-watch jobs `
        + `have nowhere to push.`);
    } else {
      toast(`Restored: ${counts}`);
    }
  } catch (e) {
    toast(e.message.startsWith('Unexpected') ? 'That file is not valid JSON.' : e.message);
  }
});

// ── command palette: Ctrl+K, one box over the whole machine ─────────────
// Ten tabs, twenty coaches, ~350 remedies, a graded supplement library —
// and until now the only way in was clicking. The palette searches all of
// it: static rows (tabs, actions) filter locally, everything else comes
// from /api/search. Selecting acts: tabs navigate, coaches are hired,
// remedies land in the Apothecary's search box, meals land in the quick bar.
(function initPalette() {
  let overlay = null, inp = null, list = null, rows = [], hot = 0, seq = 0;

  const staticRows = () => [
    ...[...document.querySelectorAll('.tabs button')].map(b => ({
      group: 'go to', label: b.textContent.trim(),
      run: () => { location.hash = b.dataset.tab; } })),
    { group: 'do', label: 'Start demo mode', run: () => { location.hash = '#demo'; } },
    { group: 'do', label: 'Open profile', run: () => document.getElementById('profile-btn')?.click() },
    { group: 'do', label: 'Focus quick log', run: () => document.getElementById('quick-input')?.focus() },
    { group: 'do', label: 'Open lift view', run: () => { location.hash = 'workouts'; } },
  ];

  function close() { overlay?.remove(); overlay = null; }

  function paintRows() {
    list.innerHTML = '';
    rows.forEach((r, i) => {
      const div = el(`<div class="pal-row${i === hot ? ' hot' : ''}">
        <span class="pal-group">${esc(r.group)}</span>
        <span class="pal-label">${esc(r.label)}</span>
        ${r.sub ? `<span class="pal-sub">${esc(r.sub)}</span>` : ''}</div>`);
      div.addEventListener('pointerdown', ev => { ev.preventDefault(); pick(i); });
      div.addEventListener('pointermove', () => {
        if (hot !== i) { hot = i; paintRows(); }
      });
      list.append(div);
    });
    if (!rows.length) list.append(el('<div class="pal-empty">Nothing matches. The Apothecary, coaches and supplements need two letters.</div>'));
  }

  function pick(i) {
    const r = rows[i];
    if (!r) return;
    close();
    r.run();
  }

  async function query(q) {
    const mine = ++seq;
    const ql = q.trim().toLowerCase();
    rows = staticRows().filter(r => !ql || r.label.toLowerCase().includes(ql));
    hot = 0;
    paintRows();
    if (ql.length < 2) return;
    try {
      const res = await api('GET', `/search?q=${encodeURIComponent(ql)}`);
      if (mine !== seq || !overlay) return;   // a newer keystroke owns the box
      for (const c of res.coaches) rows.push({
        group: 'hire coach', label: c.name, sub: c.goal,
        run: async () => {
          try { await api('POST', '/coach/select', { id: c.id }); await refresh(); }
          catch (e) { toast(e.message); }
          location.hash = 'coach';
        } });
      for (const r of res.remedies) rows.push({
        group: 'apothecary', label: r.name, sub: r.traditions.join(' · '),
        run: () => {
          sessionStorage.setItem('gna-prefill-remedies', r.name);
          if (location.hash === '#remedies') render(); else location.hash = 'remedies';
        } });
      for (const k of res.supplements) rows.push({
        group: 'supplement', label: k.name, sub: k.verdict,
        run: () => { location.hash = 'supplements'; } });
      for (const n of res.meals) rows.push({
        group: 'log again', label: n, sub: 'from your history',
        run: () => {
          const qi = document.getElementById('quick-input');
          qi.value = n; qi.focus();
        } });
      for (const n of res.exercises) rows.push({
        group: 'exercise', label: n, sub: 'in your log',
        run: () => { location.hash = 'workouts'; } });
      paintRows();
    } catch { /* offline — static rows still work */ }
  }

  function open() {
    if (overlay) return;
    overlay = el(`<div class="pal-overlay">
      <div class="pal-box">
        <input class="pal-input" type="text" placeholder="Search everything — tabs, coaches, remedies, your log…"
               autocomplete="off" spellcheck="false">
        <div class="pal-list"></div>
        <div class="pal-hint">↑↓ move · Enter select · Esc close</div>
      </div></div>`);
    inp = overlay.querySelector('.pal-input');
    list = overlay.querySelector('.pal-list');
    overlay.addEventListener('pointerdown', ev => { if (ev.target === overlay) close(); });
    inp.addEventListener('input', () => query(inp.value));
    inp.addEventListener('keydown', ev => {
      if (ev.key === 'ArrowDown') { ev.preventDefault(); hot = Math.min(hot + 1, rows.length - 1); paintRows(); }
      else if (ev.key === 'ArrowUp') { ev.preventDefault(); hot = Math.max(hot - 1, 0); paintRows(); }
      else if (ev.key === 'Enter') { ev.preventDefault(); pick(hot); }
      else if (ev.key === 'Escape') { close(); }
    });
    document.body.append(overlay);
    query('');
    inp.focus();
  }

  document.addEventListener('keydown', ev => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
      ev.preventDefault();
      overlay ? close() : open();
    }
  });
  document.getElementById('palette-link')?.addEventListener('click', ev => {
    ev.preventDefault(); open();
  });
})();

// ── voice logging: hold the coach's ear ─────────────────────────────────
(function initVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = document.getElementById('mic-btn');
  if (!SR || !btn) return;
  btn.hidden = false;
  let rec = null;
  btn.addEventListener('click', () => {
    if (rec) { rec.stop(); return; }
    rec = new SR();
    rec.lang = 'en-US';
    rec.interimResults = false;
    btn.classList.add('listening');
    toast('Listening — say what you ate, a weigh-in, or a supplement');
    rec.onresult = async ev => {
      const text = ev.results[0][0].transcript;
      toast(`Heard: "${text}" — logging…`);
      try {
        // Same door as the typed quick bar: regex first (instant, offline),
        // AI only for prose the patterns cannot shape.
        const res = await api('POST', '/quick', { text });
        toast(res.message);
        await refresh();
      } catch (e) { toast(e.message); }
    };
    rec.onerror = ev => { if (ev.error !== 'aborted') toast(`Mic: ${ev.error}`); };
    rec.onend = () => { btn.classList.remove('listening'); rec = null; };
    rec.start();
  });
})();

// 3D machined-plate disc with embossed monogram — coach cards & badges
export function plateDisc(text, { size = 44, tier = 'gold' } = {}) {
  const d = el(`<span class="plate-disc ${tier}" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.32)}px">${esc(text)}</span>`);
  return d;
}

refresh().catch(e => { view.innerHTML = ''; view.append(el(`<div class="empty">Failed to load: ${esc(e.message)}</div>`)); });
