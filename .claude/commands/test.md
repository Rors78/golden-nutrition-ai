---
description: Run the full test suite and report results
---

Run `./venv/bin/python -m pytest tests/ -q` from the repo root.

- If everything passes, report the count in one line.
- If anything fails, show the failing test output, diagnose the root cause,
  fix it (never by deleting assertions — see the qa agent's rules), and re-run
  until green.
