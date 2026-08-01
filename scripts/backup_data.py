#!/usr/bin/env python3
"""Nightly snapshot of nutrition_data.json with rotation.

Copies the data file to backups/nutrition_data-YYYY-MM-DD.json (one per day,
same-day rerun overwrites) and prunes to the newest KEEP snapshots. Run from
the repo root, or let the systemd timer installed by
scripts/install_backup_timer.sh handle it.
"""
import shutil
import sys
from datetime import date
from pathlib import Path

KEEP = 14

repo = Path(__file__).resolve().parent.parent
src = repo / 'nutrition_data.json'
dest_dir = repo / 'backups'

if not src.exists():
    print('No nutrition_data.json yet — nothing to back up.')
    sys.exit(0)

dest_dir.mkdir(exist_ok=True)
dest = dest_dir / f'nutrition_data-{date.today().isoformat()}.json'
shutil.copy2(src, dest)

snapshots = sorted(dest_dir.glob('nutrition_data-*.json'))
for old in snapshots[:-KEEP]:
    old.unlink()

print(f'Backed up to {dest} ({len(snapshots[-KEEP:])} snapshots kept)')
