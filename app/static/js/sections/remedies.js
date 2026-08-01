// The Apothecary: natural remedies from 11 world traditions — premium section.
// Evidence-graded, safety-first, complementary-never-alternative.
import { el, esc, api, toast, refresh } from '../app.js';

const CATEGORY_LABELS = {
  immune: 'Immune', digestion: 'Digestion', pain: 'Pain', heart: 'Heart',
  'blood-pressure': 'Blood pressure', 'blood-sugar': 'Blood sugar', sleep: 'Sleep',
  'stress-mood': 'Stress & mood', skin: 'Skin', wounds: 'Wounds',
  respiratory: 'Respiratory', energy: 'Energy', 'mens-health': "Men's health",
  'womens-health': "Women's health", brain: 'Brain', joints: 'Joints',
  'cancer-support': 'Complementary support', general: 'General',
};

const stars = n => `<span style="color:var(--gold-bright);letter-spacing:2px">${'★'.repeat(n)}</span><span style="color:var(--line);letter-spacing:2px">${'★'.repeat(5 - n)}</span>`;

export function renderRemedies(root, state) {
  const s = state.remedies_stats || {};
  root.append(el('<h2 class="section-title">The Apothecary</h2>'));
  root.append(el(`<p class="section-sub">${s.count || '350+'} natural remedies from ${s.traditions || 11}+ world traditions —
    65,000 years of healing knowledge, graded against modern evidence. Complementary to medical care, never a replacement.</p>`));

  // ── premium gate ──
  if (!state.remedies_unlocked) {
    const gate = el(`<div class="card" style="border:1px solid var(--gold-dim);max-width:620px">
      <p class="chart-title" style="color:var(--gold-bright)">Premium section</p>
      <p style="color:var(--ink-2);font-size:14px;line-height:1.7;margin:10px 0">
        The full archive: every remedy with its tradition of origin, evidence grade
        (the archive's own 1–5 star system), preparation instructions, and — the part that
        matters most — complete safety and drug-interaction warnings. Plus <strong>Ask the
        Apothecary</strong>: questions answered from this archive only, checked against
        your health profile.</p>
      <form class="form-row">
        <label style="flex:2 1 200px">Access key <input name="key" type="text" placeholder="Enter your key" autocomplete="off"></label>
        <button class="gold-btn" type="submit" style="flex:0 1 auto">Unlock</button>
      </form>
    </div>`);
    gate.querySelector('form').addEventListener('submit', async e => {
      e.preventDefault();
      try {
        await api('POST', '/remedies/unlock', Object.fromEntries(new FormData(e.target).entries()));
        toast('The Apothecary is open');
        await refresh();
      } catch (err) { toast(err.message); }
    });
    root.append(gate);
    return;
  }

  // ── ask the apothecary ──
  const askCard = el(`<div class="card">
    <p class="chart-title">Ask the Apothecary ${state.ai_backend ? `· ${esc(state.ai_backend)}` : ''}</p>
    <p style="color:var(--ink-2);font-size:13px;margin:8px 0">Answers come only from this archive, graded honestly,
      and checked against your profile notes for interactions.</p>
    <form class="form-row">
      <label style="flex:3 1 260px">Your question
        <input name="question" type="text" placeholder="what helps with sleep that won't clash with blood pressure meds?" autocomplete="off"></label>
      <button class="gold-btn" type="submit" style="flex:0 1 auto">Ask</button>
    </form>
    <div class="ask-result"></div>
  </div>`);
  const askForm = askCard.querySelector('form');
  const askOut = askCard.querySelector('.ask-result');
  askForm.addEventListener('submit', async e => {
    e.preventDefault();
    const question = askForm.question.value.trim();
    if (!question) { toast('Ask a question first.'); return; }
    const btn = askForm.querySelector('button');
    btn.disabled = true;
    askOut.innerHTML = '<p style="margin-top:12px"><span class="spinner"></span>Consulting the archive — about a minute…</p>';
    try {
      const { answer, sources } = await api('POST', '/remedies/ask', { question });
      askOut.innerHTML = `<div class="prose" style="margin-top:12px;font-size:14px">${esc(answer).replace(/\n/g, '<br>')}</div>
        <p style="color:var(--muted);font-size:12px;margin-top:10px">Drawn from: ${sources.map(esc).join(' · ')}</p>`;
    } catch (err) {
      askOut.innerHTML = '';
      toast(err.message);
    } finally { btn.disabled = false; }
  });
  root.append(askCard);

  // ── browse ──
  const browse = el(`<div class="card" style="margin-top:14px">
    <div class="form-row">
      <label style="flex:2 1 220px">Search <input class="rem-search" type="search" placeholder="honey, ginseng, cold exposure…"></label>
    </div>
    <div class="rem-cats" style="display:flex;gap:6px;flex-wrap:wrap;margin:10px 0"></div>
    <p class="rem-count" style="color:var(--muted);font-size:12px;margin:4px 0 10px"></p>
    <div class="rem-list" style="display:grid;gap:10px"></div>
  </div>`);
  const searchIn = browse.querySelector('.rem-search');
  const catsRow = browse.querySelector('.rem-cats');
  const countEl = browse.querySelector('.rem-count');
  const listEl = browse.querySelector('.rem-list');
  let all = [];
  let activeCat = 'all';
  const LIMIT = 40;

  function renderList() {
    const q = searchIn.value.trim().toLowerCase();
    const filtered = all.filter(r =>
      (activeCat === 'all' || r.categories.includes(activeCat)) &&
      (!q || `${r.name} ${r.aka} ${r.summary} ${r.traditions.join(' ')}`.toLowerCase().includes(q)));
    countEl.textContent = `${filtered.length} remedies${filtered.length > LIMIT ? ` — showing the ${LIMIT} strongest-evidence first, refine to narrow` : ''}`;
    listEl.innerHTML = '';
    for (const r of filtered.slice(0, LIMIT)) {
      listEl.append(el(`<details style="border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--bg)">
        <summary style="display:flex;align-items:center;gap:12px;padding:12px 14px;cursor:pointer;list-style:none;flex-wrap:wrap">
          <span style="flex:1;min-width:200px"><strong>${esc(r.name)}</strong>
            ${r.aka ? `<span style="color:var(--muted);font-size:12px"> · ${esc(r.aka)}</span>` : ''}
            <span style="display:block;color:var(--ink-2);font-size:12px;margin-top:2px">${esc(r.summary)}</span></span>
          <span style="text-align:right;font-size:11px">${stars(r.evidence)}<br>
            <span style="color:var(--steel)">${r.traditions.map(esc).join(' · ')}</span></span>
        </summary>
        <div style="padding:0 14px 14px;display:grid;gap:8px;font-size:13px">
          <div><span style="color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase">How to use</span><br>${esc(r.how)}</div>
          <div><span style="color:var(--warn);font-size:11px;letter-spacing:.08em;text-transform:uppercase">Safety & interactions</span><br>${esc(r.safety)}</div>
          <div><span style="color:var(--steel);font-size:11px;letter-spacing:.08em;text-transform:uppercase">Tradition</span><br>${esc(r.origin)}</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap">${r.categories.map(c =>
            `<span class="badge" style="color:var(--ink-2);font-size:11px">${esc(CATEGORY_LABELS[c] || c)}</span>`).join('')}</div>
        </div>
      </details>`));
    }
    if (!filtered.length) listEl.append(el('<div class="empty">Nothing matches — try fewer words.</div>'));
  }

  function renderCats() {
    catsRow.innerHTML = '';
    const cats = ['all', ...Object.keys(CATEGORY_LABELS).filter(c => all.some(r => r.categories.includes(c)))];
    for (const c of cats) {
      const b = el(`<button type="button" class="ghost-btn" style="min-height:34px;padding:6px 12px;font-size:12px${
        c === activeCat ? ';border-color:var(--gold);color:var(--gold-bright)' : ''}">${c === 'all' ? 'All' : esc(CATEGORY_LABELS[c])}</button>`);
      b.addEventListener('click', () => { activeCat = c; renderCats(); renderList(); });
      catsRow.append(b);
    }
  }

  searchIn.addEventListener('input', renderList);
  root.append(browse);

  api('GET', '/remedies').then(res => {
    all = res.remedies;
    renderCats();
    renderList();
  }).catch(e => { listEl.append(el(`<div class="empty">${esc(e.message)}</div>`)); });

  root.append(el(`<div class="callout warn" style="margin-top:14px">Complementary, not alternative: these remedies work
    best alongside evidence-based medical care, never instead of it. Natural does not mean safe — interactions with
    blood thinners, blood-pressure, diabetes, and psychiatric medications are real. Nothing here is medical advice;
    talk to a doctor or pharmacist before starting anything new, and never stop a prescription on your own.</div>`));
}
