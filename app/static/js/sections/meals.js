// Meals: AI quick log, one-tap re-log, manual entry, editable history.
import { el, esc, api, toast, refresh, rowActions } from '../app.js';

const MACROS = ['protein', 'calories', 'carbs', 'fat', 'fiber'];

export function renderMeals(root, state) {
  root.append(el('<h2 class="section-title">Meals</h2>'));
  root.append(el('<p class="section-sub">Tell Claude what you ate, re-log a regular, or enter it by hand.</p>'));

  // ── AI quick log ──
  const aiCard = el(`<div class="card">
    <p class="chart-title">AI quick log ${state.ai_backend ? `· ${esc(state.ai_backend)}` : ''}</p>
    <form class="form-row">
      <label style="flex:3 1 260px">What did you eat?
        <input name="description" type="text" placeholder="chicken burrito with rice and beans, and a protein shake" autocomplete="off"></label>
      <button class="gold-btn" type="submit">Estimate with AI</button>
    </form>
    <div class="ai-result"></div>
  </div>`);
  const aiForm = aiCard.querySelector('form');
  const aiResult = aiCard.querySelector('.ai-result');
  aiForm.addEventListener('submit', async e => {
    e.preventDefault();
    const description = aiForm.description.value.trim();
    if (!description) { toast('Describe what you ate first.'); return; }
    const btn = aiForm.querySelector('button');
    btn.disabled = true;
    aiResult.innerHTML = '<p style="margin:12px 0 0"><span class="spinner"></span>Claude is estimating the macros…</p>';
    try {
      const { meals } = await api('POST', '/meals/ai/parse', { description });
      showParsed(meals);
    } catch (err) {
      aiResult.innerHTML = '';
      toast(err.message);
    } finally { btn.disabled = false; }
  });

  function showParsed(meals) {
    const totalP = meals.reduce((s, m) => s + m.protein, 0);
    const totalC = meals.reduce((s, m) => s + m.calories, 0);
    aiResult.innerHTML = '';
    const wrap = el(`<div style="margin-top:12px">
      <div class="table-wrap"><table>
        <thead><tr><th>Item</th><th class="num">Protein</th><th class="num">Cal</th><th class="num">Carbs</th><th class="num">Fat</th><th class="num">Fiber</th></tr></thead>
        <tbody>${meals.map(m => `<tr><td>${esc(m.name)}</td><td class="num">${m.protein}g</td><td class="num">${m.calories}</td>
          <td class="num">${m.carbs}g</td><td class="num">${m.fat}g</td><td class="num">${m.fiber}g</td></tr>`).join('')}</tbody>
      </table></div>
      <p style="color:var(--ink-2);font-size:13px;margin:10px 0">Total: <strong style="color:var(--gold-bright)">${totalP}g protein, ${totalC} calories</strong></p>
      <div class="form-row">
        <button class="gold-btn add-all" type="button">Add all to log</button>
        <button class="ghost-btn discard" type="button">Discard estimate</button>
      </div></div>`);
    wrap.querySelector('.add-all').addEventListener('click', async () => {
      try {
        await api('POST', '/meals/ai/add', { meals });
        toast(`Added ${meals.length} meal${meals.length > 1 ? 's' : ''}`);
        await refresh();
      } catch (e) { toast(e.message); }
    });
    wrap.querySelector('.discard').addEventListener('click', () => { aiResult.innerHTML = ''; });
    aiResult.append(wrap);
  }

  root.append(aiCard);

  // ── quick add ──
  const quick = state.stats.quick_meals;
  if (quick.length) {
    const qCard = el(`<div class="card" style="margin-top:14px">
      <p class="chart-title">Quick add — your regulars</p>
      <form class="form-row">
        <label style="flex:3 1 240px">Recent meals<select name="idx">
          ${quick.map((m, i) => `<option value="${i}">${esc(m.name)} — ${m.protein ?? 0}g P / ${m.calories ?? 0} cal</option>`).join('')}
        </select></label>
        <button class="gold-btn" type="submit">＋ Log it again</button>
      </form></div>`);
    qCard.querySelector('form').addEventListener('submit', async e => {
      e.preventDefault();
      const src = quick[Number(qCard.querySelector('select').value)];
      try {
        await api('POST', '/meals', { ...src, date: undefined, time: undefined });
        toast(`Added: ${src.name}`);
        await refresh();
      } catch (err) { toast(err.message); }
    });
    root.append(qCard);
  }

  // ── manual entry ──
  const now = new Date();
  const manual = el(`<form class="panel" style="margin-top:14px">
    <p class="chart-title">Manual entry</p>
    <div class="grid-3">
      <label>Date <input name="date" type="date" value="${now.toISOString().slice(0, 10)}"></label>
      <label>Time <input name="time" type="time" value="${now.toTimeString().slice(0, 5)}"></label>
      <label>Meal name <input name="name" type="text" placeholder="Chicken & rice" required></label>
      <label>Protein (g) <input name="protein" type="number" min="0" value="30"></label>
      <label>Calories <input name="calories" type="number" min="0" value="400"></label>
      <label>Carbs (g) <input name="carbs" type="number" min="0" value="0"></label>
      <label>Fat (g) <input name="fat" type="number" min="0" value="0"></label>
      <label>Fiber (g) <input name="fiber" type="number" min="0" value="0"></label>
      <label>Notes <input name="notes" type="text" placeholder="Optional"></label>
    </div>
    <div style="margin-top:12px"><button class="gold-btn" type="submit">Add meal</button></div>
  </form>`);
  manual.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('POST', '/meals', Object.fromEntries(new FormData(manual).entries()));
      toast('Meal added');
      await refresh();
    } catch (err) { toast(err.message); }
  });
  root.append(manual);

  // ── last 7 days, editable ──
  root.append(el('<p class="chart-title" style="margin:18px 0 8px">Last 7 days</p>'));
  const weekAgo = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
  const rows = state.meals.map((m, idx) => ({ m, idx })).filter(({ m }) => m.date >= weekAgo).reverse();
  if (!rows.length) {
    root.append(el('<div class="empty">No meals in the last 7 days.</div>'));
    return;
  }
  const wrap = el(`<div class="table-wrap"><table>
    <thead><tr><th>Date</th><th>Time</th><th>Meal</th>
      <th class="num">P</th><th class="num">Cal</th><th class="num">C</th><th class="num">F</th><th class="num">Fib</th><th></th></tr></thead>
    <tbody></tbody></table></div>`);
  const tbody = wrap.querySelector('tbody');
  for (const { m, idx } of rows) {
    const tr = el(`<tr><td>${esc(m.date)}</td><td>${esc(m.time)}</td><td title="${esc(m.notes || '')}">${esc(m.name)}</td>
      <td class="num">${m.protein ?? 0}</td><td class="num">${m.calories ?? 0}</td>
      <td class="num">${m.carbs ?? 0}</td><td class="num">${m.fat ?? 0}</td><td class="num">${m.fiber ?? 0}</td></tr>`);
    tr.append(rowActions('meals', idx, { onEdit: () => editRow(tr, m, idx) }));
    tbody.append(tr);
  }
  root.append(wrap);

  function editRow(tr, m, idx) {
    tr.classList.add('editing');
    tr.innerHTML = `<td><input type="date" value="${esc(m.date)}"></td>
      <td><input type="time" value="${esc(m.time)}"></td>
      <td><input type="text" value="${esc(m.name)}"></td>
      ${MACROS.map(f => `<td><input type="number" min="0" value="${m[f] ?? 0}"></td>`).join('')}
      <td class="row-actions"><button class="icon-btn" title="Save">✓</button><button class="icon-btn danger" title="Cancel">↩</button></td>`;
    const inputs = tr.querySelectorAll('input');
    tr.querySelector('.icon-btn').addEventListener('click', async () => {
      const body = { date: inputs[0].value, time: inputs[1].value, name: inputs[2].value };
      MACROS.forEach((f, i) => { body[f] = inputs[3 + i].value; });
      try {
        await api('PUT', `/entry/meals/${idx}`, body);
        toast('Saved');
        await refresh();
      } catch (e) { toast(e.message); }
    });
    tr.querySelector('.danger').addEventListener('click', () => refresh());
  }
}
