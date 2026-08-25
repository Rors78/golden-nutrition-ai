// THE CORNER MAN — the coach as a presence, not a tab.
//
// A floating medallion in the corner of every screen. Tap it and the coach
// steps in: a slide-out drawer with the persona chat, a typing indicator,
// and quick asks answered INSTANTLY from the engines — no model call, no
// network, no wait. "What's my session?" reads the program. "What should I
// eat tonight?" reads recipe fit. "How's my week?" reads the report card.
// Free-form questions still go to the AI persona (with its consent-gated
// actions), and a voice toggle has the coach speak replies aloud.
import { State, el, esc, api, toast, refresh, coachMedallion } from '../app.js';

const VOICE_KEY = 'gna-coach-voice';

function currentCoach() {
  return (State?.coaches || []).find(c => c.id === State?.coach)
    || { id: 'coach', name: 'Coach', emoji: '🏋️' };
}

// ── deterministic answers: the engines speak for themselves ─────────────
const QUICK_ASKS = [
  {
    label: "Today's session",
    answer() {
      const ps = State?.stats?.program_status;
      if (!ps?.has_program) {
        return 'No block is forged yet. Workouts → The Program → pick your days and forge it — I will have the bar loaded before you get there.';
      }
      const n = ps.next_session;
      const sets = n.sets.map(s => `${s.weight}×${s.reps}${s.amrap ? '+' : ''}`).join(', ');
      const ar = State?.stats?.auto_regulation;
      const arNote = ar?.has_data && ar.factor !== 1
        ? ` Auto-regulation says ×${ar.factor} today (${ar.label}) — the session start applies it.` : '';
      return `Week ${ps.week}${ps.deload ? ' — deload, leave ego at the door' : ''}: `
        + `${n.lift}. Work up ${sets}, then ${n.supplemental.sets}×${n.supplemental.reps} at `
        + `${n.supplemental.weight}, finish with ${n.accessories.join(' and ')}. `
        + `${ps.done_this_week}/${ps.sessions_this_week} done this week.${arNote}`;
    },
  },
  {
    label: 'What should I eat tonight?',
    answer() {
      const rf = State?.stats?.recipe_fit;
      const fp = State?.stats?.fuel_plan;
      if (rf?.has_data) {
        const top = rf.ranked[0];
        return `You have ${rf.remaining.kcal.toLocaleString()} kcal and ${rf.remaining.protein} g `
          + `protein left. Best fit in the box: ${top.name} — ${top.verdict}.`;
      }
      if (fp?.has_data) {
        const t = fp.today;
        return `${rf?.note || 'No recipes to rank.'} Today's targets: ${t.kcal.toLocaleString()} kcal, `
          + `${t.protein} g protein (${fp.trained_today ? 'training day' : 'rest day'}).`;
      }
      return fp?.note || 'Log a weigh-in and the fuel plan will answer this properly.';
    },
  },
  {
    label: "How's my week?",
    answer() {
      const wi = State?.stats?.week_in_iron;
      if (!wi?.has_data) return 'No week on the books yet. Log anything today and the scoring starts.';
      const lines = wi.columns.map(c => `${c.key} ${c.pts}/${c.max} (${c.note})`).join('; ');
      const tone = wi.score >= 85 ? 'That is a week to keep.' :
        wi.score >= 60 ? 'Solid — one column short of great.' :
        'The plan survived. Now go beat it.';
      return `Week score ${wi.score}/100 — ${lines}. ${tone}`;
    },
  },
];

let open = false;

export function initCoachDock() {
  if (document.getElementById('coach-dock')) return;
  const dock = el(`<button id="coach-dock" type="button" aria-label="Talk to your coach"></button>`);
  const drawer = el(`<div id="coach-drawer" hidden>
    <div class="cd-head">
      <span class="cd-medal"></span>
      <div class="cd-who"><b></b><span>in your corner</span></div>
      <button type="button" class="cd-voice" title="Coach speaks replies aloud">🔊</button>
      <button type="button" class="cd-close" aria-label="Close">✕</button>
    </div>
    <div class="cd-log"></div>
    <div class="cd-chips"></div>
    <form class="cd-form" autocomplete="off">
      <input name="message" type="text" placeholder="Ask anything…" aria-label="Message your coach">
      <button class="gold-btn" type="submit">↵</button>
    </form>
  </div>`);
  document.body.append(dock, drawer);

  const log = drawer.querySelector('.cd-log');
  const chipsRow = drawer.querySelector('.cd-chips');
  const voiceBtn = drawer.querySelector('.cd-voice');

  const voiceOn = () => localStorage.getItem(VOICE_KEY) === '1';
  const paintVoice = () => {
    voiceBtn.classList.toggle('on', voiceOn());
    voiceBtn.title = voiceOn() ? 'Voice on — the coach speaks replies' : 'Voice off';
  };
  voiceBtn.addEventListener('click', () => {
    localStorage.setItem(VOICE_KEY, voiceOn() ? '0' : '1');
    paintVoice();
    if (!voiceOn()) speechSynthesis?.cancel();
  });

  function speak(text) {
    if (!voiceOn() || !('speechSynthesis' in window)) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/[*_#`]/g, ''));
    u.rate = 1.02; u.pitch = 0.9;
    speechSynthesis.speak(u);
  }

  function say(text, who) {
    const b = el(`<div class="cd-msg coach"><div>${esc(text)}</div>
      <span class="cd-ts">${esc(who || currentCoach().name)}</span></div>`);
    log.append(b);
    log.scrollTop = log.scrollHeight;
    speak(text);
    return b;
  }
  function mine(text) {
    log.append(el(`<div class="cd-msg user">${esc(text)}</div>`));
    log.scrollTop = log.scrollHeight;
  }

  // minimal consent card for agentic actions proposed in the drawer
  function miniAction(a) {
    const card = el(`<div class="cd-action">
      <span>${esc(a.tool.replace(/_/g, ' '))}</span>
      <button type="button" class="gold-btn cda-yes">Save it</button>
      <button type="button" class="ghost-btn cda-no">Dismiss</button></div>`);
    card.querySelector('.cda-no').addEventListener('click', () => card.remove());
    card.querySelector('.cda-yes').addEventListener('click', async ev => {
      ev.target.disabled = true;
      try {
        await api('POST', '/coach/act', { tool: a.tool, input: a.input });
        card.innerHTML = '<span class="cda-ok">✓ Saved</span>';
        await refresh();
      } catch (e) { ev.target.disabled = false; toast(e.message); }
    });
    log.append(card);
    log.scrollTop = log.scrollHeight;
  }

  for (const q of QUICK_ASKS) {
    const chip = el(`<button type="button" class="cd-chip">${esc(q.label)}</button>`);
    chip.addEventListener('click', () => {
      mine(q.label);
      // Engines answer instantly — a beat of "typing" keeps the rhythm human.
      const t = el('<div class="cd-msg coach cd-typing"><i></i><i></i><i></i></div>');
      log.append(t);
      log.scrollTop = log.scrollHeight;
      setTimeout(() => { t.remove(); say(q.answer()); }, 420);
    });
    chipsRow.append(chip);
  }

  drawer.querySelector('.cd-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    const input = drawer.querySelector('input[name=message]');
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    mine(message);
    const t = el('<div class="cd-msg coach cd-typing"><i></i><i></i><i></i></div>');
    log.append(t);
    log.scrollTop = log.scrollHeight;
    try {
      const { reply, actions } = await api('POST', '/coach/chat', { message });
      t.remove();
      say(reply);
      (actions || []).forEach(miniAction);
    } catch (e) {
      t.remove();
      say(`Can't reach the AI right now (${e.message}). The quick asks above still work — they come straight from your data.`);
    }
  });

  function paintIdentity() {
    const c = currentCoach();
    const slot = drawer.querySelector('.cd-medal');
    slot.innerHTML = '';
    slot.append(coachMedallion(c, 40));
    drawer.querySelector('.cd-who b').textContent = c.name;
    dock.innerHTML = '';
    dock.append(coachMedallion(c, 52));
  }

  function toggle(force) {
    open = force ?? !open;
    drawer.hidden = !open;
    dock.classList.toggle('open', open);
    if (open) {
      paintIdentity();
      if (!log.childElementCount) {
        say(`${currentCoach().name} here. Tap a quick ask, or type anything.`);
      }
      drawer.querySelector('input').focus();
    } else {
      speechSynthesis?.cancel();
    }
  }
  dock.addEventListener('click', () => toggle());
  drawer.querySelector('.cd-close').addEventListener('click', () => toggle(false));
  addEventListener('keydown', ev => { if (ev.key === 'Escape' && open) toggle(false); });

  paintVoice();
  // The dock waits for State so the medallion is the real coach's coin.
  const tryPaint = () => { if (State?.coaches) paintIdentity(); else setTimeout(tryPaint, 400); };
  tryPaint();
}
