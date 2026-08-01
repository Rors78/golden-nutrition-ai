"""JSON API consumed by the single-page frontend."""
import csv
import io
import json
import secrets
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, Response

from . import ai, data as store, notify, stats
from .coaches import DEFAULT_COACH, ROSTER, get_coach, persona_prompt
from .data import clean_num
from .remedies_kb import kb_stats, load_kb, search_kb
from .supplement_kb import KB

bp = Blueprint('api', __name__, url_prefix='/api')

EDITABLE_KINDS = ('meals', 'workouts', 'supplements', 'weights', 'vitals')


def _err(message, status=400):
    return jsonify({'error': str(message)}), status


VITAL_ALIASES = {
    'steps': ('steps', 'step_count', 'stepCount'),
    'resting_hr': ('resting_hr', 'restingHeartRate', 'resting_heart_rate', 'rhr', 'heart_rate'),
    'hrv_ms': ('hrv_ms', 'hrv', 'heartRateVariability'),
    'sleep_h': ('sleep_h', 'sleep_hours', 'sleepHours'),
    'bp_sys': ('bp_sys', 'systolic', 'bloodPressureSystolic'),
    'bp_dia': ('bp_dia', 'diastolic', 'bloodPressureDiastolic'),
}


def _normalize_vital(raw):
    """Accept flexible payloads (Health Connect exporters vary) → one clean row."""
    day = str(raw.get('date') or date.today().isoformat())[:10]
    row = {'date': day}
    for field, aliases in VITAL_ALIASES.items():
        for a in aliases:
            if raw.get(a) is not None and raw.get(a) != '':
                cast = float if field in ('sleep_h', 'hrv_ms') else int
                row[field] = store.clean_num(raw[a], cast)
                break
    # sleep sometimes arrives in minutes
    if 'sleep_h' not in row and raw.get('sleep_minutes') not in (None, ''):
        row['sleep_h'] = round(store.clean_num(raw['sleep_minutes'], float) / 60, 2)
    return row


def _merge_vital(d, row):
    """One row per date; new non-null fields overwrite, others survive."""
    for v in d['vitals']:
        if v['date'] == row['date']:
            v.update({k: val for k, val in row.items() if k != 'date'})
            return
    d['vitals'].append(row)
    d['vitals'].sort(key=lambda v: v['date'])


@bp.get('/state')
def get_state():
    d = store.load()
    if not d['settings'].get('ingest_token'):
        d['settings']['ingest_token'] = secrets.token_hex(8)
        store.save(d)
    note, store.last_recovery_note = store.last_recovery_note, None
    return jsonify({
        'profile': d['profile'],
        'meals': d['meals'],
        'workouts': d['workouts'],
        'supplements': d['supplements'],
        'schedule': d['supplement_schedule'],
        'weights': sorted(d['weights'], key=lambda w: w['date']),
        'vitals': sorted(d.get('vitals', []), key=lambda v: v['date']),
        'settings': d['settings'],
        'briefing': d.get('briefing'),
        'deals': d.get('deals'),
        'shopping_list': d.get('shopping_list', []),
        'watches': d.get('watches', []),
        'supp_advice': d.get('supp_advice'),
        'kb': KB,
        'remedies_unlocked': bool(d['settings'].get('remedies_unlocked')),
        'remedies_stats': kb_stats(),
        'coaches': ROSTER,
        'coach': d['profile'].get('coach', DEFAULT_COACH),
        'coach_chat': d.get('coach_chat', []),
        'reviews': (d.get('reviews') or [])[-5:],
        'plan': d.get('plan'),
        'stats': {
            'today': stats.today_summary(d),
            'weight': stats.weight_stats(d),
            'weight_extras': stats.weight_extras(d),
            'insights': stats.insights(d),
            'progression': stats.progression(d),
            'quick_meals': stats.quick_meals(d),
            'nutrition': stats.nutrition_trend(d),
            'checklist': stats.checklist(d),
            'adherence': stats.supplement_adherence(d),
            'adherence_series': stats.adherence_series(d),
            'training': stats.training_summary(d),
            'muscle_balance': stats.muscle_balance(d),
            'recent_prs': stats.recent_prs(d),
            'weekly_volume': stats.weekly_volume(d),
            'vitals': stats.vitals_summary(d),
            'readiness': stats.readiness(d),
            'readiness_series': stats.readiness_series(d),
            'vitals_weeks': stats.vitals_weeks(d),
            'step_stats': stats.step_stats(d),
            'achievements': stats.achievements(d),
            'plan_progress': stats.plan_progress(d),
            'dashboard': stats.dashboard_extras(d),
            'watch_insights': stats.watch_insights(d),
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
        'age': clean_num(body.get('age')),
        'sex': str(body.get('sex', '')),
        'height_in': clean_num(body.get('height_in')),
        'weight': clean_num(body.get('weight'), float),
        'goal_weight': clean_num(body.get('goal_weight'), float),
        'daily_protein_g': clean_num(body.get('daily_protein_g')),
        'daily_calories': clean_num(body.get('daily_calories')),
        'notes': str(body.get('notes', '')),
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


@bp.post('/meals/repeat-yesterday')
def repeat_yesterday():
    d = store.load()
    yday = (date.today() - timedelta(days=1)).isoformat()
    src = [m for m in d['meals'] if m['date'] == yday]
    if not src:
        return _err('No meals logged yesterday.')
    today = date.today().isoformat()
    for m in src:
        d['meals'].append({**m, 'date': today, 'notes': 'Repeated from yesterday'})
    store.save(d)
    return jsonify({'ok': True, 'count': len(src)})


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


@bp.post('/meals/suggest')
def suggest_meals():
    d = store.load()
    coach = get_coach(d['profile'].get('coach', DEFAULT_COACH))
    today = stats.today_summary(d)
    totals = today['totals']
    remaining = {
        'protein_g': max(0, d['profile'].get('daily_protein_g', 150) - totals['protein']),
        'calories': max(0, d['profile'].get('daily_calories', 2000) - totals['calories']),
    }
    context = json.dumps({
        'time_now': datetime.now().strftime('%H:%M'),
        'remaining_today': remaining,
        'eaten_today': [{'name': m['name'], 'protein': m.get('protein', 0),
                         'calories': m.get('calories', 0)}
                        for m in sorted(
                            (m for m in d['meals'] if m['date'] == date.today().isoformat()),
                            key=lambda m: m.get('time', ''))],
        'todays_macros_so_far': totals,
        'recent_regulars': [m['name'] for m in stats.quick_meals(d, limit=8)],
    })
    try:
        return jsonify({'suggestions': ai.suggest_meals(d['profile'],
                                                        persona_prompt(coach), context),
                        'coach': coach['id']})
    except Exception as e:
        return _err(e, 502)


@bp.post('/meals/photo')
def meals_photo():
    """Photo of the plate → Claude vision → macro estimates (review, then add)."""
    import base64
    import tempfile as tf
    body = request.get_json(force=True)
    data_url = str(body.get('image', ''))
    if ';base64,' not in data_url:
        return _err('Send the photo as a base64 data URL.')
    header, b64 = data_url.split(';base64,', 1)
    suffix = '.png' if 'png' in header else '.jpg'
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return _err('That image data did not decode.')
    if len(raw) > 12 * 1024 * 1024:
        return _err('Photo too large — keep it under 12 MB.')
    path = None
    try:
        with tf.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(raw)
            path = f.name
        return jsonify({'meals': ai.parse_meal_photo(path)})
    except Exception as e:
        return _err(e, 502)
    finally:
        if path:
            try:
                import os as _os
                _os.unlink(path)
            except OSError:
                pass


@bp.post('/voice')
def voice():
    """Voice transcript → routed action → executed. Hands-free logging."""
    body = request.get_json(force=True)
    transcript = str(body.get('text', '')).strip()
    if not transcript:
        return _err('Empty transcript.')
    try:
        route = ai.route_voice(transcript)
    except Exception as e:
        return _err(e, 502)
    action = route.get('action')
    d = store.load()

    if action == 'meal':
        desc = str(route.get('description', transcript)).strip()
        try:
            meals = ai.parse_meals(desc)
        except Exception as e:
            return _err(e, 502)
        now = datetime.now().strftime('%H:%M')
        for m in meals:
            d['meals'].append(_normalize_meal({**m, 'date': date.today().isoformat(),
                                               'time': now, 'notes': 'Logged by voice'}))
        store.save(d)
        total_p = sum(m['protein'] for m in meals)
        return jsonify({'ok': True, 'action': 'meal',
                        'message': f"Logged {len(meals)} item(s) — {total_p}g protein."})

    if action == 'weight':
        lbs = clean_num(route.get('pounds'), float)
        if lbs <= 0:
            return _err("Didn't catch the weight — try 'weigh in at 200 pounds'.")
        day = date.today().isoformat()
        d['weights'] = [w for w in d['weights'] if w['date'] != day]
        d['weights'].append({'date': day, 'weight': lbs})
        d['weights'].sort(key=lambda w: w['date'])
        d['profile']['weight'] = d['weights'][-1]['weight']
        store.save(d)
        return jsonify({'ok': True, 'action': 'weight',
                        'message': f'Weigh-in logged: {lbs:g} lbs.'})

    if action == 'supplement':
        name = str(route.get('name', '')).strip() or 'Other'
        time_of_day = str(route.get('time', 'Morning')).strip() or 'Morning'
        d['supplements'].append({'date': date.today().isoformat(), 'name': name,
                                 'time': time_of_day, 'taken': True})
        store.save(d)
        return jsonify({'ok': True, 'action': 'supplement',
                        'message': f'{name} logged ({time_of_day}).'})

    return _err(route.get('reason', "Didn't understand that — try 'log chicken and rice' "
                "or 'weigh in at 200'."))


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


@bp.post('/vitals')
def add_vitals():
    row = _normalize_vital(request.get_json(force=True))
    if len(row) == 1:
        return _err('No vital readings in that entry.')
    d = store.load()
    _merge_vital(d, row)
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/ingest')
def ingest():
    """Webhook for wearable exporters (Health Connect sync apps, scripts).
    POST /api/ingest?token=... with one reading or {"days": [...]}."""
    d = store.load()
    token = d['settings'].get('ingest_token')
    if not token or request.args.get('token') != token:
        return _err('Bad or missing ingest token.', 401)
    body = request.get_json(force=True, silent=True) or {}
    rows = body.get('days') if isinstance(body.get('days'), list) else [body]
    merged = 0
    for raw in rows:
        row = _normalize_vital(raw if isinstance(raw, dict) else {})
        if len(row) > 1:
            _merge_vital(d, row)
            merged += 1
    if not merged:
        return _err('No recognizable vital fields in the payload.')
    store.save(d)
    return jsonify({'ok': True, 'merged': merged})


@bp.post('/settings')
def save_settings():
    body = request.get_json(force=True)
    d = store.load()
    s = d['settings']
    if 'ntfy_topic' in body:
        s['ntfy_topic'] = str(body['ntfy_topic']).strip()
    if 'ntfy_server' in body:
        s['ntfy_server'] = str(body['ntfy_server']).strip() or 'https://ntfy.sh'
    if 'daily_steps' in body:
        s['daily_steps'] = clean_num(body['daily_steps']) or 8000
    if 'sleep_target' in body:
        s['sleep_target'] = clean_num(body['sleep_target'], float) or 7.5
    store.save(d)
    return jsonify({'ok': True, 'settings': s})


@bp.post('/notify/test')
def notify_test():
    d = store.load()
    try:
        sent = notify.push(d['settings'], 'Golden Nutrition AI',
                           'Coach line is live. Notifications will land here.')
    except Exception as e:
        return _err(f'Push failed: {e}', 502)
    if not sent:
        return _err('Set an ntfy topic first.')
    return jsonify({'ok': True})


@bp.post('/briefing')
def briefing():
    d = store.load()
    coach = get_coach(d['profile'].get('coach', DEFAULT_COACH))
    today = date.today().isoformat()
    week = (d.get('plan') or {}).get('plan', {}).get('week', [])
    day_name = datetime.now().strftime('%A')
    plan_day = next((x for x in week if day_name.lower() in x.get('day', '').lower()), None)
    vs = stats.vitals_summary(d)
    context = json.dumps({
        'weekday': day_name,
        'planned_session': plan_day,
        'readiness': stats.readiness(d),
        'yesterday_vitals': (vs.get('series') or [])[-1:] if vs.get('has_data') else [],
        'goals': {'protein_g': d['profile'].get('daily_protein_g'),
                  'calories': d['profile'].get('daily_calories'),
                  'steps': d['settings'].get('daily_steps')},
        'stack_adherence_7d': stats.supplement_adherence(d),
        'supplements_running_low': [f"{i['name']} ({i['servings_left']} left)"
                                    for i in d['supplement_schedule']
                                    if i.get('servings_left') is not None
                                    and i['servings_left'] <= 7],
        'latest_weight': (sorted(d['weights'], key=lambda w: w['date'])[-1]
                          if d['weights'] else None),
    })
    try:
        text = ai.daily_briefing(d['profile'], persona_prompt(coach), context)
    except Exception as e:
        return _err(e, 502)
    d['briefing'] = {'date': today, 'coach': coach['id'], 'text': text}
    store.save(d)
    try:
        notify.push(d['settings'], f"{coach['name']} — morning briefing", text[:400])
    except Exception:
        pass  # the briefing still lands in the app if the push fails
    return jsonify(d['briefing'])


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
    name = str(body.get('name', '')).strip()
    time_of_day = str(body.get('time', '')).strip()
    if not name or not time_of_day:
        return _err('Name and time are required.')
    d = store.load()
    if any(i['name'] == name and i['time'] == time_of_day
           for i in d['supplement_schedule']):
        return _err('Already on the schedule.')
    entry = {'name': name, 'time': time_of_day,
             'dose': str(body.get('dose', '')).strip()}
    servings = clean_num(body.get('servings'))
    if servings > 0:
        entry['servings_left'] = servings
    d['supplement_schedule'].append(entry)
    store.save(d)
    return jsonify({'ok': True})


@bp.put('/schedule/<int:idx>')
def update_schedule(idx):
    """Edit dose or restock servings on a stack item."""
    body = request.get_json(force=True)
    d = store.load()
    if not 0 <= idx < len(d['supplement_schedule']):
        return _err('No such schedule item.', 404)
    item = d['supplement_schedule'][idx]
    if 'dose' in body:
        item['dose'] = str(body['dose']).strip()
    if 'servings' in body:
        servings = clean_num(body['servings'])
        if servings > 0:
            item['servings_left'] = servings
        else:
            item.pop('servings_left', None)
    store.save(d)
    return jsonify({'ok': True, 'item': item})


@bp.delete('/schedule/<int:idx>')
def remove_schedule(idx):
    d = store.load()
    if not 0 <= idx < len(d['supplement_schedule']):
        return _err('No such schedule item.', 404)
    d['supplement_schedule'].pop(idx)
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/supplements/advice')
def supplements_advice():
    d = store.load()
    coach = get_coach(d['profile'].get('coach', DEFAULT_COACH))
    ins = stats.insights(d)

    today = date.today().isoformat()
    week_ago = (date.today().toordinal() - 7)
    cutoff = date.fromordinal(week_ago).isoformat()
    recent_supps = [s for s in d['supplements'] if s['date'] >= cutoff]
    missed = sum(1 for s in recent_supps if not s.get('taken', True))

    context = {
        'current_stack': d.get('supplement_schedule', []),
        'supplements_logged_last_7d': len(recent_supps),
        'missed_last_7d': missed,
        'workouts_last_7d': ins.get('workout_count', 0),
        'workout_types_last_7d': sorted({w['name'] for w in d['workouts'] if w['date'] >= cutoff}),
    }
    if ins.get('has_data'):
        context['diet_last_7d'] = {
            'avg_daily_protein_g': ins['avg_daily_protein'],
            'protein_goal_g': ins['protein_goal'],
            'avg_carbs_g_day': ins['avg_carbs_day'],
            'avg_fat_g_day': ins['avg_fat_day'],
            'avg_fiber_g_day': ins['avg_fiber_day'],
            'days_logged': ins['days_logged'],
        }
    try:
        advice = ai.supplement_advice(d['profile'], persona_prompt(coach), json.dumps(context))
    except Exception as e:
        return _err(e, 502)
    d['supp_advice'] = {'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                        'coach': coach['id'], 'advice': advice}
    store.save(d)
    return jsonify(d['supp_advice'])


REMEDY_UNLOCK_KEY = 'GOLDEN'  # placeholder gate — swap for real payments when hosted


def _remedies_locked(d):
    return not d['settings'].get('remedies_unlocked')


@bp.post('/remedies/unlock')
def remedies_unlock():
    body = request.get_json(force=True)
    if str(body.get('key', '')).strip().upper() != REMEDY_UNLOCK_KEY:
        return _err('That key did not unlock the Apothecary.', 403)
    d = store.load()
    d['settings']['remedies_unlocked'] = True
    store.save(d)
    return jsonify({'ok': True})


@bp.get('/remedies')
def remedies():
    d = store.load()
    if _remedies_locked(d):
        return _err('The Apothecary is locked.', 403)
    return jsonify({'remedies': load_kb(), **kb_stats()})


@bp.post('/remedies/ask')
def remedies_ask():
    d = store.load()
    if _remedies_locked(d):
        return _err('The Apothecary is locked.', 403)
    question = str(request.get_json(force=True).get('question', '')).strip()
    if not question:
        return _err('Ask a question first.')
    matches = search_kb(question)
    if not matches:
        return _err("Nothing in the archive matches that — try different words "
                    "(e.g. 'sleep', 'joint pain', 'blood pressure').")
    try:
        answer = ai.remedy_answer(d['profile'], question, matches)
    except Exception as e:
        return _err(e, 502)
    return jsonify({'answer': answer, 'sources': [m['name'] for m in matches]})


@bp.post('/checklist/toggle')
def toggle_checklist():
    body = request.get_json(force=True)
    name, time_of_day = str(body.get('name', '')), str(body.get('time', ''))
    today = date.today().isoformat()
    d = store.load()
    match = [s for s in d['supplements']
             if s['date'] == today and s['name'] == name
             and s['time'] == time_of_day and s.get('taken')]
    sched = next((i for i in d['supplement_schedule']
                  if i['name'] == name and i['time'] == time_of_day), None)
    if match:
        d['supplements'] = [s for s in d['supplements'] if s not in match]
        if sched and sched.get('servings_left') is not None:
            sched['servings_left'] += 1  # un-ticking puts the serving back
    else:
        d['supplements'].append({'date': today, 'name': name, 'time': time_of_day, 'taken': True})
        if sched and sched.get('servings_left') is not None:
            sched['servings_left'] = max(0, sched['servings_left'] - 1)
    store.save(d)
    return jsonify({'ok': True, 'taken': not match})


def _parse_price(text):
    """'$49.99', '£1,299', '2 for $30' → first numeric price found, or None."""
    import re
    m = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)', str(text))
    if not m:
        return None
    try:
        return float(m.group(1).replace(',', ''))
    except ValueError:
        return None


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
    d['settings']['deals_location'] = location  # remember store preferences
    store.save(d)
    return jsonify(d['deals'])


@bp.post('/shopping')
def shopping_add():
    body = request.get_json(force=True)
    items = body.get('items') if isinstance(body.get('items'), list) else [body.get('item')]
    d = store.load()
    added = 0
    existing = {i.lower() for i in d['shopping_list']}
    for raw in items:
        item = str(raw or '').strip()
        if item and item.lower() not in existing:
            d['shopping_list'].append(item)
            existing.add(item.lower())
            added += 1
    if not added:
        return _err('Nothing new to add.')
    store.save(d)
    return jsonify({'ok': True, 'added': added})


@bp.delete('/shopping/<int:idx>')
def shopping_remove(idx):
    d = store.load()
    if not 0 <= idx < len(d['shopping_list']):
        return _err('No such item.', 404)
    d['shopping_list'].pop(idx)
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/watches')
def watch_add():
    body = request.get_json(force=True)
    item = str(body.get('item', '')).strip()
    if not item:
        return _err('Watch needs an item name.')
    d = store.load()
    if any(w['item'].lower() == item.lower() for w in d['watches']):
        return _err('Already watching that item.')
    price_num = _parse_price(body.get('price'))
    point = None
    if price_num is not None:
        point = {'date': date.today().isoformat(), 'price': price_num,
                 'raw': str(body.get('price', '')),
                 'store': str(body.get('store', '')), 'url': str(body.get('url', ''))}
    d['watches'].append({'item': item, 'created': date.today().isoformat(),
                         'history': [point] if point else []})
    store.save(d)
    return jsonify({'ok': True})


@bp.delete('/watches/<int:idx>')
def watch_remove(idx):
    d = store.load()
    if not 0 <= idx < len(d['watches']):
        return _err('No such watch.', 404)
    d['watches'].pop(idx)
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/watches/recheck')
def watches_recheck():
    """Re-search every watched item, record price points, push on drops.
    Called from the UI or scripts/price_watch.py on a timer."""
    d = store.load()
    if not d['watches']:
        return _err('No price watches yet — watch a deal first.')
    items = ', '.join(w['item'] for w in d['watches'])
    try:
        found = ai.find_deals(items, d['settings'].get('deals_location', ''))
    except Exception as e:
        return _err(e, 502)

    def match(watch):
        tokens = [t for t in watch['item'].lower().split() if len(t) > 2]
        best, best_score = None, 0
        for deal in found:
            hay = f"{deal['item']}".lower()
            score = sum(1 for t in tokens if t in hay)
            if score > best_score:
                best, best_score = deal, score
        return best if best_score else None

    today = date.today().isoformat()
    drops, updated = [], 0
    for w in d['watches']:
        deal = match(w)
        if not deal:
            continue
        price_num = _parse_price(deal.get('price'))
        if price_num is None:
            continue
        prev_best = min((p['price'] for p in w['history']), default=None)
        w['history'] = [p for p in w['history'] if p['date'] != today]
        w['history'].append({'date': today, 'price': price_num,
                             'raw': deal.get('price', ''),
                             'store': deal.get('store', ''), 'url': deal.get('url', '')})
        w['history'] = w['history'][-60:]  # keep two months of points
        updated += 1
        if prev_best is not None and price_num < prev_best * 0.98:
            drops.append({'item': w['item'], 'price': deal.get('price', ''),
                          'store': deal.get('store', ''), 'was': prev_best})
    store.save(d)
    if drops:
        lines = '; '.join(f"{x['item']} now {x['price']} at {x['store']}" for x in drops)
        try:
            notify.push(d['settings'], 'Price drop on your watchlist', lines, priority='high')
        except Exception:
            pass
    return jsonify({'ok': True, 'updated': updated, 'drops': drops})


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
        'vitals': [v for v in d.get('vitals', []) if v['date'] >= cutoff],
    }
    if not week_data['meals'] and not week_data['workouts']:
        return _err("Log some meals or workouts first — there's nothing from the last 7 days to review.")
    coach = get_coach(d['profile'].get('coach', DEFAULT_COACH))
    try:
        summary = ai.coaching_summary(week_data, persona_prompt(coach))
    except Exception as e:
        return _err(e, 502)
    reviews = d.setdefault('reviews', [])
    reviews.append({'date': date.today().isoformat(), 'coach': coach['id'],
                    'summary': summary})
    d['reviews'] = reviews[-12:]
    store.save(d)
    return jsonify({'summary': summary, 'coach': coach['id']})


@bp.post('/coach/chat')
def coach_chat():
    message = str(request.get_json(force=True).get('message', '')).strip()
    if not message:
        return _err('Say something to your coach first.')
    d = store.load()
    coach = get_coach(d['profile'].get('coach', DEFAULT_COACH))
    today = stats.today_summary(d)
    snapshot = json.dumps({
        'time_now': datetime.now().strftime('%A %H:%M'),
        'today_macros': today['totals'],
        'goals': {'protein_g': d['profile'].get('daily_protein_g'),
                  'calories': d['profile'].get('daily_calories')},
        'readiness': stats.readiness(d),
        'training_7d': stats.training_summary(d),
        'plan_today': next((x for x in (d.get('plan') or {}).get('plan', {}).get('week', [])
                            if datetime.now().strftime('%A').lower() in str(x.get('day', '')).lower()), None),
        'plan_progress': stats.plan_progress(d),
        'latest_weight': (sorted(d['weights'], key=lambda w: w['date'])[-1]
                          if d['weights'] else None),
        'profile_notes': d['profile'].get('notes', ''),
    })
    history = d.get('coach_chat', [])
    try:
        reply = ai.coach_chat(persona_prompt(coach), history, message, snapshot)
    except Exception as e:
        return _err(e, 502)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    history.append({'role': 'user', 'text': message, 'ts': now})
    history.append({'role': 'coach', 'text': reply, 'ts': now, 'coach': coach['id']})
    d['coach_chat'] = history[-40:]
    store.save(d)
    return jsonify({'reply': reply, 'coach': coach['id']})


@bp.delete('/coach/chat')
def coach_chat_clear():
    d = store.load()
    d['coach_chat'] = []
    store.save(d)
    return jsonify({'ok': True})


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
    elif kind == 'vitals':
        row = _normalize_vital(body)
        merged = {**entries[idx], **row}
        # blanking a field in the edit removes the reading entirely
        for f, aliases in VITAL_ALIASES.items():
            if any(str(body.get(a, 'x')) == '' for a in aliases):
                merged.pop(f, None)
        entries[idx] = merged
        entries.sort(key=lambda v: v['date'])
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
