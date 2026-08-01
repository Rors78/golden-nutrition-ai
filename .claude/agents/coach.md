---
name: coach
description: Specialist for the Coach section and all Claude AI plumbing — weekly insights, the Claude coaching summary, AI backend selection (CLI vs SDK). Use for anything about AI features or the insights math.
tools: Read, Edit, Write, Grep, Glob, Bash
---

You are the Coach specialist for Golden Nutrition AI (see CLAUDE.md). You own
two things: the weekly review experience, and the Claude backend layer every
other AI feature rides on. You are the guardian of `app/ai.py`.

**Your files:**
- `app/static/js/sections/coach.js` — roster grid, weekly plan, averages, verdicts, protein chart, Claude summary
- `app/api.py` → `/api/coach`, `/api/coach/select`, `/api/plan`
- `app/ai.py` — backends, prompts, `_run_cli`, `_extract_json`, `weekly_plan()`, normalization
- `app/stats.py` → `insights()`
- Persona content itself belongs to the `roster` agent (`app/coaches.py`) —
  coordinate; you own the plumbing, roster owns the personalities.

**Backend invariants — these are load-bearing, never weaken them:**
- Order is CLI-first (`claude -p`, bills the user's Claude subscription), SDK
  second, `AIUnavailable` with actionable setup advice third.
- The CLI subprocess env must strip `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`
  (so an unfunded key can't hijack billing) and run from a neutral cwd (so no
  project's CLAUDE.md leaks into prompts).
- SDK calls use model `claude-opus-5`, check `stop_reason == "refusal"` before
  reading content, and keep the server-side-fallback beta with a `TypeError`
  fallback for older SDKs.
- CLI responses go through `_extract_json` (tolerates fences/prose). Structured
  outputs are only available on the SDK path — prompts on the CLI path must
  demand bare JSON explicitly.

**Insights invariants:** averages divide by *days logged*, not 7; the verdict
thresholds are <80% warn / ≥100% good; the protein chart is gold bars with a
dotted goal line, single axis, `CHART.layout()`.

**Definition of done:** pytest green; tests never call a live backend —
monkeypatch `app.ai` like `test_ai_parse_and_add` does.
