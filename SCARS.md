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

## 7. Server lifetime: use the scheduled task, not a session shell

**Incident.** The app died when a Claude Code session ended, because it had been
started as a background shell owned by that session.

**Fix.** `\GoldenNutritionAI\Server` (Task Scheduler) owns the server; it also
starts at logon. `scripts/launch_app.ps1` — what the desktop shortcut runs —
starts that task if the server is down rather than spawning its own copy.

**If you start it from a shell instead:** it dies with the shell, and the desktop
shortcut can end up racing a second server on the same port.
