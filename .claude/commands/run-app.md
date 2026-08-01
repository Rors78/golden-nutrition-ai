---
description: Start the Golden Nutrition AI server and verify it's serving
---

Start the app and confirm it's healthy:

1. If something is already listening on port 8501, stop it first (`fuser -k 8501/tcp`).
2. Launch in the background: `./venv/bin/python run.py` (from the repo root).
3. Poll `http://localhost:8501` until it returns HTTP 200 (up to 15s).
4. Confirm `/api/state` returns valid JSON and report which AI backend it shows
   (`ai_backend` field).
5. Tell the user the app is up at http://localhost:8501.
