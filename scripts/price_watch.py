#!/usr/bin/env python3
"""Re-check all price watches and push drop alerts — for cron/systemd.

Run from the repo root (nutrition_data.json lives in the cwd):
    ./venv/bin/python scripts/price_watch.py

Install as a daily 09:00 systemd user timer with scripts/install_price_watch_timer.sh.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402


def main():
    app = create_app()
    with app.test_client() as client:
        res = client.post('/api/watches/recheck')
        body = res.get_json() or {}
        if res.status_code == 200:
            print(f"Re-checked {body.get('updated', 0)} watches; "
                  f"{len(body.get('drops', []))} drop(s)")
            return 0
        print(f"Price watch failed: {body.get('error', res.status)}", file=sys.stderr)
        # 'No price watches yet' is a clean no-op, not a failure
        return 0 if 'No price watches' in str(body.get('error', '')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
