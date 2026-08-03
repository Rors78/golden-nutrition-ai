#!/usr/bin/env python3
"""Daily sentinel: push a phone alert only when something needs attention.

Checks: backup freshness, logging gone quiet, training-strain warnings,
cratered readiness, weight plateau. Silence means all clear.

Run from the repo root (nutrition_data.json lives in the cwd):
    ./venv/bin/python scripts/sentinel.py

Install as a daily 12:00 systemd user timer with scripts/install_sentinel_timer.sh;
on Windows, scripts/install_windows_tasks.ps1 registers the Sentinel task.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import data as store, notify, stats  # noqa: E402


def main():
    d = store.load()

    backup_age = None
    snaps = sorted(Path('backups').glob('nutrition_data-*.json')) \
        if Path('backups').is_dir() else []
    if snaps:
        backup_age = (time.time() - snaps[-1].stat().st_mtime) / 86400

    log_age = None
    if store.DATA_FILE.exists():
        log_age = (time.time() - store.DATA_FILE.stat().st_mtime) / 86400

    alerts = stats.sentinel_alerts(d, backup_age_days=backup_age,
                                   last_log_age_days=log_age)
    if not alerts:
        print('Sentinel: all clear.')
        return 0
    print('Sentinel alerts:')
    for a in alerts:
        print(f'  - {a}')
    try:
        sent = notify.push(d['settings'], 'Golden Nutrition — sentinel',
                           '\n'.join(alerts[:4]))
        if not sent:
            print('(no ntfy topic set — alerts shown here only)')
    except Exception as e:
        print(f'(push failed: {e})', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
