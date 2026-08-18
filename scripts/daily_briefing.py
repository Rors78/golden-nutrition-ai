#!/usr/bin/env python3
"""Generate the morning briefing and push it to the phone — for cron/systemd.

Run from the repo root (nutrition_data.json lives in the cwd):
    ./venv/bin/python scripts/daily_briefing.py

Install as a 7am systemd user timer with scripts/install_briefing_timer.sh.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402


EXIT_NOTHING_TO_BRIEF = 4


def main():
    app = create_app()
    with app.test_client() as client:
        res = client.post('/api/briefing')
        body = res.get_json() or {}
        if res.status_code == 200:
            print(f"Briefing generated for {body.get('date')} by {body.get('coach')}")
            return 0
        if res.status_code == 422:
            # Nothing logged: a real condition, not a malfunction. Distinct exit
            # code so Task Scheduler shows "no data" apart from "it broke" —
            # and never 0, which would claim a briefing that does not exist.
            print(f"No briefing today: {body.get('error')}", file=sys.stderr)
            return EXIT_NOTHING_TO_BRIEF
        print(f"Briefing failed: {body.get('error', res.status)}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
