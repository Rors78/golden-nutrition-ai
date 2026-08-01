// Supplements: daily checklist from a schedule, manual logging, history.
import { el, esc, api, toast, refresh, rowActions, barbell } from '../app.js';

const SUPPS = ['Multivitamin', 'Protein Shake', 'Creatine', 'Fish Oil', 'Vitamin D', 'BCAAs', 'Pre-Workout', 'Other'];
const TIMES = ['Morning', 'Afternoon', 'Evening', 'Pre-Workout', 'Post-Workout'];

const TIME_GUESS = [
  [/pre.?(workout|training)/i, 'Pre-Workout'],
  [/post.?(workout|training)|recovery|after train/i, 'Post-Workout'],
  [/even|night|bed|sleep|dinner/i, 'Evening'],
  [/afternoon|lunch|midday/i, 'Afternoon'],
];

function guessTime(timing) {
  for (const [re, t] of TIME_GUESS) if (re.test(timing || '')) return t;
  return 'Morning';
}

export function renderSupplements(root, state) {
  root.append(el('<h2 class="section-title">Supplements</h2>'));
  root.append(el('<p class="section-sub">Set your daily stack once — it becomes a one-tap checklist every day.</p>'));

  // ── AI optimal-stack advisor ──
  const p = state.profile;
  const coach = (state.coaches || []).find(c => c.id === state.coach);
  const factors = [
    p.age ? `age ${p.age}` : 'age —',
    p.sex || 'sex —',
    p.weight ? `${p.weight} lbs` : 'weight —',
    p.goal_weight ? `goal ${p.goal_weight} lbs` : 'goal —',
    coach ? `coach: ${coach.name}` : null,
    p.notes ? `notes: ${p.notes}` : null,
  ].filter(Boolean);

  const adv = el(`<div class="card">
    <p class="chart-title">Optimal stack, personalized ${state.ai_backend ? `· ${esc(state.ai_backend)}` : ''}</p>
    <p style="color:var(--ink-2);font-size:13px;margin:8px 0">Claude weighs your profile, your logged training and diet gaps,
      and ${esc(coach ? coach.name + "'s" : "your coach's")} supplement philosophy — then tiers what's worth it and what to skip.</p>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px">${factors.map(f =>
      `<span class="badge" style="color:var(--ink-2)">${esc(f)}</span>`).join('')}</div>
    <button class="gold-btn" type="button">Analyze my stack</button>
    <div class="adv-result"></div>
  </div>`);
  const advBtn = adv.querySelector('button');
  const advOut = adv.querySelector('.adv-result');

  advBtn.addEventListener('click', async () => {
    if (!p.age || !p.sex) toast('Tip: add age & sex in Profile for sharper advice');
    advBtn.disabled = true;
    advOut.innerHTML = `<p style="margin-top:12px"><span class="spinner"></span>${esc(coach?.name || 'Coach')} is reviewing your stack — about a minute…</p>`;
    try {
      renderAdvice(await api('POST', '/supplements/advice'));
    } catch (e) {
      advOut.innerHTML = '';
      toast(e.message);
    } finally { advBtn.disabled = false; }
  });

  const PRIORITY = {
    essential: { label: 'Essential', color: 'var(--gold)' },
    beneficial: { label: 'Beneficial', color: 'var(--steel)' },
    optional: { label: 'Optional', color: 'var(--muted)' },
  };

  function renderAdvice(cached) {
    const a = cached.advice;
    const by = coach && cached.coach === coach.id ? coach.name
      : (state.coaches || []).find(c => c.id === cached.coach)?.name || 'your coach';
    advOut.innerHTML = '';
    advOut.append(el(`<p class="section-sub" style="margin:12px 0 8px">By ${esc(by)} · ${esc(cached.generated_at)}</p>`));

    for (const key of ['essential', 'beneficial', 'optional']) {
      const recs = a.recommendations.filter(r => r.priority === key);
      if (!recs.length) continue;
      advOut.append(el(`<p class="chart-title" style="margin:12px 0 6px;color:${PRIORITY[key].color}">${PRIORITY[key].label}</p>`));
      for (const r of recs) {
        const row = el(`<div class="deal" style="border-left-color:${PRIORITY[key].color};margin-bottom:8px">
          <div class="deal-top"><span class="deal-item">${esc(r.name)}</span>
            <span style="font-family:var(--font-mono);font-size:12px;color:var(--ink-2);white-space:nowrap">${esc(r.dose)} · ${esc(r.timing)}</span></div>
          <div class="deal-meta">${esc(r.why)}</div>
          <div><button class="ghost-btn" type="button" style="min-height:34px;padding:6px 14px;font-size:12px">＋ Add to my stack</button></div>
        </div>`);
        row.querySelector('button').addEventListener('click', async () => {
          try {
            await api('POST', '/schedule', { name: r.name, time: guessTime(r.timing) });
            toast(`${r.name} added to your stack`);
            await refresh();
          } catch (e) { toast(e.message); }
        });
        advOut.append(row);
      }
    }

    if (a.skip?.length) {
      advOut.append(el(`<p class="chart-title" style="margin:12px 0 6px">Skip these</p>
        <div style="display:grid;gap:6px">${a.skip.map(s =>
          `<div style="color:var(--muted);font-size:13px"><s style="color:var(--ink-2)">${esc(s.name)}</s> — ${esc(s.why)}</div>`).join('')}</div>`));
    }
    if (a.coach_note) advOut.append(el(`<div class="callout good" style="margin-top:12px">${esc(a.coach_note)}</div>`));

    const worthBuying = a.recommendations
      .filter(r => r.priority !== 'optional').map(r => r.name);
    if (worthBuying.length) {
      const shop = el(`<div style="margin-top:12px"><button class="gold-btn" type="button">Shop this stack in Deals</button></div>`);
      shop.querySelector('button').addEventListener('click', () => {
        sessionStorage.setItem('deals_prefill', worthBuying.join(', '));
        location.hash = 'deals';
      });
      advOut.append(shop);
    }
    if (a.safety_note) advOut.append(el(`<div class="callout warn" style="margin-top:8px">${esc(a.safety_note)}
      <span style="color:var(--muted)"> Not medical advice — check with a doctor or pharmacist, especially alongside medication.</span></div>`));
  }

  if (state.supp_advice?.advice) renderAdvice(state.supp_advice);
  root.append(adv);

  // ── supplement library: what's a true supplement and what's garbage ──
  const kb = state.kb || [];
  if (kb.length) {
    const TIERS = {
      proven: { label: 'Proven', desc: 'the real ones', tier: '', order: 0 },
      solid: { label: 'Solid', desc: 'worth it for the right training', tier: 'steel', order: 1 },
      situational: { label: 'Situational', desc: 'only if you specifically need it', tier: 'green', order: 2 },
      weak: { label: 'Weak', desc: 'evidence too thin for the money', tier: 'iron', order: 3 },
      garbage: { label: 'Garbage', desc: 'marketing in a tub', tier: 'rust', order: 4 },
    };
    const lib = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Supplement library — the honest tier list</p>
      <p style="color:var(--ink-2);font-size:13px;margin:8px 0">Every mainstream supplement, graded on current evidence.
        Know what's a true supplement and what's garbage before you spend.</p>
      <div class="lib-filters" style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0"></div>
      <div class="lib-list" style="display:grid;gap:10px"></div>
      <p style="color:var(--muted);font-size:12px;margin:12px 0 0">Distilled from current evidence summaries and position stands.
        Reference information, not medical advice.</p>
    </div>`);
    const filters = lib.querySelector('.lib-filters');
    const list = lib.querySelector('.lib-list');
    let active = 'all';

    function renderList() {
      list.innerHTML = '';
      const items = kb
        .filter(s => active === 'all' || s.verdict === active)
        .sort((x, y) => TIERS[x.verdict].order - TIERS[y.verdict].order || x.name.localeCompare(y.name));
      for (const s of items) {
        const t = TIERS[s.verdict];
        list.append(el(`<details class="lib-item" style="border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--bg)">
          <summary style="display:flex;align-items:center;gap:12px;padding:12px 14px;cursor:pointer;list-style:none">
            <span class="plate-disc ${t.tier}" style="width:38px;height:38px;font-size:9px">${t.label.slice(0, 4).toUpperCase()}</span>
            <span style="flex:1"><strong>${esc(s.name)}</strong>
              <span style="display:block;color:var(--ink-2);font-size:12px;margin-top:2px">${esc(s.evidence_for)}</span></span>
          </summary>
          <div style="padding:0 14px 14px;display:grid;gap:8px;font-size:13px">
            <div><span style="color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase">Dose</span><br>${esc(s.dose)}</div>
            <div><span style="color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase">Timing</span><br>${esc(s.timing)}</div>
            <div class="grid-2" style="gap:10px">
              <div><span style="color:var(--good);font-size:11px;letter-spacing:.08em;text-transform:uppercase">Pros</span>
                <ul style="margin:4px 0 0;padding-left:18px;color:var(--ink-2)">${s.pros.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
              <div><span style="color:var(--warn);font-size:11px;letter-spacing:.08em;text-transform:uppercase">Cons</span>
                <ul style="margin:4px 0 0;padding-left:18px;color:var(--ink-2)">${s.cons.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
            </div>
            <div><span style="color:var(--steel);font-size:11px;letter-spacing:.08em;text-transform:uppercase">Best for</span><br>${esc(s.best_for)}</div>
            <div><span style="color:var(--bad);font-size:11px;letter-spacing:.08em;text-transform:uppercase">Skip if</span><br>${esc(s.skip_if)}</div>
          </div>
        </details>`));
      }
      if (!items.length) list.append(el('<div class="empty">Nothing in this tier.</div>'));
    }

    const allBtn = el(`<button type="button" class="ghost-btn" style="min-height:36px;padding:6px 14px;font-size:12px">All (${kb.length})</button>`);
    allBtn.addEventListener('click', () => { active = 'all'; syncFilters(); });
    filters.append(allBtn);
    for (const [key, t] of Object.entries(TIERS)) {
      const n = kb.filter(s => s.verdict === key).length;
      const b = el(`<button type="button" class="ghost-btn" style="min-height:36px;padding:6px 14px;font-size:12px">${t.label} (${n}) — ${t.desc}</button>`);
      b.addEventListener('click', () => { active = key; syncFilters(); });
      b.dataset.key = key;
      filters.append(b);
    }
    function syncFilters() {
      [...filters.children].forEach(b => {
        const on = (b.dataset.key || 'all') === active;
        b.style.borderColor = on ? 'var(--gold)' : '';
        b.style.color = on ? 'var(--gold-bright)' : '';
      });
      renderList();
    }
    syncFilters();
    root.append(lib);
  }

  // ── today's checklist ──
  const checklist = state.stats.checklist;
  const card = el('<div class="card"><p class="chart-title">Today\'s checklist</p></div>');
  if (checklist.length) {
    const done = checklist.filter(c => c.taken).length;
    const adh = state.stats.adherence;
    if (adh?.has_schedule) {
      card.querySelector('.chart-title').insertAdjacentHTML('beforeend',
        ` · <span style="color:${adh.pct >= 80 ? 'var(--good)' : adh.pct >= 50 ? 'var(--ink-2)' : 'var(--warn)'}">${adh.pct}% adherence, 7d</span>`);
    }
    const list = el('<div class="check-list"></div>');
    for (const item of checklist) {
      const node = el(`<button type="button" class="check-item${item.taken ? ' done' : ''}">
        <span class="box">${item.taken ? '✓' : ''}</span>
        <span class="check-name">${esc(item.name)} <span style="color:var(--muted);font-size:12px">· ${esc(item.time)}</span></span>
      </button>`);
      node.addEventListener('click', async () => {
        try {
          await api('POST', '/checklist/toggle', { name: item.name, time: item.time });
          await refresh();
        } catch (e) { toast(e.message); }
      });
      list.append(node);
    }
    card.append(list, barbell('Stack completed', done, checklist.length, ''));
    const shopStack = el(`<div style="margin-top:10px"><button class="ghost-btn" type="button">Find deals on my stack</button></div>`);
    shopStack.querySelector('button').addEventListener('click', () => {
      sessionStorage.setItem('deals_prefill', [...new Set(schedule.map(i => i.name))].join(', '));
      location.hash = 'deals';
    });
    card.append(shopStack);
  } else {
    card.append(el('<div class="empty">No schedule yet — build your stack below and it shows up here every day.</div>'));
  }
  root.append(card);

  // ── schedule editor ──
  const sched = el(`<div class="card" style="margin-top:14px">
    <p class="chart-title">Daily stack</p>
    <form class="form-row">
      <label>Supplement <select name="name">${SUPPS.map(s => `<option>${s}</option>`).join('')}</select></label>
      <label>Time of day <select name="time">${TIMES.map(t => `<option>${t}</option>`).join('')}</select></label>
      <button class="gold-btn" type="submit" style="flex:0 1 auto">Add to stack</button>
    </form>
    <div class="sched-list" style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap"></div>
  </div>`);
  sched.querySelector('form').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('POST', '/schedule', Object.fromEntries(new FormData(e.target).entries()));
      toast('Added to stack');
      await refresh();
    } catch (err) { toast(err.message); }
  });
  const schedList = sched.querySelector('.sched-list');
  state.schedule.forEach((item, idx) => {
    const chip = el(`<span class="badge" style="display:inline-flex;align-items:center;gap:8px;font-size:12px;color:var(--ink-2)">
      ${esc(item.name)} · ${esc(item.time)} <button class="icon-btn danger" style="min-height:auto;padding:0 2px" title="Remove">✕</button></span>`);
    chip.querySelector('button').addEventListener('click', async () => {
      try { await api('DELETE', `/schedule/${idx}`); toast('Removed'); await refresh(); }
      catch (e) { toast(e.message); }
    });
    schedList.append(chip);
  });
  root.append(sched);

  // ── manual log ──
  const manual = el(`<form class="panel form-row" style="margin-top:14px">
    <label>Date <input name="date" type="date" value="${new Date().toISOString().slice(0, 10)}"></label>
    <label>Supplement <select name="name">${SUPPS.map(s => `<option>${s}</option>`).join('')}</select></label>
    <label>Time of day <select name="time">${TIMES.map(t => `<option>${t}</option>`).join('')}</select></label>
    <label style="flex-direction:row;align-items:center;gap:8px;flex:0 1 auto">
      <input name="taken" type="checkbox" checked style="min-height:auto;width:20px;height:20px"> Taken</label>
    <button class="gold-btn" type="submit" style="flex:0 1 auto">Log</button>
  </form>`);
  manual.addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(manual);
    try {
      await api('POST', '/supplements', {
        date: fd.get('date'), name: fd.get('name'), time: fd.get('time'),
        taken: manual.taken.checked,
      });
      toast('Logged');
      await refresh();
    } catch (err) { toast(err.message); }
  });
  root.append(manual);

  // ── this week ──
  root.append(el('<p class="chart-title" style="margin:18px 0 8px">This week</p>'));
  const weekAgo = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
  const rows = state.supplements.map((s, idx) => ({ s, idx })).filter(({ s }) => s.date >= weekAgo).reverse();
  if (!rows.length) {
    root.append(el('<div class="empty">Nothing logged this week.</div>'));
    return;
  }
  const wrap = el(`<div class="table-wrap"><table>
    <thead><tr><th>Date</th><th>Supplement</th><th>Time</th><th>Taken</th><th></th></tr></thead>
    <tbody></tbody></table></div>`);
  const tbody = wrap.querySelector('tbody');
  for (const { s, idx } of rows) {
    const tr = el(`<tr><td>${esc(s.date)}</td><td>${esc(s.name)}</td><td>${esc(s.time)}</td>
      <td>${s.taken ? '<span class="note-good">✓ taken</span>' : '<span class="note-warn">missed</span>'}</td></tr>`);
    tr.append(rowActions('supplements', idx));
    tbody.append(tr);
  }
  root.append(wrap);
}
