# Scars

Hard-won lessons from real incidents in this repo. Each entry: what happened,
why it happened, and what it costs you if you undo the fix.

---

## 1. Never pass a bare `claude` to `subprocess` on Windows

**Incident.** Every AI feature returned HTTP 502 instantly. The header cheerfully
read "AI: Claude Code (subscription)" the whole time.

**Cause.** `shutil.which("claude")` finds `claude.CMD`, so the availability check
passed — but `subprocess.run(["claude", ...])` failed with
`[WinError 2] The system cannot find the file specified`, because CreateProcess
will not launch a `.cmd` by bare name.

**Fix.** `app/ai.py` has `_claude_exe()`, which returns the full resolved path
from `shutil.which`. All CLI call sites use it.

**If you undo it:** the whole AI layer dies on Windows while still advertising
itself as available — the worst kind of failure, because the UI lies about it.

---

## 2. Decode CLI subprocess output as UTF-8 explicitly

**Incident.** After fixing #1, briefings still 502'd — this time with
`UnicodeDecodeError: 'charmap' codec can't decode byte 0x8f`, and `stdout` came
back as `None`.

**Cause.** Python decoded the subprocess pipe using the Windows ANSI codepage
(cp1252), which chokes on the emoji coaches love ("YEAH BUDDY 💪").

**Fix.** Every `subprocess.run` in `app/ai.py` passes
`encoding="utf-8", errors="replace"`.

**If you undo it:** any AI response containing an emoji or a curly quote takes
down the request. Intermittent and maddening — it depends on what the model says.

---

## 3. Keep `.ps1` files pure ASCII

**Incident.** `powershell -ExecutionPolicy Bypass -File scripts\install_windows_tasks.ps1`
— the exact command in the README — failed with cascading parse errors. The same
file ran fine under `pwsh` 7.

**Cause.** Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI. An em-dash
(`E2 80 94`) decodes to `â€”`, and that trailing `"` is a curly quote that 5.1
treats as a string terminator.

**Fix.** Both `.ps1` files are ASCII-only (plain hyphens, no smart quotes).

**Verify before shipping any `.ps1`:** parse-check under 5.1 specifically, not
just pwsh 7 —
`powershell -NoProfile -Command "[System.Management.Automation.Language.Parser]::ParseFile('<abs path>',[ref]$null,[ref]$errs)"`.

**If you undo it:** shortcuts and scheduled tasks — which invoke
`powershell.exe`, i.e. 5.1 — break, while your terminal testing in pwsh 7 keeps
passing.

---

## 4. `el()` returns only the FIRST root element

**Incident.** The Weight tab rendered "Failed to load: DOM element provided is
null or undefined". A tape-measurement chart never appeared.

**Cause.** `el()` in `app/static/js/app.js` returns
`template.content.firstElementChild`. The markup passed in had two sibling roots
(a header row and the chart div); the second was silently discarded, so Plotly
got `null`.

**Fix.** Wrap multi-root markup in a single container `<div>` before passing to
`el()`.

**If you forget:** silent partial renders — the section still "works", just
missing whatever came after the first root. Easy to miss without a browser check.

---

## 5. Verify features in a browser, not just via pytest

Three real bugs this repo shipped-and-caught were invisible to the test suite:
the `el()` truncation above, an interval that killed itself before its panel
mounted (live session clock), and a stale-cache JS load. **The suite passes and
the page is still broken.** Run the app (`run.py 8502` against a scratch data
file) and click the actual feature.

---

## 6. Statistical features must stay silent without enough data

`stats.energy_balance` (adaptive TDEE) requires >= 10 fully-logged days and >= 8
weigh-ins spanning two weeks. `stats.training_strain` requires a real 3-week
baseline. Both return `has_data: False` otherwise, and the UI hides the card.

**Why it matters:** a TDEE computed from three days of partial logging is not a
rough estimate, it is a wrong number that a user will eat by. Honest silence
beats a confident guess. Same reason partial food-log days (< 800 cal) are
excluded from the intake average — they would drag the estimate down and hand
back a maintenance figure that is too low.

---

## 7. False green: "nothing logged" measured the app, not the user

**Incident.** A false-green audit fed the sentinel a data file whose newest user
entry was 8 days old — and it reported all clear.

**Cause.** The quiet-logging alert read the data file's **mtime**. The app
rewrites that file during ordinary activity (minting an ingest token on
`/api/state`, saving settings), so mtime measured *the app being alive*, not
*the user showing up*. The check could never fire while the server ran — which
is precisely when you would want it to.

**Fix.** `stats.days_since_user_entry()` derives the answer from actual entry
dates across meals/workouts/weights/vitals/supplements/measurements. Never
logged is its own distinct alert, not silence.

**The general rule:** healthy-by-absence is the most common false green there
is. When a check reports "fine", confirm it *measured something and found
nothing* rather than *measured nothing*.

---

## 8. False green: a scheduled job that exits 0 while telling nobody

**Incident.** The `\GoldenNutritionAI\Sentinel` task showed `LastTaskResult: 0`
— success — after its 12:00 run. It had, in fact, notified no one: no ntfy topic
was configured, so the alerts went to a `print()` no human reads.

**Cause.** `sentinel.py` returned 0 unconditionally. An undeliverable alert and a
clean bill of health were the same exit code.

**Fix.** The sentinel now exits **3** when it has alerts but no push channel and
**2** when the push raises, so Task Scheduler's LastTaskResult stops lying.
System Pulse also warns when no notification topic is set, since that panel is
where a human actually looks.

**If you undo it:** the entire alerting layer reverts to decorative — every job
green, nobody told. Verified red-capable: with alerts and no topic the script
exits 3; healthy with a topic it exits 0 and stays silent.

---

## 9. Server lifetime: use the scheduled task, not a session shell

**Incident.** The app died when a Claude Code session ended, because it had been
started as a background shell owned by that session.

**Fix.** `\GoldenNutritionAI\Server` (Task Scheduler) owns the server; it also
starts at logon. `scripts/launch_app.ps1` — what the desktop shortcut runs —
starts that task if the server is down rather than spawning its own copy.

**If you start it from a shell instead:** it dies with the shell, and the desktop
shortcut can end up racing a second server on the same port.

---

## 10. False green: a healthy backend that wrote someone else's project into the data file

**Incident.** The 07:00 briefing for 2026-08-18 was stored in `nutrition_data.json`
as a Claude Code response about an 18-bot crypto trading fleet, COSMOS
dashboards, and a 14-engine math council — none of which exist in this app. The
AI backend was healthy the whole time: it connected, responded, and returned
fluent prose. Every scheduled task reported success.

**Cause — not the two obvious ones.** It was not a walked-up project
`CLAUDE.md` (there is no user-global one on the box) and not the memory
directory. `app/ai.py` **already** ran the CLI with
`cwd=tempfile.gettempdir()` and the comment "neutral cwd: no project context
leaks in" — and the contamination happened anyway. Reading the actual session
transcript for the 07:00 run showed the source: the **user-global skills
registry**. Skill descriptions (`fleet-status`, `bot-onboard`, ...) are injected
into every `claude -p` invocation so the model can pick relevant ones. They are
registered at user scope, so they follow the binary regardless of cwd, project,
or memory. A neutral cwd cannot fence this off.

**The compounding failure.** Every list in the file was empty. With no data,
there was nothing to brief on, so the model filled the space from the only
context it had. The endpoint then did `store.save(d)` on the result with no
validation — a wrong record written into the user's history, where it reads as
fact afterward.

**Fix.** Three parts, all needed:
1. `ai.daily_briefing()` is **SDK-only**. A briefing is a stateless completion;
   `claude -p` is an agent primitive carrying skills, memory, tools, and an
   environment preamble — all contamination surface this feature does not use.
   Interactive features keep the CLI-first order (they are supervised).
2. `_briefing_has_material()` refuses (422) before calling the AI at all when
   nothing is logged. An empty briefing is not a weak briefing, it is invention.
3. `_briefing_is_plausible()` gates the text **before** `store.save`, and the
   stored record carries `input_sha` — a hash of the exact context that produced
   it, so provenance is checkable later instead of inferred.

**If you undo it:** the 07:00 job silently resumes writing whatever ambient
context the CLI happens to carry that morning into the user's permanent record —
and since the backend is genuinely healthy, no health check will ever notice.
An observability fix would not have caught this one; only a correctness gate does.

**The general rule:** for any unattended job that *persists* its output, validate
before the write, not after. And prefer the narrowest primitive that does the
job — an agent where a completion suffices is an open context surface you are
not using but still inherit.
