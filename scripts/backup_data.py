#!/usr/bin/env python3
"""Nightly snapshot of nutrition_data.json with rotation.

Copies the data file to backups/nutrition_data-YYYY-MM-DD.json (one per day,
same-day rerun overwrites) and prunes to the newest KEEP snapshots. Run from
the repo root, or let the systemd timer installed by
scripts/install_backup_timer.sh handle it.
"""
import json
import sys
from datetime import date
from pathlib import Path

KEEP = 14
EXIT_INVALID = 5

repo = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo))

try:
    from app import data as store
except ImportError:  # running the script detached from the package
    store = None

def _fallback_validate(data):
    """Minimal structural check when app.data is not importable.

    Kept deliberately weak — it is a floor, not a substitute. The real rules
    live in app/data.py so there is one definition when the package is present.
    """
    if not isinstance(data, dict):
        return ['payload is not a JSON object']
    return [] if isinstance(data.get('profile'), dict) else ['profile is missing']


def _fallback_strip(data):
    """Strip credentials and derived output without app.data present."""
    out = dict(data)
    out.pop('briefing', None)
    if isinstance(out.get('settings'), dict):
        out['settings'] = {k: v for k, v in out['settings'].items()
                           if k not in ('ntfy_topic', 'ingest_token')}
    return out


src = repo / 'nutrition_data.json'
dest_dir = repo / 'backups'

if not src.exists():
    print('No nutrition_data.json yet — nothing to back up.')
    sys.exit(0)

# load -> validate -> strip -> write.
#
# This was shutil.copy2, which gave the backup path no schema awareness at all:
# it could not strip credentials, could not validate, and faithfully preserved
# valid-but-wrong content. Atomic writes protect against torn files; they do not
# protect against a file that parses fine and is wrong.
try:
    raw = json.loads(src.read_text(encoding='utf-8'))
except (OSError, ValueError) as e:
    print(f'Refusing to back up: source file is unreadable ({e}).', file=sys.stderr)
    sys.exit(EXIT_INVALID)

problems = store.validate(raw) if store else _fallback_validate(raw)
if problems:
    # Refuse rather than snapshot something broken. A bad backup is worse than a
    # missing one: it looks like a recovery point. System Pulse tracks backup
    # freshness, so refusing surfaces as "stale" — the correct loud signal.
    print('Refusing to back up — the data file did not validate:', file=sys.stderr)
    for p in problems:
        print(f'  - {p}', file=sys.stderr)
    sys.exit(EXIT_INVALID)

dest_dir.mkdir(exist_ok=True)
dest = dest_dir / f'nutrition_data-{date.today().isoformat()}.json'
safe = store.for_export(raw) if store else _fallback_strip(raw)
dest.write_text(json.dumps(safe, indent=2), encoding='utf-8')

snapshots = sorted(dest_dir.glob('nutrition_data-*.json'))
for old in snapshots[:-KEEP]:
    old.unlink()

print(f'Backed up to {dest} ({len(snapshots[-KEEP:])} snapshots kept)')
