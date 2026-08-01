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

const SECTIONS = {
  dashboard: renderDashboard,
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
  SECTIONS[tab](view, State);
}

document.querySelectorAll('.tabs button').forEach(b =>
  b.addEventListener('click', () => { location.hash = b.dataset.tab; }));
addEventListener('hashchange', render);

// ── profile dialog ──────────────────────────────────────────────────────
const dialog = document.getElementById('profile-dialog');
const form = document.getElementById('profile-form');
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

// Restore from a full-backup JSON (footer). The server snapshots the current
// file before replacing it, so a bad pick is recoverable.
document.getElementById('restore-input')?.addEventListener('change', async ev => {
  const file = ev.target.files[0];
  ev.target.value = '';
  if (!file) return;
  try {
    const body = JSON.parse(await file.text());
    const res = await api('POST', '/import/backup', body);
    toast(`Restored: ${res.meals} meals, ${res.workouts} workouts, ${res.weights} weigh-ins`);
    await refresh();
  } catch (e) {
    toast(e.message.startsWith('Unexpected') ? 'That file is not valid JSON.' : e.message);
  }
});

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
        const res = await api('POST', '/voice', { text });
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
