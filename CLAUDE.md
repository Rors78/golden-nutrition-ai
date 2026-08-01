# Golden Nutrition AI

A local-first fitness & nutrition tracker: Flask JSON API + vanilla-JS single-page
frontend, with Claude-powered features (meal macro estimation, weekly coaching,
live deal finding) that run on the user's Claude subscription via the Claude Code
CLI (`claude -p`), falling back to the Anthropic API when the CLI isn't installed.

## Commands

```bash
./venv/bin/python run.py            # serve on http://localhost:8501
./venv/bin/python -m pytest tests/  # run the test suite (no AI credentials needed)
```

CI (GitHub Actions) runs pytest on every push and PR.

## Architecture

| Path | What lives there |
|---|---|
| `run.py` | entry point (port 8501 by default) |
| `app/__init__.py` | Flask app factory; serves the SPA at `/` |
| `app/data.py` | storage: `nutrition_data.json`, atomic writes, corruption recovery |
| `app/ai.py` | Claude backends: CLI-first (`claude -p`, subscription), SDK fallback |
| `app/coaches.py` | the 10-coach roster: research-backed personas + `persona_prompt()` |
| `app/stats.py` | computed stats: today totals, weight trend/ETA, insights, progression |
| `app/api.py` | all `/api/*` JSON endpoints (one blueprint) |
| `app/templates/index.html` | SPA shell: header, tabs, profile dialog |
| `app/static/css/style.css` | the entire design system (tokens at the top) |
| `app/static/js/app.js` | SPA core: state, router, api(), toast, metric, barbell, CHART |
| `app/static/js/sections/*.js` | one module per section — see the agent roster below |
| `tests/test_app.py` | Flask test-client suite; AI is monkeypatched |

## Data model (`nutrition_data.json`)

Top-level keys: `profile`, `meals`, `workouts` (with nested `exercises`),
`supplements`, `supplement_schedule`, `weights`, `deals` (cache).
Meals carry `protein/calories/carbs/fat/fiber`; older files without newer keys
must keep loading (defaults fill in — `test_legacy_v1_data_still_loads` guards this).

## Conventions

- **Entry identity is list index** (`/api/entry/<kind>/<idx>`); the frontend
  always re-fetches `/api/state` after any mutation — never patch client state.
- Every route loads + saves via `app/data.py`; never touch the JSON file directly.
- AI calls must keep the CLI-first / SDK-fallback order and must strip
  `ANTHROPIC_API_KEY` from the CLI subprocess env (see `app/ai.py`).
- Frontend is dependency-free ES modules + Plotly CDN. Use the helpers from
  `app.js` (`el`, `esc`, `api`, `toast`, `metric`, `barbell`, `rowActions`,
  `CHART.layout()`); escape all user data with `esc()`.
- Design tokens live in `:root` of `style.css` — never hardcode colors in JS/HTML.
- Charts: single axis, gold `#d9a441` primary / steel `#7da7c4` secondary,
  recessive grid, `CHART.config` (no modebar), hover templates on every trace.
- After any behavior change: add/adjust a test in `tests/test_app.py` and run pytest.

## Specialist agents

One agent per app section lives in `.claude/agents/` — delegate section work to
them (e.g. "have the meals agent add a barcode field"): `dashboard`, `weight`,
`meals`, `workouts`, `supplements`, `deals`, `coach`, `roster` (the 10 coach
personas), plus `design` (visual system) and `qa` (tests/CI). Each owns its
section's JS module and API endpoints.
