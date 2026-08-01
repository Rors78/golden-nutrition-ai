// Supplements: daily checklist from a schedule, manual logging, history.
import { el, esc, api, toast, refresh, rowActions, barbell } from '../app.js';

const SUPPS = ['Multivitamin', 'Protein Shake', 'Creatine', 'Fish Oil', 'Vitamin D', 'BCAAs', 'Pre-Workout', 'Other'];
const TIMES = ['Morning', 'Afternoon', 'Evening', 'Pre-Workout', 'Post-Workout'];

export function renderSupplements(root, state) {
  root.append(el('<h2 class="section-title">Supplements</h2>'));
  root.append(el('<p class="section-sub">Set your daily stack once — it becomes a one-tap checklist every day.</p>'));

  // ── today's checklist ──
  const checklist = state.stats.checklist;
  const card = el('<div class="card"><p class="chart-title">Today\'s checklist</p></div>');
  if (checklist.length) {
    const done = checklist.filter(c => c.taken).length;
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
