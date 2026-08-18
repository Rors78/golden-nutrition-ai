"""Storage layer: one JSON file, atomic writes, corruption recovery."""
import copy
import json
from pathlib import Path

DATA_FILE = Path("nutrition_data.json")

DEFAULT_DATA = {
    'profile': {
        'name': '',
        'age': 0,
        'sex': '',
        'height_in': 0,
        'weight': 0,
        'goal_weight': 0,
        'daily_protein_g': 150,
        'daily_calories': 2000,
        'notes': ''
    },
    'meals': [],
    'workouts': [],
    'supplements': [],
    'supplement_schedule': [],
    'weights': [],
    'vitals': [],
    'measurements': [],
    'photos': [],
    'recipes': [],
    'shopping_list': [],
    'watches': [],
    'remedy_cabinet': [],
    'settings': {
        'ntfy_server': 'https://ntfy.sh',
        'ntfy_topic': '',
        'ingest_token': '',
        'daily_steps': 8000,
        'sleep_target': 7.5
    }
}

MACRO_FIELDS = ('protein', 'calories', 'carbs', 'fat', 'fiber')

# Set when a corrupted file was recovered, so the UI can mention it once
last_recovery_note = None


def load():
    """Load user data, recovering gracefully from a corrupted file."""
    global last_recovery_note
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            for key, default in DEFAULT_DATA.items():
                data.setdefault(key, copy.deepcopy(default))
            for key, default in DEFAULT_DATA['profile'].items():
                data['profile'].setdefault(key, default)
            return data
        except (json.JSONDecodeError, OSError):
            backup = DATA_FILE.with_name(DATA_FILE.name + '.corrupt')
            DATA_FILE.replace(backup)
            last_recovery_note = f"Data file was unreadable — backed it up to {backup} and started fresh."
    return copy.deepcopy(DEFAULT_DATA)


def save(data):
    """Atomic write: a crash mid-save can't corrupt the file."""
    tmp = DATA_FILE.with_name(DATA_FILE.name + '.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    tmp.replace(DATA_FILE)


# Keys that must never leave this machine inside a backup or an export.
# Two categories, both non-user-data:
#   secrets  - live credentials. ntfy topics are bearer secrets (knowing the
#              topic is enough to subscribe AND publish), and ingest_token
#              authenticates the /api/ingest webhook.
#   derived  - AI output regenerated from the source data. It is not the user's
#              record, it outlives the context that explains it, and it is the
#              one field that has already been observed carrying foreign
#              content (SCARS #10).
EXPORT_STRIP_SETTINGS = ('ntfy_topic', 'ingest_token')
EXPORT_STRIP_TOP = ('briefing',)


def for_export(data):
    """A copy of `data` safe to write to disk or hand to another party.

    Strips credentials and derived AI output. Used by BOTH the export endpoint
    and the nightly backup, so the two cannot drift — the whole reason the
    backup stopped being a byte-for-byte copy.
    """
    out = copy.deepcopy(data)
    for k in EXPORT_STRIP_TOP:
        out.pop(k, None)
    settings = out.get('settings')
    if isinstance(settings, dict):
        for k in EXPORT_STRIP_SETTINGS:
            settings.pop(k, None)
    return out


def validate(data):
    """Return a list of structural problems, empty if the payload is sound.

    Deliberately structural, not semantic: it answers "is this a nutrition data
    file" rather than "are these good numbers". A backup that fails this is
    refused rather than written, because a snapshot that parses fine and is
    wrong is worse than no snapshot — it looks like a recovery point.
    """
    problems = []
    if not isinstance(data, dict):
        return ['payload is not a JSON object']
    if not isinstance(data.get('profile'), dict):
        problems.append('profile is missing or not an object')
    if not isinstance(data.get('settings'), dict):
        problems.append('settings is missing or not an object')
    for key in ('meals', 'workouts', 'weights', 'supplements'):
        if not isinstance(data.get(key), list):
            problems.append(f'{key} is missing or not a list')
    for key in ('vitals', 'measurements', 'photos', 'recipes'):
        if key in data and not isinstance(data[key], list):
            problems.append(f'{key} is present but not a list')
    return problems


def clean_num(v, cast=int):
    """Coerce user/AI input to a number, treating blanks as 0."""
    try:
        if v is None or v == '':
            return cast(0)
        return cast(float(v))
    except (TypeError, ValueError):
        return cast(0)
