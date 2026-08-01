"""JSON API consumed by the single-page frontend."""
import csv
import io
from datetime import date, datetime

from flask import Blueprint, jsonify, request, Response

from . import ai, data as store, stats
from .coaches import DEFAULT_COACH, ROSTER, get_coach, persona_prompt
from .data import clean_num

bp = Blueprint('api', __name__, url_prefix='/api')

EDITABLE_KINDS = ('meals', 'workouts', 'supplements', 'weights')


def _err(message, status=400):
    return jsonify({'error': str(message)}), status


@bp.get('/state')
def get_state():
    d = store.load()
    note, store.last_recovery_note = store.last_recovery_note, None
    return jsonify({
        'profile': d['profile'],
        'meals': d['meals'],
        'workouts': d['workouts'],
        'supplements': d['supplements'],
        'schedule': d['supplement_schedule'],
        'weights': sorted(d['weights'], key=lambda w: w['date']),
        'deals': d.get('deals'),
        'coaches': ROSTER,
        'coach': d['profile'].get('coach', DEFAULT_COACH),
        'plan': d.get('plan'),
        'stats': {
            'today': stats.today_summary(d),
            'weight': stats.weight_stats(d),
            'insights': stats.insights(d),
            'progression': stats.progression(d),
            'quick_meals': stats.quick_meals(d),
            'checklist': stats.checklist(d),
        },
        'ai_backend': ai.backend_name(),
        'recovery_note': note,
    })


@bp.post('/profile')
def save_profile():
    body = request.get_json(force=True)
    d = store.load()
    d['profile'] = {
        'name': str(body.get('name', '')),
        'weight': clean_num(body.get('weight'), float),
        'goal_weight': clean_num(body.get('goal_weight'), float),
        'daily_protein_g': clean_num(body.get('daily_protein_g')),
        'daily_calories': clean_num(body.get('daily_calories')),
        'coach': d['profile'].get('coach', DEFAULT_COACH),
    }
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/coach/select')
def select_coach():
    body = request.get_json(force=True)
    coach_id = str(body.get('id', ''))
    if coach_id not in {c['id'] for c in ROSTER}:
        return _err('Unknown coach.', 404)
    d = store.load()
    d['profile']['coach'] = coach_id
    store.save(d)
    return jsonify({'ok': True, 'coach': coach_id})


@bp.post('/plan')
def weekly_plan():
    d = store.load()
    coach = get_coach(d['profile'].get('coach', DEFAULT_COACH))
    ins = stats.insights(d)
    context = ''
    if ins.get('has_data'):
        context = (f"averaging {ins['avg_daily_protein']}g protein/day over "
                   f"{ins['days_logged']} logged days, {ins['workout_count']} workouts this week")
    try:
        plan = ai.weekly_plan(d['profile'], persona_prompt(coach), context)
    except Exception as e:
        return _err(e, 502)
    d['plan'] = {'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                 'coach': coach['id'], 'plan': plan}
    store.save(d)
    return jsonify(d['plan'])


def _normalize_meal(m):
    return {
        'date': str(m.get('date') or date.today().isoformat())[:10],
        'time': str(m.get('time') or datetime.now().strftime('%H:%M'))[:5],
        'name': str(m.get('name', '')).strip(),
        'protein': clean_num(m.get('protein')),
        'calories': clean_num(m.get('calories')),
        'carbs': clean_num(m.get('carbs')),
        'fat': clean_num(m.get('fat')),
        'fiber': clean_num(m.get('fiber')),
        'notes': str(m.get('notes', '')),
    }


@bp.post('/meals')
def add_meal():
    meal = _normalize_meal(request.get_json(force=True))
    if not meal['name']:
        return _err('Meal name is required.')
    d = store.load()
    d['meals'].append(meal)
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/meals/ai/parse')
def ai_parse_meals():
    body = request.get_json(force=True)
    desc = str(body.get('description', '')).strip()
    if not desc:
        return _err('Describe what you ate first.')
    try:
        return jsonify({'meals': ai.parse_meals(desc)})
    except Exception as e:
        return _err(e, 502)


@bp.post('/meals/ai/add')
def ai_add_meals():
    body = request.get_json(force=True)
    meals = body.get('meals', [])
    if not meals:
        return _err('Nothing to add.')
    d = store.load()
    now = datetime.now().strftime('%H:%M')
    for m in meals:
        meal = _normalize_meal({**m, 'date': date.today().isoformat(),
                                'time': now, 'notes': 'Estimated by Claude'})
        if meal['name']:
            d['meals'].append(meal)
    store.save(d)
    return jsonify({'ok': True, 'added': len(meals)})


@bp.post('/weights')
def add_weight():
    body = request.get_json(force=True)
    day = str(body.get('date') or date.today().isoformat())[:10]
    lbs = clean_num(body.get('weight'), float)
    if lbs <= 0:
        return _err('Weight must be above 0.')
    d = store.load()
    d['weights'] = [w for w in d['weights'] if w['date'] != day]
    d['weights'].append({'date': day, 'weight': lbs})
    d['weights'].sort(key=lambda w: w['date'])
    d['profile']['weight'] = d['weights'][-1]['weight']
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/workouts')
def add_workout():
    body = request.get_json(force=True)
    exercises = []
    for r in body.get('exercises', []):
        name = str(r.get('exercise', '')).strip()
        if not name:
            continue
        exercises.append({
            'exercise': name,
            'sets': clean_num(r.get('sets')),
            'reps': clean_num(r.get('reps')),
            'weight': clean_num(r.get('weight'), float),
        })
    d = store.load()
    d['workouts'].append({
        'date': str(body.get('date') or date.today().isoformat())[:10],
        'time': str(body.get('time') or datetime.now().strftime('%H:%M'))[:5],
        'name': str(body.get('name', 'Custom')),
        'duration': clean_num(body.get('duration')),
        'intensity': str(body.get('intensity', 'Moderate')),
        'notes': str(body.get('notes', '')),
        'exercises': exercises,
    })
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/supplements')
def log_supplement():
    body = request.get_json(force=True)
    d = store.load()
    d['supplements'].append({
        'date': str(body.get('date') or date.today().isoformat())[:10],
        'name': str(body.get('name', 'Other')),
        'time': str(body.get('time', 'Morning')),
        'taken': bool(body.get('taken', True)),
    })
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/schedule')
def add_schedule():
    body = request.get_json(force=True)
    entry = {'name': str(body.get('name', '')).strip(), 'time': str(body.get('time', '')).strip()}
    if not entry['name'] or not entry['time']:
        return _err('Name and time are required.')
    d = store.load()
    if entry in d['supplement_schedule']:
        return _err('Already on the schedule.')
    d['supplement_schedule'].append(entry)
    store.save(d)
    return jsonify({'ok': True})


@bp.delete('/schedule/<int:idx>')
def remove_schedule(idx):
    d = store.load()
    if not 0 <= idx < len(d['supplement_schedule']):
        return _err('No such schedule item.', 404)
    d['supplement_schedule'].pop(idx)
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/checklist/toggle')
def toggle_checklist():
    body = request.get_json(force=True)
    name, time_of_day = str(body.get('name', '')), str(body.get('time', ''))
    today = date.today().isoformat()
    d = store.load()
    match = [s for s in d['supplements']
             if s['date'] == today and s['name'] == name
             and s['time'] == time_of_day and s.get('taken')]
    if match:
        d['supplements'] = [s for s in d['supplements'] if s not in match]
    else:
        d['supplements'].append({'date': today, 'name': name, 'time': time_of_day, 'taken': True})
    store.save(d)
    return jsonify({'ok': True, 'taken': not match})


@bp.post('/deals')
def deals():
    body = request.get_json(force=True)
    items = str(body.get('items', '')).strip()
    location = str(body.get('location', '')).strip()
    if not items:
        return _err('List some items to shop for first.')
    try:
        found = ai.find_deals(items, location)
    except Exception as e:
        return _err(e, 502)
    d = store.load()
    d['deals'] = {'fetched_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                  'items': items, 'location': location, 'results': found}
    store.save(d)
    return jsonify(d['deals'])


@bp.post('/coach')
def coach():
    d = store.load()
    week_ago = (date.today().toordinal() - 7)
    cutoff = date.fromordinal(week_ago).isoformat()
    week_data = {
        'profile': d['profile'],
        'meals': [m for m in d['meals'] if m['date'] >= cutoff],
        'workouts': [w for w in d['workouts'] if w['date'] >= cutoff],
        'supplements': [s for s in d['supplements'] if s['date'] >= cutoff],
        'weigh_ins': [w for w in d['weights'] if w['date'] >= cutoff],
    }
    if not week_data['meals'] and not week_data['workouts']:
        return _err("Log some meals or workouts first — there's nothing from the last 7 days to review.")
    coach = get_coach(d['profile'].get('coach', DEFAULT_COACH))
    try:
        return jsonify({'summary': ai.coaching_summary(week_data, persona_prompt(coach)),
                        'coach': coach['id']})
    except Exception as e:
        return _err(e, 502)


@bp.put('/entry/<kind>/<int:idx>')
def update_entry(kind, idx):
    if kind not in EDITABLE_KINDS:
        return _err('Unknown kind.', 404)
    body = request.get_json(force=True)
    d = store.load()
    entries = d[kind]
    if not 0 <= idx < len(entries):
        return _err('No such entry.', 404)
    if kind == 'meals':
        entry = _normalize_meal({**entries[idx], **body})
        if not entry['name']:
            return _err('Meal name is required.')
        entries[idx] = entry
    elif kind == 'weights':
        entries[idx] = {'date': str(body.get('date', entries[idx]['date']))[:10],
                        'weight': clean_num(body.get('weight', entries[idx]['weight']), float)}
        entries.sort(key=lambda w: w['date'])
        if entries:
            d['profile']['weight'] = entries[-1]['weight']
    else:
        entries[idx] = {**entries[idx], **body}
    store.save(d)
    return jsonify({'ok': True})


@bp.delete('/entry/<kind>/<int:idx>')
def delete_entry(kind, idx):
    if kind not in EDITABLE_KINDS:
        return _err('Unknown kind.', 404)
    d = store.load()
    entries = d[kind]
    if not 0 <= idx < len(entries):
        return _err('No such entry.', 404)
    entries.pop(idx)
    if kind == 'weights' and entries:
        entries.sort(key=lambda w: w['date'])
        d['profile']['weight'] = entries[-1]['weight']
    store.save(d)
    return jsonify({'ok': True})


@bp.get('/export/<kind>.csv')
def export_csv(kind):
    if kind not in EDITABLE_KINDS:
        return _err('Unknown kind.', 404)
    d = store.load()
    rows = d[kind]
    buf = io.StringIO()
    if rows:
        fields = sorted({k for r in rows for k in r})
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: (str(v) if isinstance(v, (list, dict)) else v)
                             for k, v in r.items()})
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={kind}.csv'})
