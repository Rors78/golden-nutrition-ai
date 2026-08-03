"""Tolerant CSV import — bring history from other apps.

Handles MyFitnessPal-style meal exports, Strong-style workout exports
(one row per set), and any date,weight file. Header matching is
case/space-insensitive with per-app aliases; rows that don't parse are
skipped, never fatal. Duplicates against existing data are skipped so
re-importing the same file is a no-op.
"""
import csv
import io
from datetime import datetime

MEAL_ALIASES = {
    'date': ('date', 'day'),
    'name': ('name', 'meal', 'food', 'food name', 'description', 'item'),
    'protein': ('protein', 'protein (g)', 'protein_g'),
    'calories': ('calories', 'energy', 'kcal', 'energy (kcal)'),
    'carbs': ('carbs', 'carbs (g)', 'carbohydrates', 'carbohydrates (g)'),
    'fat': ('fat', 'fat (g)', 'total fat'),
    'fiber': ('fiber', 'fiber (g)', 'fibre'),
}
WEIGHT_ALIASES = {
    'date': ('date', 'day'),
    'weight': ('weight', 'weight (lbs)', 'lbs', 'body weight', 'bodyweight'),
}
WORKOUT_ALIASES = {
    'date': ('date', 'day'),
    'workout': ('workout name', 'workout', 'routine'),
    'exercise': ('exercise name', 'exercise'),
    'weight': ('weight', 'weight (lbs)', 'lbs'),
    'reps': ('reps', 'repetitions'),
}


def _parse_date(raw):
    s = str(raw or '').strip().strip('"')
    for cand in (s, s[:10]):
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d.%m.%Y', '%b %d, %Y'):
            try:
                return datetime.strptime(cand, fmt).date().isoformat()
            except ValueError:
                pass
    return None


def _mapper(fieldnames, aliases):
    """our field -> actual CSV header, case/space tolerant."""
    lowered = {str(f).strip().lower(): f for f in fieldnames or []}
    m = {}
    for ours, names in aliases.items():
        for n in names:
            if n in lowered:
                m[ours] = lowered[n]
                break
    return m


def _num(v, cast=float):
    try:
        return cast(float(str(v).replace(',', '').strip() or 0))
    except (TypeError, ValueError):
        return cast(0)


def _import_meals(text, data):
    rows = csv.DictReader(io.StringIO(text))
    m = _mapper(rows.fieldnames, MEAL_ALIASES)
    if 'date' not in m or 'name' not in m:
        raise ValueError('Meals CSV needs at least Date and Meal/Food columns.')
    existing = {(x['date'], str(x.get('name', '')).strip().lower())
                for x in data['meals']}
    imported = skipped = 0
    for r in rows:
        day = _parse_date(r.get(m['date']))
        name = str(r.get(m['name']) or '').strip()
        if not day or not name or (day, name.lower()) in existing:
            skipped += 1
            continue
        meal = {'date': day, 'time': '12:00', 'name': name[:120],
                'notes': 'Imported'}
        for f in ('protein', 'calories', 'carbs', 'fat', 'fiber'):
            meal[f] = _num(r.get(m[f])) if f in m else 0
        data['meals'].append(meal)
        existing.add((day, name.lower()))
        imported += 1
    return imported, skipped


def _import_weights(text, data):
    rows = csv.DictReader(io.StringIO(text))
    m = _mapper(rows.fieldnames, WEIGHT_ALIASES)
    if 'date' not in m or 'weight' not in m:
        raise ValueError('Weights CSV needs Date and Weight columns.')
    existing = {w['date'] for w in data['weights']}
    imported = skipped = 0
    for r in rows:
        day = _parse_date(r.get(m['date']))
        lbs = _num(r.get(m['weight']))
        if not day or lbs <= 0 or day in existing:
            skipped += 1
            continue
        data['weights'].append({'date': day, 'weight': lbs})
        existing.add(day)
        imported += 1
    if imported:
        data['weights'].sort(key=lambda w: w['date'])
        data['profile']['weight'] = data['weights'][-1]['weight']
    return imported, skipped


def _import_workouts(text, data):
    rows = csv.DictReader(io.StringIO(text))
    m = _mapper(rows.fieldnames, WORKOUT_ALIASES)
    if 'date' not in m or 'exercise' not in m:
        raise ValueError('Workouts CSV needs Date and Exercise Name columns '
                         '(Strong-style, one row per set).')
    existing = {(w['date'], w.get('name', '')) for w in data['workouts']}
    sessions = {}
    skipped = 0
    for r in rows:
        day = _parse_date(r.get(m['date']))
        exercise = str(r.get(m['exercise']) or '').strip()
        if not day or not exercise:
            skipped += 1
            continue
        wname = (str(r.get(m['workout']) or '').strip() or 'Imported workout') \
            if 'workout' in m else 'Imported workout'
        if (day, wname) in existing:
            skipped += 1
            continue
        sessions.setdefault((day, wname), []).append({
            'exercise': exercise[:60],
            'sets': 1,
            'reps': _num(r.get(m['reps']), int) if 'reps' in m else 0,
            'weight': _num(r.get(m['weight'])) if 'weight' in m else 0,
        })
    for (day, wname), exercises in sorted(sessions.items()):
        data['workouts'].append({
            'date': day, 'time': '12:00', 'name': wname, 'duration': 60,
            'intensity': 'Moderate', 'notes': 'Imported',
            'exercises': exercises,
        })
    return len(sessions), skipped


def import_kind(kind, text, data):
    """Dispatch. Returns (imported, skipped); raises ValueError on bad shape."""
    fn = {'meals': _import_meals, 'weights': _import_weights,
          'workouts': _import_workouts}.get(kind)
    if fn is None:
        raise ValueError('kind must be meals, weights, or workouts.')
    return fn(text, data)
