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

EXIT_PUSH_FAILED = 2
EXIT_NO_CHANNEL = 3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import data as store, notify, stats  # noqa: E402


def main():
    d = store.load()

    backup_age = None
    snaps = sorted(Path('backups').glob('nutrition_data-*.json')) \
        if Path('backups').is_dir() else []
    if snaps:
        backup_age = (time.time() - snaps[-1].stat().st_mtime) / 86400

    alerts = stats.sentinel_alerts(d, backup_age_days=backup_age)
    if not alerts:
        print('Sentinel: all clear.')
        return 0
    print('Sentinel alerts:')
    for a in alerts:
        print(f'  - {a}')
    try:
        sent = notify.push(d['settings'], 'Golden Nutrition — sentinel',
                           '\n'.join(alerts[:4]))
    except Exception as e:
        # A sentinel that cannot deliver must not exit 0: a scheduled task
        # reporting success while nobody is told is a false green.
        print(f'Sentinel has {len(alerts)} alert(s) but the push FAILED: {e}',
              file=sys.stderr)
        return 2
    if not sent:
        print('Sentinel has alerts but NO ntfy topic is configured — nobody was '
              'notified. Set one in the Vitals tab.', file=sys.stderr)
        return 3
    print(f'Pushed {len(alerts)} alert(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
