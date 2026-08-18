// VESSEL — the body as the primary object.
//
// This module renders and computes NOTHING. Every number arrives fully derived
// from GET /api/vessel; duplicating any of it here would create a second source
// of truth that diverges silently. If a value looks wrong, fix stats.vessel().
//
// The figure is horizontal ellipses stacked at anatomical landmarks, connected
// by meridian strands whose alpha tracks sin(theta + rotation) so front-facing
// strands burn brighter than back. That single trick reads as a rotating 3D
// scan with no mesh, no library, and no depth buffer.
import { el, esc, api, toast, refresh } from '../app.js';

// Which torso slice belongs to which measurable site, so a tap on a ring knows
// what it is asking for. Only real sites appear here — the interpolated
// shoulder/rib rings are not tappable, because there is nothing to log.
// Change heat: cool where the body came in, warm where it grew. Rendered on
// the ring itself rather than as a chart, because "where did I change" is a
// question about a body and a bar chart cannot answer it.
//
// Scale caps at 6 mm radial — roughly 1.5 in of circumference — which is a
// large real change over a month. Beyond that the colour saturates rather than
// running away, so a mismeasurement cannot paint the whole figure.
const HEAT_CAP_MM = 6;
function heatColor(mm, alpha) {
  const k = Math.min(1, Math.abs(mm) / HEAT_CAP_MM);
  return mm < 0
    ? `rgba(110,180,255,${(0.25 + 0.65 * k) * alpha})`   // came in
    : `rgba(255,140,80,${(0.25 + 0.65 * k) * alpha})`;   // grew
}

const RING_SITES = [
  { y: 9.2, key: 'neck_in', label: 'Neck',
    how: 'Just below the larynx, tape sloping slightly down at the front.' },
  { y: 16.6, key: 'chest_in', label: 'Chest',
    how: 'Across the nipples, arms relaxed, at the end of a normal breath out.' },
  { y: 24.2, key: 'waist_in', label: 'Waist',
    how: 'At the navel, not the narrowest point. Relaxed — do not suck in.' },
  { y: 28.0, key: 'hips_in', label: 'Hips',
    how: 'The widest point of the glutes, feet together.' },
];

const TAU = Math.PI * 2;
const TILT = 0.27;          // ellipse squash: how much "perspective" a ring has
const BODY_IN = 71;         // nominal figure height in inches, for scale only
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

// Only six sites are ever measured (see stats.VESSEL_SITES). shoulder/rib/calf
// are interpolated from neighbours so the figure has a silhouette — they are
// drawn thinner and never claimed as measurements.
function slices(tape, breath) {
  const r = v => (v ? v / Math.PI / 2 : null);
  const neck = r(tape.neck_in), chest = r(tape.chest_in), waist = r(tape.waist_in);
  const hip = r(tape.hips_in), arm = r(tape.arm_in), thigh = r(tape.thigh_in);
  if (!neck || !chest || !waist || !hip) return null;
  const shoulder = chest * 1.17;      // derived, not measured
  const rib = (chest + waist) / 2;    // derived, not measured
  return {
    torso: [
      [0.5, 1.5, 0.35], [3.0, 3.62, 0.55], [6.4, 3.05, 0.45],
      [9.2, neck, 0.70], [12.4, shoulder, 1.0],
      [16.6, chest * breath, 1.0], [20.4, rib * breath, 0.70],
      [24.2, waist, 1.0], [28.0, hip, 1.0], [31.0, hip * 0.93, 0.55],
    ],
    leg: thigh ? [[31, thigh * 1.06], [39, thigh], [46, thigh * 0.70],
                  [52, thigh * 0.62], [61, thigh * 0.40], [67.5, thigh * 0.34]] : [],
    // Arms start at the shoulder ring's height so they read as attached
    // rather than floating beside the torso.
    arm: arm ? [[12.4, arm * 1.30], [18, arm * 1.05], [24, arm * 0.84],
                [30, arm * 0.80], [36, arm * 0.60], [40, arm * 0.46]] : [],
    shoulderR: shoulder, hipR: hip,
  };
}

export function renderVessel(root, state) {
  const wrap = el(`<div class="vessel-wrap">
    <button type="button" class="vessel-mode" data-f="modeBtn" hidden>Change map</button>
    <canvas class="vessel-canvas"></canvas>
    <div class="vessel-hud">
      <div class="vh vh-tl"><span class="vh-lab">Fuel · today</span>
        <b class="vh-big" data-f="kcal">—</b><small data-f="kcalSub">—</small></div>
      <div class="vh vh-bl"><span class="vh-lab">Protein</span>
        <b class="vh-mid" data-f="prot">—</b><small data-f="protSub">—</small></div>
      <div class="vh vh-tr"><span class="vh-lab">Structural load</span>
        <b class="vh-big" data-f="acr">—</b><small data-f="acrSub">—</small></div>
      <div class="vh vh-br"><span class="vh-lab">Composition</span>
        <b class="vh-mid" data-f="bf">—</b><small data-f="bfSub">—</small></div>
      <div class="vh vh-b"><span class="vh-lab" data-f="voyLab">Voyage</span>
        <b class="vh-voy" data-f="voy">—</b><small data-f="eta">—</small></div>
      <div class="vessel-state" data-f="stateTag"></div>
      <div class="vessel-hint" data-f="hint"></div>
      <div class="vessel-change" data-f="changeBox"></div>
    </div>
  </div>`);
  root.append(wrap);

  const cv = wrap.querySelector('canvas'), cx = cv.getContext('2d');
  const F = {};
  wrap.querySelectorAll('[data-f]').forEach(n => { F[n.dataset.f] = n; });

  let W = 0, H = 0, raf = 0, t0 = performance.now();
  let V = null;                       // the payload; null until first fetch
  let hot = null;                     // ring under the pointer, if any
  let showChange = false;             // change-map overlay on/off
  const D = { kcal: 0, prot: 0, acr: 0, bf: 0 };   // eased display values

  function resize() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    W = wrap.clientWidth; H = Math.max(420, Math.min(innerHeight * 0.72, 760));
    cv.style.width = W + 'px'; cv.style.height = H + 'px';
    cv.width = W * dpr; cv.height = H * dpr;
    cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function field() {
    cx.fillStyle = '#04060a'; cx.fillRect(0, 0, W, H);
    const g = cx.createRadialGradient(W / 2, H * 0.46, 0, W / 2, H * 0.46, Math.max(W, H) * 0.62);
    g.addColorStop(0, 'rgba(16,34,46,.5)'); g.addColorStop(1, 'rgba(4,6,10,0)');
    cx.fillStyle = g; cx.fillRect(0, 0, W, H);
    cx.strokeStyle = 'rgba(143,227,242,.028)'; cx.lineWidth = 1;
    for (let x = (W / 2) % 64; x < W; x += 64) { cx.beginPath(); cx.moveTo(x, 0); cx.lineTo(x, H); cx.stroke(); }
    for (let y = (H / 2) % 64; y < H; y += 64) { cx.beginPath(); cx.moveTo(0, y); cx.lineTo(W, y); cx.stroke(); }
  }

  function stack(pts, ox, cxp, ppi, rot, alpha, shellK) {
    const proj = [];
    for (const [yi, ri, wg = 1] of pts) {
      if (!ri) continue;
      const py = yi * ppi, rp = ri * ppi;
      if (shellK > 0.001) {
        cx.beginPath();
        cx.ellipse(cxp + ox, py, rp * (1 + shellK), rp * (1 + shellK) * TILT, 0, 0, TAU);
        cx.strokeStyle = `rgba(143,227,242,${0.05 * wg * alpha})`;
        cx.lineWidth = 1; cx.stroke();
      }
      cx.beginPath();
      cx.ellipse(cxp + ox, py, rp, rp * TILT, 0, 0, TAU);
      cx.strokeStyle = `rgba(143,227,242,${(0.3 * wg + 0.1) * alpha})`;
      cx.lineWidth = 0.9 * wg + 0.35; cx.stroke();
      proj.push({ py, rp });
    }
    const N = W < 820 ? 10 : 22;
    for (let m = 0; m < N; m++) {
      const a = rot + m / N * TAU, front = Math.sin(a);
      if (front < -0.35) continue;
      const al = Math.min(1, Math.max(0, (front + 0.35) / 1.35));
      cx.beginPath();
      proj.forEach((p, i) => {
        const x = cxp + ox + Math.cos(a) * p.rp, y = p.py + Math.sin(a) * p.rp * TILT;
        i ? cx.lineTo(x, y) : cx.moveTo(x, y);
      });
      cx.strokeStyle = `rgba(143,227,242,${(0.028 + 0.12 * al) * alpha})`;
      cx.lineWidth = 0.65; cx.stroke();
    }
  }

  // Single source of truth for the figure transform. Both the renderer and the
  // hit-test read it, so a tap can never land somewhere the ring is not drawn.
  function geom() {
    const ppi = Math.min(H * 0.92 / BODY_IN, W * 0.34 / 12);
    return { ppi, cxp: W / 2, top: H / 2 - BODY_IN * ppi * 0.5 };
  }

  // Which tappable ring is under this point, if any.
  function ringAt(px, py) {
    if (!V || !V.body.have) return null;
    const { ppi, cxp, top } = geom();
    const tape = V.body.tape_in || {};
    let best = null, bestD = 26;   // generous target: fingers, not cursors
    for (const site of RING_SITES) {
      const ry = top + site.y * ppi;
      const c = tape[site.key];
      const rp = c ? (c / Math.PI / 2) * ppi : 3 * ppi;
      // distance to the ellipse band, not its centre
      const dx = Math.abs(px - cxp), dy = Math.abs(py - ry);
      const d = Math.hypot(Math.max(0, dx - rp), dy / TILT * 0.55);
      if (d < bestD) { bestD = d; best = site; }
    }
    return best;
  }

  function figure(t) {
    const b = V.body;
    const sl = slices(b.tape_in || {}, reduced ? 1 : 1 + 0.014 * Math.sin(t * 1.55));
    if (!sl) return;
    // Opacity IS the degradation ladder: a generic figure must not look like
    // a measured one.
    const alpha = b.fidelity === 'full' ? 1 : b.fidelity === 'estimated' ? 0.65 : 0.45;
    // Scale to fill the frame vertically; the figure is the primary object,
    // not a diagram sitting in the middle of one.
    const { ppi, cxp, top } = geom();
    const rot = reduced ? 0.7 : t * 0.30;
    const shellK = V.composition.have
      ? Math.min(1, Math.max(0, (V.composition.bf_pct - 8) / 27)) * 0.20 : 0;

    cx.save();
    cx.translate(0, top);
    cx.globalCompositeOperation = 'lighter';
    for (const side of [-1, 1]) {
      stack(sl.leg, side * sl.hipR * ppi * 0.46, cxp, ppi, rot, alpha * 0.72, shellK * 0.8);
      stack(sl.arm, side * sl.shoulderR * ppi * 0.98, cxp, ppi, rot, alpha * 0.62, shellK * 0.7);
    }
    stack(sl.torso, 0, cxp, ppi, rot, alpha, shellK);

    // ── change map: heat on the sites that actually moved ──
    if (showChange && V.change?.has_data) {
      for (const s of V.change.sites) {
        if (!s.significant) continue;
        const site = RING_SITES.find(r => r.key === s.site);
        if (!site) continue;
        const c = (b.tape_in || {})[s.site];
        if (!c) continue;
        const rp = (c / Math.PI / 2) * ppi;
        const py = site.y * ppi;
        // two passes: a soft halo for presence, a hard ring for the reading
        cx.beginPath();
        cx.ellipse(cxp, py, rp * 1.14, rp * 1.14 * TILT, 0, 0, TAU);
        cx.strokeStyle = heatColor(s.delta_mm, 0.45);
        cx.lineWidth = 9; cx.stroke();
        cx.beginPath();
        cx.ellipse(cxp, py, rp, rp * TILT, 0, 0, TAU);
        cx.strokeStyle = heatColor(s.delta_mm, 1);
        cx.lineWidth = 2.4; cx.stroke();
      }
    }

    // the ring under the pointer lights up, so the target is legible before
    // the tap rather than discovered by it
    if (hot) {
      const c = (b.tape_in || {})[hot.key];
      const rp = c ? (c / Math.PI / 2) * ppi : 3 * ppi;
      cx.beginPath();
      cx.ellipse(cxp, hot.y * ppi, rp, rp * TILT, 0, 0, TAU);
      cx.strokeStyle = 'rgba(242,166,60,.9)'; cx.lineWidth = 2; cx.stroke();
    }
    cx.beginPath();
    cx.moveTo(cxp, 9.2 * ppi); cx.lineTo(cxp, 31 * ppi);
    cx.strokeStyle = `rgba(242,166,60,${(0.16 + 0.1 * Math.sin(t * 1.55)) * alpha})`;
    cx.lineWidth = 1.1; cx.stroke();
    cx.restore();
  }

  function rails(t) {
    const y0 = H * 0.24, y1 = H * 0.76, h = y1 - y0;
    // fuel rail — left
    const fx = 34;
    cx.strokeStyle = 'rgba(143,227,242,.10)'; cx.lineWidth = 1;
    cx.beginPath(); cx.moveTo(fx, y0); cx.lineTo(fx, y1); cx.stroke();
    if (V.fuel.kcal_target) {
      const k = Math.min(D.kcal / V.fuel.kcal_target, 1);
      cx.beginPath(); cx.moveTo(fx - 7, y0); cx.lineTo(fx + 7, y0);
      cx.strokeStyle = 'rgba(242,166,60,.5)'; cx.stroke();
      const fy = y1 - h * k;
      cx.strokeStyle = 'rgba(143,227,242,.55)'; cx.lineWidth = 2.6;
      cx.beginPath(); cx.moveTo(fx, y1); cx.lineTo(fx, fy); cx.stroke();
      cx.beginPath(); cx.arc(fx, fy, 3.1, 0, TAU);
      cx.fillStyle = D.kcal > V.fuel.kcal_target ? 'rgba(242,166,60,.95)' : 'rgba(233,246,250,.95)';
      cx.fill();
    }
    // load rail — right. The corridor is drawn as territory, not a number.
    const lx = W - 34;
    cx.strokeStyle = 'rgba(143,227,242,.10)'; cx.lineWidth = 1;
    cx.beginPath(); cx.moveTo(lx, y0); cx.lineTo(lx, y1); cx.stroke();
    if (V.load.have) {
      const [lo, hi] = V.load.corridor;
      const b0 = y1 - h * (lo / 2), b1 = y1 - h * (hi / 2);
      cx.fillStyle = 'rgba(110,231,168,.055)'; cx.fillRect(lx - 6, b1, 12, b0 - b1);
      cx.strokeStyle = 'rgba(110,231,168,.22)';
      cx.beginPath(); cx.moveTo(lx - 6, b0); cx.lineTo(lx + 6, b0);
      cx.moveTo(lx - 6, b1); cx.lineTo(lx + 6, b1); cx.stroke();
      const py = y1 - h * Math.min(1, Math.max(0, D.acr / 2));
      const hot = D.acr > hi || D.acr < lo;
      cx.beginPath(); cx.moveTo(lx - 13, py); cx.lineTo(lx + 13, py);
      cx.strokeStyle = hot ? 'rgba(242,166,60,.95)' : 'rgba(233,246,250,.9)';
      cx.lineWidth = 2; cx.stroke();
    }
  }

  function hud() {
    const f = V.fuel, c = V.composition, l = V.load, v = V.voyage, b = V.body;
    F.kcal.textContent = Math.round(D.kcal).toLocaleString();
    F.kcalSub.textContent = f.kcal_target
      ? `of ${f.kcal_target.toLocaleString()} kcal · ${Math.max(0, Math.round(f.kcal_target - D.kcal)).toLocaleString()} left`
      : 'no target set';
    F.kcal.classList.toggle('over', !!f.kcal_target && D.kcal > f.kcal_target);
    F.prot.textContent = Math.round(D.prot);
    F.protSub.textContent = f.protein_target_g ? `of ${f.protein_target_g} g` : 'no target set';

    F.acr.textContent = l.have ? D.acr.toFixed(2) : '—';
    F.acrSub.textContent = l.have ? `acute : chronic · ${esc(l.state || '')}`
      : 'needs 3 weeks of training';
    F.acr.classList.toggle('warn', l.have && (D.acr > l.corridor[1] || D.acr < l.corridor[0]));

    F.bf.textContent = c.have ? `${D.bf.toFixed(1)}%` : '—';
    F.bfSub.textContent = c.have
      ? (c.confidence === 'stale' ? `body fat · ${c.age_days}d old — re-tape`
        : `body fat · navy method`)
      : 'log waist + neck';
    F.bf.classList.toggle('faded', c.have && c.confidence === 'stale');

    if (v.have && v.goal_lb && v.start_lb != null) {
      const lost = v.start_lb - v.current_lb, togo = v.current_lb - v.goal_lb;
      F.voy.innerHTML = `${v.current_lb.toFixed(1)} <i>lb</i> · <b>${lost.toFixed(1)}</b> <i>travelled</i> · <b>${togo.toFixed(1)}</b> <i>remaining</i>`;
      F.eta.textContent = v.eta ? `projected arrival ${v.eta}` : 'pace unknown — log more weigh-ins';
    } else if (v.have) {
      F.voy.innerHTML = `${v.current_lb.toFixed(1)} <i>lb</i>`;
      F.eta.textContent = 'set a goal weight in Profile to plot the voyage';
    } else {
      F.voy.textContent = '—';
      F.eta.textContent = 'step on the scale to begin the voyage';
    }

    // ── change map readout ──
    const ch = V.change;
    F.modeBtn.hidden = !ch?.has_data;
    F.modeBtn.textContent = showChange ? 'Hide change' : 'Change map';
    F.modeBtn.classList.toggle('on', showChange);
    if (showChange && ch?.has_data) {
      const rows = ch.sites.filter(s => s.significant)
        .sort((a2, b2) => Math.abs(b2.delta_mm) - Math.abs(a2.delta_mm))
        .map(s => `<span class="cg-row ${s.direction}">
          <i>${esc(s.site.replace('_in', ''))}</i>
          ${s.delta_mm > 0 ? '+' : ''}${s.delta_mm.toFixed(1)} mm
          <small>${s.delta_in > 0 ? '+' : ''}${s.delta_in.toFixed(2)}"</small></span>`).join('');
      F.changeBox.innerHTML = ch.unchanged
        ? `<div class="cg-head">No measurable change</div>
           <div class="cg-note">Every site is inside the ±${ch.noise_floor_mm} mm
           tape noise floor over ${ch.span_days} days. That is a real answer,
           not a missing one.</div>`
        : `<div class="cg-head">${ch.span_days} days · radial change</div>${rows}
           <div class="cg-note">Cool = came in · warm = grew ·
           under ±${ch.noise_floor_mm} mm is tape noise and is not shown</div>`;
      F.changeBox.classList.add('show');
    } else {
      F.changeBox.classList.remove('show');
    }

    const tag = { full: '', estimated: 'ESTIMATED FIGURE — LOG A TAPE SET',
                  generic: 'UNMEASURED — ADD HEIGHT AND A TAPE SET' }[b.fidelity];
    F.stateTag.textContent = tag || (b.confidence === 'stale'
      ? `TAPE ${b.age_days} DAYS OLD` : '');
    F.stateTag.classList.toggle('show', !!F.stateTag.textContent);
  }

  function frame(now) {
    const dt = Math.min((now - t0) / 1000, 0.05); t0 = now;
    if (V) {
      const k = reduced ? 1 : dt * 3.2, ks = reduced ? 1 : dt * 1.6;
      D.kcal += ((V.fuel.kcal || 0) - D.kcal) * k;
      D.prot += ((V.fuel.protein_g || 0) - D.prot) * k;
      D.acr += ((V.load.acr || 0) - D.acr) * ks;
      D.bf += ((V.composition.bf_pct || 0) - D.bf) * ks;
      const t = now / 1000;
      field();
      if (V.body.have) figure(t);
      rails(t);
      hud();
    }
    raf = requestAnimationFrame(frame);
  }

  // Suspend on hidden: an unpaused canvas loop on a phone home screen is a
  // battery complaint waiting to happen.
  function vis() {
    if (document.hidden) { cancelAnimationFrame(raf); raf = 0; }
    else if (!raf) { t0 = performance.now(); raf = requestAnimationFrame(frame); }
  }
  document.addEventListener('visibilitychange', vis);

  const ro = new ResizeObserver(resize);
  ro.observe(wrap);
  resize();

  // ── the instrument as input surface ───────────────────────────────────
  // Logging *through* the figure is what kills the chore: tap the waist ring
  // and enter a waist. The forms in Weight stay — a hit target is a fine
  // affordance and a poor accessibility story, so this is *a* way to log,
  // never the only one.
  function pointAt(ev) {
    const r = cv.getBoundingClientRect();
    return [ev.clientX - r.left, ev.clientY - r.top];
  }

  cv.addEventListener('pointermove', ev => {
    const next = ringAt(...pointAt(ev));
    if (next !== hot) {
      hot = next;
      cv.style.cursor = hot ? 'pointer' : 'default';
      F.hint.textContent = hot ? `${hot.label} — tap to log` : '';
      F.hint.classList.toggle('show', !!hot);
    }
  });
  cv.addEventListener('pointerleave', () => {
    hot = null; cv.style.cursor = 'default'; F.hint.classList.remove('show');
  });

  cv.addEventListener('click', async ev => {
    const site = ringAt(...pointAt(ev));
    if (!site) return;
    const current = (V.body.tape_in || {})[site.key];
    const shown = V.body.fidelity === 'full' && current ? ` (last: ${current}")` : '';
    const raw = prompt(`${site.label} in inches${shown}\n\n${site.how}`,
                       V.body.fidelity === 'full' && current ? current : '');
    if (raw === null) return;
    const val = parseFloat(raw);
    if (!(val > 0)) { toast('Enter a number in inches.'); return; }
    // Same >2in placement guard as the Weight form: a jump that large is
    // almost always the tape sitting somewhere different.
    if (V.body.fidelity === 'full' && current && Math.abs(val - current) > 2
        && !confirm(`${site.label}: ${current}" → ${val.toFixed(1)}"\n\n`
          + 'That is a big change. Usually it means the tape sat somewhere '
          + 'different. Log it anyway?')) return;
    try {
      await api('POST', '/measurements', { [site.key]: val });
      toast(`${site.label} logged`);
      V = await api('GET', '/vessel');
      await refresh();
    } catch (e) { toast(e.message); }
  });

  F.modeBtn.addEventListener('click', () => { showChange = !showChange; });

  // Demo mode injects a payload on State rather than writing to the server,
  // so honour it when present instead of fetching over the top of it.
  if (state.vessel_demo) V = state.vessel_demo;
  else api('GET', '/vessel').then(v => { V = v; }).catch(() => {});
  raf = requestAnimationFrame(frame);

  // Stop cleanly when the section is replaced, or the loop outlives its canvas.
  const mo = new MutationObserver(() => {
    if (!document.contains(wrap)) {
      cancelAnimationFrame(raf);
      document.removeEventListener('visibilitychange', vis);
      ro.disconnect(); mo.disconnect();
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });
}
