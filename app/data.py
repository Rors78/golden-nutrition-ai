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


def clean_num(v, cast=int):
    """Coerce user/AI input to a number, treating blanks as 0."""
    try:
        if v is None or v == '':
            return cast(0)
        return cast(float(v))
    except (TypeError, ValueError):
        return cast(0)
