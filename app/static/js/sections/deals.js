// Deals: shopping list, live web-searched prices, and price watches with
// history + drop alerts pushed to the phone.
import { el, esc, api, toast, refresh, CHART } from '../app.js';

export function renderDeals(root, state) {
  root.append(el('<h2 class="section-title">Deal Finder</h2>'));
  root.append(el('<p class="section-sub">Build the list, let Claude hunt the prices, watch the good ones — the app pings your phone when they drop.</p>'));

  // ── restock radar: supplements running low, one tap from the stack ──
  const low = (state.stats?.checklist || []).filter(c => c.low);
  if (low.length) {
    const names = [...new Set(low.map(c => c.name))];
    const inList = new Set((state.shopping_list || []).map(i => i.toLowerCase()));
    const missing = names.filter(n => !inList.has(n.toLowerCase()));
    const radar = el(`<div class="callout warn" style="margin-bottom:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <span style="flex:1;min-width:220px"><strong>Restock radar:</strong> ${names.map(esc).join(', ')}
        ${names.length > 1 ? 'are' : 'is'} running low in your stack.</span>
      ${missing.length ? '<button class="ghost-btn" type="button" style="flex:0 1 auto;min-height:34px;padding:6px 12px;font-size:12px">Add to shopping list</button>' : '<span style="font-size:12px;color:var(--muted)">already on the list</span>'}
    </div>`);
    radar.querySelector('button')?.addEventListener('click', async () => {
      try { await api('POST', '/shopping', { items: missing }); toast('Added to the list'); await refresh(); }
      catch (e) { toast(e.message); }
    });
    root.append(radar);
  }

  // ── shopping list ──
  const shop = el(`<div class="card">
    <p class="chart-title">Shopping list</p>
    <div class="shop-chips" style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0"></div>
    <form class="form-row">
      <label style="flex:2 1 200px">Add item <input name="item" type="text" placeholder="whey protein 5lb" autocomplete="off"></label>
      <button class="ghost-btn" type="submit" style="flex:0 1 auto">Add</button>
      <button class="ghost-btn from-stack" type="button" style="flex:0 1 auto">Add my supplement stack</button>
      <button class="gold-btn hunt-list" type="button" style="flex:0 1 auto">Find deals for my list</button>
    </form>
  </div>`);
  const chips = shop.querySelector('.shop-chips');
  const list = state.shopping_list || [];
  if (list.length) {
    list.forEach((item, idx) => {
      const chip = el(`<span class="badge" style="display:inline-flex;align-items:center;gap:8px;font-size:12px;color:var(--ink-2)">
        ${esc(item)} <button class="icon-btn danger" style="min-height:auto;padding:0 2px" title="Remove">✕</button></span>`);
      chip.querySelector('button').addEventListener('click', async () => {
        try { await api('DELETE', `/shopping/${idx}`); await refresh(); } catch (e) { toast(e.message); }
      });
      chips.append(chip);
    });
  } else {
    chips.append(el('<span style="color:var(--muted);font-size:13px">Empty — add items, or pull in your supplement stack.</span>'));
  }
  shop.querySelector('form').addEventListener('submit', async e => {
    e.preventDefault();
    const item = e.target.item.value.trim();
    if (!item) return;
    try { await api('POST', '/shopping', { item }); toast('Added'); await refresh(); }
    catch (err) { toast(err.message); }
  });
  shop.querySelector('.from-stack').addEventListener('click', async () => {
    const names = [...new Set((state.schedule || []).map(i => i.name))];
    if (!names.length) { toast('Your supplement stack is empty.'); return; }
    try {
      await api('POST', '/shopping', { items: names });
      toast('Stack added to the list');
      await refresh();
    } catch (e) { toast(e.message); }
  });
  root.append(shop);

  // ── search ──
  const form = el(`<form class="panel" style="margin-top:14px">
    <div class="grid-2">
      <label>What are you shopping for?
        <input name="items" type="text" placeholder="whey protein 5lb, creatine monohydrate, chicken breast" required></label>
      <label>Location / preferred stores <span style="color:var(--muted)">(remembered)</span>
        <input name="location" type="text" value="${esc(state.settings?.deals_location || '')}" placeholder="UK · Amazon, MyProtein, Tesco"></label>
    </div>
    <div style="margin-top:12px"><button class="gold-btn" type="submit">Find deals</button>
      <span style="color:var(--muted);font-size:12px;margin-left:10px">Live web search — takes 1–2 minutes</span></div>
  </form>`);
  const results = el('<div class="deals-results" style="margin-top:14px;display:grid;gap:10px"></div>');

  async function hunt(items, location) {
    results.innerHTML = '<p><span class="spinner"></span>Claude is out shopping — searching the web for current prices…</p>';
    try {
      const found = await api('POST', '/deals', { items, location });
      showDeals(found);
    } catch (err) {
      results.innerHTML = '';
      toast(err.message);
    }
  }

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = form.querySelector('button');
    btn.disabled = true;
    await hunt(form.items.value, form.location.value);
    btn.disabled = false;
  });
  shop.querySelector('.hunt-list').addEventListener('click', async ev => {
    if (!list.length) { toast('The list is empty.'); return; }
    ev.target.disabled = true;
    form.items.value = list.join(', ');
    await hunt(list.join(', '), form.location.value);
    ev.target.disabled = false;
  });

  function showDeals(d) {
    results.innerHTML = '';
    results.append(el(`<p class="section-sub" style="margin:0">Found ${d.results.length} deals for
      “${esc(d.items)}” · fetched ${esc(d.fetched_at)}</p>`));
    for (const deal of d.results) {
      const card = el(`<div class="deal">
        <div class="deal-top"><span class="deal-item">${esc(deal.item)}</span>
          <span class="deal-price">${esc(deal.price)}</span></div>
        <div class="deal-meta">${esc(deal.store)}${deal.deal ? ` — ${esc(deal.deal)}` : ''}
          ${deal.unit_price ? ` · <span style="color:var(--steel);font-family:var(--font-mono)">${esc(deal.unit_price)}</span>` : ''}</div>
        <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
          ${deal.url ? `<a href="${esc(deal.url)}" target="_blank" rel="noopener noreferrer">${esc(deal.url)} ↗</a>` : ''}
          <button class="ghost-btn watch-btn" type="button" style="min-height:32px;padding:5px 12px;font-size:12px">Watch price</button>
        </div>
      </div>`);
      card.querySelector('.watch-btn').addEventListener('click', async () => {
        try {
          await api('POST', '/watches', deal);
          toast(`Watching: ${deal.item}`);
          await refresh();
        } catch (e) { toast(e.message); }
      });
      results.append(card);
    }
    results.append(el(`<p style="color:var(--muted);font-size:12px">Prices are what Claude found just now — always confirm on the retailer's page before buying.</p>`));
  }

  root.append(form, results);

  if (state.deals?.results?.length) {
    form.items.value = state.deals.items || '';
    showDeals(state.deals);
  }

  // Hand-off from the Supps tab: "shop this stack" pre-fills the search
  const prefill = sessionStorage.getItem('deals_prefill');
  if (prefill) {
    sessionStorage.removeItem('deals_prefill');
    form.items.value = prefill;
    toast('Stack loaded — hit Find deals when ready');
    form.items.focus();
  }

  // ── price watches ──
  const watches = state.watches || [];
  const watchCard = el(`<div class="card" style="margin-top:14px">
    <div class="form-row" style="align-items:center">
      <p class="chart-title" style="margin:0;flex:1">Price watches ${watches.length ? `· ${watches.length}` : ''}</p>
      ${watches.length ? '<button class="gold-btn recheck" type="button" style="flex:0 1 auto;min-height:38px;padding:8px 16px;font-size:13px">Re-check prices now</button>' : ''}
    </div>
    <p style="color:var(--ink-2);font-size:13px;margin:8px 0 0">Watched items get re-searched on demand (or on the daily timer) —
      a real drop pings your phone.</p>
    <div class="watch-summary"></div>
    <div class="watch-list" style="display:grid;gap:10px;margin-top:10px"></div>
  </div>`);
  const insights = state.stats?.watch_insights || [];
  const byItem = Object.fromEntries(insights.map(i => [i.item, i]));
  const atBest = insights.filter(i => i.verdict === 'best' && i.points > 1).length;
  if (atBest) {
    watchCard.querySelector('.watch-summary').append(el(
      `<div class="callout good" style="margin-top:10px">${atBest} of your ${insights.length}
        watches ${atBest > 1 ? 'are' : 'is'} at the lowest price seen — buy window is open.</div>`));
  }
  const wl = watchCard.querySelector('.watch-list');
  if (!watches.length) {
    wl.append(el('<div class="empty">No watches yet — hit “Watch price” on any deal above.</div>'));
  }
  watches.forEach((w, idx) => {
    const latest = w.history[w.history.length - 1];
    const best = w.history.length ? Math.min(...w.history.map(p => p.price)) : null;
    const row = el(`<div style="border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--bg);padding:12px 14px;display:grid;gap:6px">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline;flex-wrap:wrap">
        <strong>${esc(w.item)}${(() => {
          const ins = byItem[w.item];
          if (!ins?.verdict || ins.points < 2) return '';
          const color = ins.verdict === 'best' ? 'var(--good)' : ins.verdict === 'high' ? 'var(--warn)' : 'var(--muted)';
          return ` <span title="${esc(ins.text)}" style="font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
            color:${color};border:1px solid ${color};border-radius:999px;padding:2px 8px;vertical-align:middle">${esc(ins.verdict)}</span>`;
        })()}</strong>
        <span style="font-family:var(--font-mono);font-size:13px">
          ${latest ? `latest <span style="color:var(--gold-bright)">${esc(latest.raw || latest.price)}</span> · ${esc(latest.store)}` : 'no price points yet'}
          ${best != null && latest && latest.price > best ? ` · best ${best}` : ''}</span>
      </div>
      ${latest?.url ? `<a href="${esc(latest.url)}" target="_blank" rel="noopener noreferrer" style="color:var(--steel);font-size:12px;overflow-wrap:anywhere">${esc(latest.url)} ↗</a>` : ''}
      <div class="watch-spark"></div>
      <div><button class="icon-btn danger" title="Stop watching">✕ stop watching</button></div>
    </div>`);
    if (w.history.length >= 2) {
      const spark = row.querySelector('.watch-spark');
      spark.style.height = '64px';
      Plotly.newPlot(spark,
        [{ x: w.history.map(p => p.date), y: w.history.map(p => p.price),
           mode: 'lines+markers', line: { color: CHART.gold, width: 2 }, marker: { size: 5 },
           hovertemplate: '%{x}<br>%{y}<extra></extra>' }],
        CHART.layout({ height: 64, margin: { l: 34, r: 6, t: 4, b: 18 },
          xaxis: { visible: false, fixedrange: true },
          yaxis: { gridcolor: 'rgba(110,118,131,.12)', zeroline: false, fixedrange: true, tickfont: { size: 9 } } }),
        CHART.config);
    }
    row.querySelector('.danger').addEventListener('click', async () => {
      try { await api('DELETE', `/watches/${idx}`); toast('Watch removed'); await refresh(); }
      catch (e) { toast(e.message); }
    });
    wl.append(row);
  });
  const recheckBtn = watchCard.querySelector('.recheck');
  if (recheckBtn) recheckBtn.addEventListener('click', async () => {
    recheckBtn.disabled = true;
    recheckBtn.textContent = 'Hunting…';
    try {
      const res = await api('POST', '/watches/recheck');
      toast(res.drops.length
        ? `Price drops: ${res.drops.map(x => x.item).join(', ')}`
        : `Re-checked ${res.updated} watch${res.updated === 1 ? '' : 'es'} — no drops`);
      await refresh();
    } catch (e) {
      toast(e.message);
      recheckBtn.disabled = false;
      recheckBtn.textContent = 'Re-check prices now';
    }
  });
  root.append(watchCard);
}
