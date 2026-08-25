// THE FORM GUIDE — how to perform what the program prescribes.
//
// Text comes from the server's exercise KB. The demonstration is drawn
// here: a side-view wireframe lifter in the vessel's own style, looping
// between hand-tuned keyframe poses with the bar path traced in gold.
// It teaches the *shape* of the movement — hinge vs squat, bar over
// midfoot, the bench's shallow J — which is exactly what a stick figure
// shows better than a video full of someone's gym.
import { el, esc, api } from '../app.js';

// Poses are joints in a 0–100 box, side view, lifter facing left.
// a ankle · k knee · h hip · s shoulder · hd head · e elbow · b bar
const ANIM = {
  'Back Squat': {
    poses: [
      { a: [50, 90], k: [50, 72], h: [50, 52], s: [48, 26], hd: [47, 16], e: [55, 30], b: [48, 27] },
      { a: [50, 90], k: [42, 74], h: [59, 70], s: [48, 45], hd: [45, 36], e: [56, 47], b: [48, 46] },
    ],
    note: 'Bar stays over midfoot. Hips travel down and back; chest leads the way up.',
  },
  'Deadlift': {
    poses: [
      { a: [50, 90], k: [46, 74], h: [60, 58], s: [45, 34], hd: [42, 25], e: [45, 52], b: [46, 84] },
      { a: [50, 90], k: [50, 72], h: [51, 52], s: [50, 25], hd: [49, 15], e: [50, 45], b: [50, 62] },
    ],
    note: 'The bar drags up the legs in a straight vertical line. Hips and shoulders rise together.',
  },
  'Bench Press': {
    bench: true,
    poses: [
      { a: [82, 88], k: [72, 66], h: [55, 64], s: [36, 64], hd: [26, 63], e: [42, 52], b: [38, 34] },
      { a: [82, 88], k: [72, 66], h: [55, 64], s: [36, 64], hd: [26, 63], e: [48, 62], b: [41, 56] },
    ],
    note: 'Touch the lower chest, press back over the shoulders — a shallow J, never a straight drop.',
  },
  'Overhead Press': {
    poses: [
      { a: [50, 90], k: [50, 72], h: [50, 52], s: [50, 27], hd: [48, 16], e: [56, 36], b: [47, 30] },
      { a: [50, 90], k: [50, 72], h: [50, 52], s: [50, 27], hd: [51, 17], e: [52, 18], b: [50, 6] },
    ],
    note: 'Vertical bar path past the face; head pushes through at the top, glutes tight throughout.',
  },
  'Barbell Row': {
    poses: [
      { a: [50, 90], k: [48, 74], h: [58, 58], s: [40, 40], hd: [36, 32], e: [41, 52], b: [41, 68] },
      { a: [50, 90], k: [48, 74], h: [58, 58], s: [40, 40], hd: [36, 32], e: [48, 46], b: [42, 50] },
    ],
    note: 'The torso is a table — only the bar moves. Elbows drive back to the hips.',
  },
};

const ease = t => t * t * (3 - 2 * t);

function drawLifter(cx, W, H, anim, t) {
  const u = ease(t <= 0.5 ? t * 2 : 2 - t * 2);   // ping-pong with dwell feel
  const [p0, p1] = anim.poses;
  const P = {};
  for (const k of Object.keys(p0)) {
    P[k] = [
      (p0[k][0] + (p1[k][0] - p0[k][0]) * u) / 100 * W,
      (p0[k][1] + (p1[k][1] - p0[k][1]) * u) / 100 * H,
    ];
  }
  cx.clearRect(0, 0, W, H);

  // floor / bench
  cx.strokeStyle = 'rgba(143,227,242,.18)'; cx.lineWidth = 1.5;
  cx.beginPath(); cx.moveTo(W * 0.1, H * 0.9); cx.lineTo(W * 0.9, H * 0.9); cx.stroke();
  if (anim.bench) {
    cx.strokeStyle = 'rgba(143,227,242,.3)'; cx.lineWidth = 3;
    cx.beginPath(); cx.moveTo(W * 0.18, H * 0.68); cx.lineTo(W * 0.62, H * 0.68); cx.stroke();
    cx.beginPath(); cx.moveTo(W * 0.26, H * 0.68); cx.lineTo(W * 0.26, H * 0.9);
    cx.moveTo(W * 0.56, H * 0.68); cx.lineTo(W * 0.56, H * 0.9); cx.stroke();
  }

  // bar path trace: the whole travel, faint gold
  cx.strokeStyle = 'rgba(242,193,78,.28)'; cx.lineWidth = 2; cx.setLineDash([4, 5]);
  cx.beginPath();
  cx.moveTo(p0.b[0] / 100 * W, p0.b[1] / 100 * H);
  cx.lineTo(p1.b[0] / 100 * W, p1.b[1] / 100 * H);
  cx.stroke(); cx.setLineDash([]);

  // skeleton
  cx.strokeStyle = 'rgba(143,227,242,.85)'; cx.lineWidth = 3; cx.lineCap = 'round';
  for (const [q, r] of [['a', 'k'], ['k', 'h'], ['h', 's'], ['s', 'hd'], ['s', 'e'], ['e', 'b']]) {
    cx.beginPath(); cx.moveTo(...P[q]); cx.lineTo(...P[r]); cx.stroke();
  }
  // head
  cx.beginPath(); cx.arc(P.hd[0], P.hd[1] - 4, 7, 0, 7);
  cx.stroke();
  // joints
  cx.fillStyle = 'rgba(143,227,242,.9)';
  for (const k of ['a', 'k', 'h', 's', 'e']) {
    cx.beginPath(); cx.arc(P[k][0], P[k][1], 3, 0, 7); cx.fill();
  }
  // the bar: gold, glowing, with a plate
  cx.beginPath(); cx.arc(P.b[0], P.b[1], 11, 0, 7);
  cx.strokeStyle = 'rgba(242,193,78,.95)'; cx.lineWidth = 3;
  cx.shadowColor = 'rgba(242,193,78,.7)'; cx.shadowBlur = 12;
  cx.stroke();
  cx.shadowBlur = 0;
  cx.beginPath(); cx.arc(P.b[0], P.b[1], 4, 0, 7);
  cx.fillStyle = 'rgba(255,216,117,.95)'; cx.fill();
}

let closeGuide = null;

export async function openFormGuide(name) {
  closeGuide?.();
  let g;
  try { g = await api('GET', `/exercise/${encodeURIComponent(name)}`); }
  catch { g = null; }

  const box = el(`<div class="fg-overlay">
    <div class="fg-box">
      <div class="fg-head">
        <b>${esc(g?.name || name)}</b>
        <span class="fg-tag">form guide</span>
        <button type="button" class="fg-close" aria-label="Close">✕</button>
      </div>
      <div class="fg-body"></div>
    </div></div>`);
  const body = box.querySelector('.fg-body');

  if (!g) {
    body.append(el(`<p class="fg-none">No guide for this one yet. The library covers the
      barbell lifts and the program's accessories — the movement patterns worth
      coaching in text. For anything else, one session with good eyes beats any card.</p>`));
  } else {
    const anim = ANIM[g.name];
    if (anim) {
      const wrap2 = el(`<div class="fg-anim"><canvas width="420" height="300"></canvas>
        <p class="fg-note">${esc(anim.note)}</p></div>`);
      body.append(wrap2);
      const cv = wrap2.querySelector('canvas');
      const cx = cv.getContext('2d');
      let raf = 0;
      const t0 = performance.now();
      const loop = now => {
        if (!document.contains(cv)) { cancelAnimationFrame(raf); return; }
        drawLifter(cx, cv.width, cv.height, anim, ((now - t0) / 2600) % 1);
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    }
    const section = (title, items) => el(`<div class="fg-sec">
      <span class="fg-lab">${title}</span>
      <ul>${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>`);
    body.append(section('Setup', g.setup));
    body.append(section('Execution', g.cues));
    body.append(el(`<div class="fg-sec"><span class="fg-lab">Common faults</span>
      <ul>${g.faults.map(f => `<li><b>${esc(f.fault)}.</b> ${esc(f.fix)}</li>`).join('')}</ul></div>`));
    body.append(el(`<div class="fg-sec"><span class="fg-lab">Breathing</span>
      <p>${esc(g.breath)}</p></div>`));
    body.append(el(`<div class="fg-sec warn"><span class="fg-lab">Safety</span>
      <p>${esc(g.safety)}</p></div>`));
  }

  const close = () => { box.remove(); removeEventListener('keydown', onKey); closeGuide = null; };
  const onKey = ev => { if (ev.key === 'Escape') close(); };
  box.addEventListener('pointerdown', ev => { if (ev.target === box) close(); });
  box.querySelector('.fg-close').addEventListener('click', close);
  addEventListener('keydown', onKey);
  document.body.append(box);
  closeGuide = close;
}

// Any element carrying data-form="<exercise>" opens the guide — sections
// sprinkle the attribute instead of importing and wiring this module.
document.addEventListener('click', ev => {
  const t = ev.target.closest('[data-form]');
  if (t) { ev.preventDefault(); openFormGuide(t.dataset.form); }
});
