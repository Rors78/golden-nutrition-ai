// Deals: Claude web-searches current prices on food & supplements.
import { el, esc, api, toast } from '../app.js';

export function renderDeals(root, state) {
  root.append(el('<h2 class="section-title">Deal Finder</h2>'));
  root.append(el('<p class="section-sub">Claude searches the web for current prices and offers on your fitness shopping list.</p>'));

  const form = el(`<form class="panel">
    <div class="grid-2">
      <label>What are you shopping for?
        <input name="items" type="text" placeholder="whey protein 5lb, creatine monohydrate, chicken breast" required></label>
      <label>Location / preferred stores <span style="color:var(--muted)">(optional)</span>
        <input name="location" type="text" placeholder="UK · Amazon, MyProtein, Tesco"></label>
    </div>
    <div style="margin-top:12px"><button class="gold-btn" type="submit">Find deals</button>
      <span style="color:var(--muted);font-size:12px;margin-left:10px">Live web search — takes 1–2 minutes</span></div>
  </form>`);
  const results = el('<div class="deals-results" style="margin-top:14px;display:grid;gap:10px"></div>');

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = form.querySelector('button');
    btn.disabled = true;
    results.innerHTML = '<p><span class="spinner"></span>Claude is out shopping — searching the web for current prices…</p>';
    try {
      const found = await api('POST', '/deals', Object.fromEntries(new FormData(form).entries()));
      showDeals(found);
    } catch (err) {
      results.innerHTML = '';
      toast(err.message);
    } finally { btn.disabled = false; }
  });

  function showDeals(d) {
    results.innerHTML = '';
    results.append(el(`<p class="section-sub" style="margin:0">Found ${d.results.length} deals for
      “${esc(d.items)}” · fetched ${esc(d.fetched_at)}</p>`));
    for (const deal of d.results) {
      results.append(el(`<div class="deal">
        <div class="deal-top"><span class="deal-item">${esc(deal.item)}</span>
          <span class="deal-price">${esc(deal.price)}</span></div>
        <div class="deal-meta">${esc(deal.store)}${deal.deal ? ` — ${esc(deal.deal)}` : ''}</div>
        ${deal.url ? `<a href="${esc(deal.url)}" target="_blank" rel="noopener noreferrer">${esc(deal.url)} ↗</a>` : ''}
      </div>`));
    }
    results.append(el(`<p style="color:var(--muted);font-size:12px">Prices are what Claude found just now — always confirm on the retailer's page before buying.</p>`));
  }

  root.append(form, results);

  if (state.deals?.results?.length) {
    form.items.value = state.deals.items || '';
    form.location.value = state.deals.location || '';
    showDeals(state.deals);
  }
}
