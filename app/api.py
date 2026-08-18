"""JSON API consumed by the single-page frontend."""
import copy
import csv
import hashlib
import io
import json
import os
import platform
import re
import secrets
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, request, Response, send_from_directory

from . import ai, data as store, food_db, importer, notify, stats
from .coaches import DEFAULT_COACH, ROSTER, get_coach, persona_prompt
from .data import MACRO_FIELDS, clean_num
from .remedies_kb import kb_stats, load_kb, remedy_of_day, search_kb
from .supplement_kb import KB

bp = Blueprint('api', __name__, url_prefix='/api')

EDITABLE_KINDS = ('meals', 'workouts', 'supplements', 'weights', 'vitals',
                  'measurements')

MEASURE_FIELDS = ('neck_in', 'chest_in', 'waist_in', 'hips_in', 'arm_in', 'thigh_in')


def _err(message, status=400):
    return jsonify({'error': str(message)}), status


def _privilege():
    """How much environment an AI subprocess started by this request may inherit.

    Scheduled jobs set X-GNA-Unattended; nobody is watching what they do, so
    they run constrained (see ai._cli_env). Requests from the UI have a human
    present and run interactive. Defaulting to constrained would be safer still,
    but would silently change interactive behavior, so the unattended callers
    declare themselves and the tests assert they do.
    """
    return ('constrained' if request.headers.get('X-GNA-Unattended')
            else 'interactive')


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
        'measurements': sorted(d.get('measurements', []), key=lambda m: m['date']),
        'photos': d.get('photos', []),
        'recipes': d.get('recipes', []),
        'settings': d['settings'],
        'briefing': d.get('briefing'),
        'deals': d.get('deals'),
        'shopping_list': d.get('shopping_list', []),
        'watches': d.get('watches', []),
        'supp_advice': d.get('supp_advice'),
        'kb': KB,
        'remedies_unlocked': bool(d['settings'].get('remedies_unlocked')),
        'remedies_stats': kb_stats(),
        'remedy_cabinet': d.get('remedy_cabinet', []),
        'remedy_of_day': (remedy_of_day()
                          if d['settings'].get('remedies_unlocked') else None),
        'coaches': ROSTER,
        'coach': d['profile'].get('coach', DEFAULT_COACH),
        'coach_chat': d.get('coach_chat', []),
        'reviews': (d.get('reviews') or [])[-5:],
        'plan': d.get('plan'),
        'stats': {
            'today': stats.today_summary(d),
            'weight': stats.weight_stats(d),
            'weight_extras': stats.weight_extras(d),
            'body_comp': stats.body_comp(d),
            'strain': stats.training_strain(d),
            'energy': stats.energy_balance(d),
            'next_targets': stats.next_targets(d),
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
            'coach_fit': stats.coach_fit(d),
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


@bp.post('/profile/calorie-goal')
def set_calorie_goal():
    """One-tap adoption of the adaptive-TDEE calorie recommendation."""
    cal = clean_num(request.get_json(force=True).get('calories'))
    if not 1000 <= cal <= 6000:
        return _err('Calorie goal must be between 1000 and 6000.')
    d = store.load()
    d['profile']['daily_calories'] = cal
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


@bp.post('/vessel/preview')
def vessel_preview():
    """Derive a VESSEL payload from a supplied dataset, without saving it.

    Demo mode needs a full twelve-week figure on an install that has logged
    nothing. Rather than reimplement Navy BF, ACWR and the change map in JS —
    which would create the second source of truth the whole architecture
    avoids — it posts a dataset here and gets the same derived payload the
    real endpoint returns. Nothing is written.
    """
    body = request.get_json(force=True, silent=True) or {}
    if not isinstance(body, dict):
        return _err('Preview needs a data object.')
    d = copy.deepcopy(store.DEFAULT_DATA)
    for key in ('profile', 'settings'):
        if isinstance(body.get(key), dict):
            d[key].update(body[key])
    for key in ('meals', 'workouts', 'weights', 'vitals', 'measurements',
                'supplements', 'supplement_schedule'):
        if isinstance(body.get(key), list):
            d[key] = body[key]
    # Every derived block, not just the figure: the demo swaps client state,
    # and a dashboard computed from the real (empty) file would contradict the
    # demo data sitting beside it.
    return jsonify({
        'vessel': stats.vessel(d),
        'stats': {
            'today': stats.today_summary(d),
            'weight': stats.weight_stats(d),
            'weight_extras': stats.weight_extras(d),
            'body_comp': stats.body_comp(d),
            'strain': stats.training_strain(d),
            'energy': stats.energy_balance(d),
            'next_targets': stats.next_targets(d),
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
            'coach_fit': stats.coach_fit(d),
        },
    })


@bp.get('/vessel')
def vessel():
    """Fully-derived payload for the VESSEL instrument.

    The canvas is a pure function of this JSON and computes nothing — so the
    renderer can be verified against fixtures with no backend, and the backend
    with no canvas, and neither can lie about the other.
    """
    return jsonify(stats.vessel(store.load()))


@bp.get('/system')
def system_pulse():
    """Health of the machinery guarding the user's data: backups, AI backend,
    server, data-file stats. Powers the footer's System pulse dialog."""
    d = store.load()
    df = store.DATA_FILE
    file_info = {'bytes': 0, 'modified': None}
    if df.exists():
        st = df.stat()
        file_info = {'bytes': st.st_size,
                     'modified': datetime.fromtimestamp(st.st_mtime).isoformat(timespec='minutes')}
    counts = {k: len(d.get(k) or []) for k in
              ('meals', 'workouts', 'supplements', 'weights', 'vitals')}
    warnings = []
    bdir = df.resolve().parent / 'backups'
    snaps = sorted(bdir.glob('nutrition_data-*.json')) if bdir.is_dir() else []
    backups = {'count': len(snaps), 'newest': None, 'age_days': None}
    if snaps:
        newest = snaps[-1]
        age = round((datetime.now().timestamp() - newest.stat().st_mtime) / 86400, 1)
        backups.update({'newest': newest.name, 'age_days': age})
        if age > 2:
            warnings.append(f'Newest backup is {age} days old — is the nightly '
                            'backup job still running?')
    else:
        warnings.append('No backups yet — install the nightly backup job '
                        '(scripts/install_backup_timer.sh or '
                        'scripts\\install_windows_tasks.ps1).')
    if not ai.backend_name():
        warnings.append('No AI backend — install Claude Code or set ANTHROPIC_API_KEY.')
    topic_state = store.secret_state(d, 'ntfy_topic')
    if topic_state == store.SECRET_CLEARED_BY_RESTORE:
        # Distinct from never-configured: this one WAS working and a restore
        # dropped it. Saying so is the difference between "set this up" and
        # "your push channel silently stopped".
        warnings.append('Notification topic was cleared by a restore — backups '
                        'do not carry it. Re-enter it in Vitals or the sentinel, '
                        'briefing, and price-watch jobs stay silent.')
    elif topic_state == store.SECRET_NEVER_SET:
        warnings.append('No notification topic — the sentinel, briefing, and '
                        'price-watch jobs have nowhere to push. Set one in Vitals.')
    quiet = stats.days_since_user_entry(d)
    if quiet is not None and quiet >= 3:
        warnings.append(f'Nothing logged in {quiet} days — the adaptive engines '
                        'run on recent history.')
    return jsonify({
        'data_file': {**file_info, 'counts': counts, 'path': str(df.resolve())},
        'backups': backups,
        'briefing_date': (d.get('briefing') or {}).get('date'),
        'push_channel': bool((d['settings'].get('ntfy_topic') or '').strip()),
        'days_since_entry': stats.days_since_user_entry(d),
        'ai_backend': ai.backend_name(),
        'server': request.environ.get('SERVER_SOFTWARE') or 'Flask dev server',
        'platform': f'Python {platform.python_version()} on {sys.platform}',
        'warnings': warnings,
    })


@bp.get('/food/barcode/<code>')
def food_barcode(code):
    try:
        hit = food_db.lookup_barcode(code)
    except ValueError as e:
        return _err(e)
    except Exception as e:
        return _err(f'Barcode lookup failed: {e}', 502)
    if not hit:
        return _err('No product found for that barcode.', 404)
    return jsonify(hit)


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


# ── quick log: one box, everything ──────────────────────────────────────────
#
# The app's analytics are all dormant until data exists, and the thing keeping
# the file empty is that every entry costs a tab change and a form. This is one
# text box that takes anything.
#
# Deliberately deterministic FIRST. The common shapes — "215", "waist 37.2",
# "bench 225x5x3" — are unambiguous, and a regex answers them instantly,
# offline, with no API key and no per-call cost. AI is the fallback for prose
# ("two eggs and toast"), not the default path. An app that needs a model to
# record a number the user just typed is slower and more fragile than one that
# does not.
QUICK_PATTERNS = [
    # a bare number in a plausible bodyweight range is a weigh-in
    (r'^(?:weigh(?:ed|s|ing)?(?:\s+in)?(?:\s+at)?\s*)?(\d{2,3}(?:\.\d)?)\s*(?:lbs?|pounds?)?$',
     'weight'),
    # "waist 37.2" / "waist 37.2in" — any of the six tape sites
    (r'^(neck|chest|waist|hips?|arm|thigh)\s*[:=]?\s*(\d{1,2}(?:\.\d{1,2})?)\s*(?:in|"|inches)?$',
     'measurement'),
    # "bench 225x5" or "bench press 225 x 5 x 3" (weight x reps x sets)
    (r'^(.+?)\s+(\d{1,4}(?:\.\d)?)\s*[x×*]\s*(\d{1,3})(?:\s*[x×*]\s*(\d{1,2}))?$',
     'workout'),
]

TAPE_ALIAS = {'neck': 'neck_in', 'chest': 'chest_in', 'waist': 'waist_in',
              'hip': 'hips_in', 'hips': 'hips_in', 'arm': 'arm_in',
              'thigh': 'thigh_in'}


def _quick_parse(text):
    """Text -> a structured action, or None when only AI can read it."""
    t = ' '.join(text.strip().split())
    for pattern, kind in QUICK_PATTERNS:
        m = re.match(pattern, t, re.I)
        if not m:
            continue
        if kind == 'weight':
            lbs = float(m.group(1))
            # Outside this range it is far more likely a rep count or a typo
            # than a bodyweight; let it fall through to the AI path.
            if 60 <= lbs <= 700:
                return {'action': 'weight', 'pounds': lbs}
        elif kind == 'measurement':
            return {'action': 'measurement',
                    'site': TAPE_ALIAS[m.group(1).lower()],
                    'inches': float(m.group(2))}
        elif kind == 'workout':
            name = m.group(1).strip()
            # "eggs 2x3" is not a lift; require something word-like and short.
            if 2 <= len(name) <= 48:
                return {'action': 'workout', 'exercise': name.title(),
                        'weight': float(m.group(2)), 'reps': int(m.group(3)),
                        'sets': int(m.group(4) or 1)}
    return None


@bp.post('/quick')
def quick_log():
    """One box for everything. Deterministic where possible, AI where needed."""
    text = str(request.get_json(force=True).get('text', '')).strip()
    if not text:
        return _err('Type something to log.')

    parsed = _quick_parse(text)
    used_ai = False
    if parsed is None:
        # Prose. Needs a model — and says so plainly if there is not one.
        if not ai.backend_name():
            return _err("Couldn't read that. Try '215', 'waist 37.2', or "
                        "'bench 225x5x3' — or set up an AI backend for "
                        "free-text meals.")
        try:
            route = ai.route_voice(text)
        except Exception as e:
            return _err(e, 502)
        used_ai = True
        parsed = {'action': route.get('action'), 'description':
                  route.get('description', text), 'pounds': route.get('pounds'),
                  'name': route.get('name')}

    d = store.load()
    act = parsed.get('action')
    today = date.today().isoformat()

    if act == 'weight':
        lbs = clean_num(parsed.get('pounds'), float)
        if lbs <= 0:
            return _err("Didn't catch a weight in that.")
        d['weights'] = [w for w in d['weights'] if w['date'] != today]
        d['weights'].append({'date': today, 'weight': lbs})
        d['weights'].sort(key=lambda w: w['date'])
        d['profile']['weight'] = lbs
        store.save(d)
        return jsonify({'ok': True, 'action': 'weight', 'ai': used_ai,
                        'message': f'Weigh-in logged — {lbs:g} lbs.'})

    if act == 'measurement':
        row = next((m for m in d.setdefault('measurements', [])
                    if m['date'] == today), None)
        if row is None:
            row = {'date': today}
            d['measurements'].append(row)
        row[parsed['site']] = parsed['inches']
        d['measurements'].sort(key=lambda m: m['date'])
        store.save(d)
        site = parsed['site'].replace('_in', '')
        return jsonify({'ok': True, 'action': 'measurement', 'ai': used_ai,
                        'message': f'{site.title()} logged — {parsed["inches"]:g}".'})

    if act == 'workout':
        d['workouts'].append({
            'date': today, 'time': datetime.now().strftime('%H:%M'),
            'name': parsed['exercise'], 'duration': 0, 'intensity': 'Moderate',
            'notes': 'Quick log',
            'exercises': [{'exercise': parsed['exercise'], 'sets': parsed['sets'],
                           'reps': parsed['reps'], 'weight': parsed['weight']}],
        })
        store.save(d)
        p = parsed
        return jsonify({'ok': True, 'action': 'workout', 'ai': used_ai,
                        'message': (f'{p["exercise"]} logged — '
                                    f'{p["sets"]}×{p["reps"]} @ {p["weight"]:g}.')})

    if act == 'meal':
        try:
            meals = ai.parse_meals(str(parsed.get('description') or text))
        except Exception as e:
            return _err(e, 502)
        now = datetime.now().strftime('%H:%M')
        for m in meals:
            d['meals'].append(_normalize_meal({**m, 'date': today, 'time': now,
                                               'notes': 'Quick log'}))
        store.save(d)
        total = sum(m['protein'] for m in meals)
        return jsonify({'ok': True, 'action': 'meal', 'ai': True,
                        'message': f'Logged {len(meals)} item(s) — {total}g protein.'})

    return _err("Couldn't tell what that was. Try '215', 'waist 37.2', "
                "'bench 225x5x3', or describe a meal.")


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
        if s['ntfy_topic']:
            # Re-entered: the cleared-by-restore state is resolved, so the
            # warning must stop. A flag that never clears is noise.
            (s.get(store.SECRET_STATE_KEY) or {}).pop('ntfy_topic', None)
            (s.get(store.SECRET_STATE_KEY) or {}).pop('ntfy_topic_at', None)
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


def _body_comp_brief(d):
    """Compact body-composition summary for AI contexts (skip the series)."""
    bc = stats.body_comp(d)
    return {'bf_pct': bc['current'], 'change_since_first': bc['change'],
            'method': bc['method']} if bc['current'] is not None else None


BRIEFING_LOGGED_KINDS = ('meals', 'workouts', 'weights', 'vitals',
                         'supplements', 'measurements')


def _briefing_has_material(d):
    """True when there is anything real to brief on.

    A briefing generated from an empty file is not a weak briefing, it is a
    fabrication: with every field None/[] the model has nothing to work from and
    fills the space from whatever else is in its context. Refusing is the honest
    output. (This is how a crypto-fleet essay ended up in nutrition_data.json —
    SCARS #10.)
    """
    return any(d.get(k) for k in BRIEFING_LOGGED_KINDS)


def _briefing_is_plausible(text, context_json):
    """Reject output that cannot be a nutrition briefing for this user.

    Not a content filter — a containment check on the one field that gets
    persisted unattended. Catches the empty/garbage/wrong-domain cases; a merely
    mediocre briefing still passes, which is correct.
    """
    body = (text or '').strip()
    # Deliberately a floor, not a length standard: several coaches on the roster
    # are terse by design ("Run. Eat. Stay hard."). This catches empty and
    # truncated-to-nothing, and leaves style alone.
    if len(body) < 15:
        return 'the briefing came back empty or truncated'
    # Wrong-domain tells: this app has no bots, ports, or trading anything.
    stray = ('crypto', 'trading bot', 'fleet', 'portfolio pool', 'event bus',
             'dashboard port', 'repository', 'subprocess')
    low = body.lower()
    hit = next((w for w in stray if w in low), None)
    if hit:
        return f'the briefing mentioned "{hit}" — that is not nutrition output'
    return None


@bp.post('/briefing')
def briefing():
    d = store.load()
    if not _briefing_has_material(d):
        return _err('Nothing logged yet — log a meal, a lift, or a weigh-in and '
                    'the morning briefing has something to work from.', 422)
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
        'body_comp': _body_comp_brief(d),
        'tape_latest': (sorted(d.get('measurements', []), key=lambda m: m['date'])[-1]
                        if d.get('measurements') else None),
        'training_strain': stats.training_strain(d),
        'energy_balance': stats.energy_balance(d),
        'lift_targets': stats.next_targets(d)[:5],
    })
    try:
        text = ai.daily_briefing(d['profile'], persona_prompt(coach), context)
    except Exception as e:
        return _err(e, 502)
    bad = _briefing_is_plausible(text, context)
    if bad:
        # Never persist output that failed the gate — a wrong briefing in the
        # data file outlives the run that produced it and reads as history.
        return _err(f'Briefing rejected before saving: {bad}.', 502)
    d['briefing'] = {
        'date': today, 'coach': coach['id'], 'text': text,
        # Provenance: which input produced this text. Makes "was this generated
        # from real data?" checkable after the fact instead of inferred.
        'input_sha': hashlib.sha256(context.encode('utf-8')).hexdigest()[:16],
        'source': 'api',
    }
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


@bp.post('/recipes')
def add_recipe():
    body = request.get_json(force=True)
    name = str(body.get('name', '')).strip()
    if not name:
        return _err('Recipe needs a name.')
    servings = clean_num(body.get('servings'), float)
    if servings <= 0:
        servings = 1
    items = []
    for r in body.get('items', []):
        iname = str(r.get('name', '')).strip()
        if not iname:
            continue
        items.append({'name': iname,
                      **{f: clean_num(r.get(f), float) for f in MACRO_FIELDS}})
    if not items:
        return _err('Recipe needs at least one item.')
    d = store.load()
    d.setdefault('recipes', [])
    d['recipes'].append({'name': name[:80], 'servings': servings, 'items': items})
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/recipes/<int:idx>/log')
def log_recipe(idx):
    servings = clean_num(request.get_json(force=True).get('servings'), float)
    if servings <= 0:
        servings = 1
    d = store.load()
    recipes = d.get('recipes', [])
    if not 0 <= idx < len(recipes):
        return _err('No such recipe.', 404)
    r = recipes[idx]
    per = {f: sum(i.get(f, 0) for i in r['items']) / (r.get('servings') or 1)
           for f in MACRO_FIELDS}
    d['meals'].append({
        'date': date.today().isoformat(),
        'time': datetime.now().strftime('%H:%M'),
        'name': r['name'] + (f' ×{servings:g}' if servings != 1 else ''),
        **{f: round(per[f] * servings, 1) for f in MACRO_FIELDS},
        'notes': 'From recipe',
    })
    store.save(d)
    return jsonify({'ok': True})


@bp.delete('/recipes/<int:idx>')
def delete_recipe(idx):
    d = store.load()
    recipes = d.get('recipes', [])
    if not 0 <= idx < len(recipes):
        return _err('No such recipe.', 404)
    recipes.pop(idx)
    store.save(d)
    return jsonify({'ok': True})


PHOTO_DIR = Path('photos')


@bp.post('/photos')
def add_photo():
    """Store a progress photo on disk beside the data file (never uploaded
    anywhere) and record it in the photos list."""
    import base64
    body = request.get_json(force=True)
    data_url = str(body.get('image', ''))
    if ';base64,' not in data_url:
        return _err('Send the photo as a base64 data URL.')
    header, b64 = data_url.split(';base64,', 1)
    ext = '.png' if 'png' in header else '.jpg'
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return _err('That image data did not decode.')
    if len(raw) > 12 * 1024 * 1024:
        return _err('Photo too large — keep it under 12 MB.')
    day = str(body.get('date') or date.today().isoformat())[:10]
    d = store.load()
    d.setdefault('photos', [])
    PHOTO_DIR.mkdir(exist_ok=True)
    n = 1
    while (PHOTO_DIR / f'{day}-{n}{ext}').exists():
        n += 1
    name = f'{day}-{n}{ext}'
    (PHOTO_DIR / name).write_bytes(raw)
    d['photos'].append({'date': day, 'file': name})
    d['photos'].sort(key=lambda p: p['date'])
    store.save(d)
    return jsonify({'ok': True, 'file': name})


@bp.get('/photos/<name>')
def get_photo(name):
    d = store.load()
    if not any(p['file'] == name for p in d.get('photos', [])):
        return _err('No such photo.', 404)
    return send_from_directory(PHOTO_DIR.resolve(), name)


@bp.delete('/photos/<int:idx>')
def delete_photo(idx):
    d = store.load()
    photos = d.get('photos', [])
    if not 0 <= idx < len(photos):
        return _err('No such photo.', 404)
    gone = photos.pop(idx)
    try:
        (PHOTO_DIR / gone['file']).unlink()
    except OSError:
        pass
    store.save(d)
    return jsonify({'ok': True})


@bp.post('/measurements')
def add_measurement():
    body = request.get_json(force=True)
    day = str(body.get('date') or date.today().isoformat())[:10]
    row = {'date': day}
    for f in MEASURE_FIELDS:
        if body.get(f) not in (None, ''):
            val = clean_num(body[f], float)
            if val > 0:
                row[f] = val
    if len(row) == 1:
        return _err('Enter at least one measurement.')
    d = store.load()
    d.setdefault('measurements', [])
    for m in d['measurements']:
        if m['date'] == day:
            m.update({k: v for k, v in row.items() if k != 'date'})
            break
    else:
        d['measurements'].append(row)
    d['measurements'].sort(key=lambda m: m['date'])
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


@bp.post('/remedies/cabinet')
def cabinet_add():
    d = store.load()
    if _remedies_locked(d):
        return _err('The Apothecary is locked.', 403)
    rid = str(request.get_json(force=True).get('id', '')).strip()
    if not any(r['id'] == rid for r in load_kb()):
        return _err('No such remedy in the archive.', 404)
    if rid not in d['remedy_cabinet']:
        d['remedy_cabinet'].append(rid)
        store.save(d)
    return jsonify({'ok': True, 'cabinet': d['remedy_cabinet']})


@bp.delete('/remedies/cabinet/<rid>')
def cabinet_remove(rid):
    d = store.load()
    if _remedies_locked(d):
        return _err('The Apothecary is locked.', 403)
    if rid not in d['remedy_cabinet']:
        return _err('Not in your cabinet.', 404)
    d['remedy_cabinet'].remove(rid)
    store.save(d)
    return jsonify({'ok': True, 'cabinet': d['remedy_cabinet']})


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
        found = ai.find_deals(items, d['settings'].get('deals_location', ''),
                              privilege=_privilege())
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
        'measurements': [m for m in d.get('measurements', []) if m['date'] >= cutoff],
        'body_comp': _body_comp_brief(d),
        'recent_prs': stats.recent_prs(d),
        'readiness': stats.readiness(d),
        'training_strain': stats.training_strain(d),
        'energy_balance': stats.energy_balance(d),
    }
    if not week_data['meals'] and not week_data['workouts']:
        return _err("Log some meals or workouts first — there's nothing from the last 7 days to review.")
    coach = get_coach(d['profile'].get('coach', DEFAULT_COACH))
    try:
        summary = ai.coaching_summary(week_data, persona_prompt(coach),
                                      privilege=_privilege())
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
        'body_comp': _body_comp_brief(d),
        'profile_notes': d['profile'].get('notes', ''),
    })
    history = d.get('coach_chat', [])
    # Agentic path when the API is available: the coach can propose writes.
    # Falls back to plain prose on the CLI, which has no tool-use channel.
    actions = []
    try:
        if os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN'):
            out = ai.coach_chat_agentic(persona_prompt(coach), history, message, snapshot)
            reply, actions = out['text'], out['actions']
        else:
            reply = ai.coach_chat(persona_prompt(coach), history, message, snapshot)
    except Exception as e:
        return _err(e, 502)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    history.append({'role': 'user', 'text': message, 'ts': now})
    history.append({'role': 'coach', 'text': reply, 'ts': now, 'coach': coach['id']})
    d['coach_chat'] = history[-40:]
    store.save(d)
    # Actions are PROPOSALS. They are returned for the user to confirm and are
    # deliberately not executed here — see /coach/act.
    return jsonify({'reply': reply, 'coach': coach['id'], 'actions': actions})


# What the coach is allowed to propose, and how each one is carried out. An
# explicit allow-list rather than dispatching on a model-supplied name: a tool
# the model invents must do nothing at all.
COACH_ACTIONS = {
    'log_meal': lambda d, a: d['meals'].append(_normalize_meal(a)),
    'log_weight': lambda d, a: _agent_log_weight(d, a),
    'log_workout': lambda d, a: _agent_log_workout(d, a),
    'log_measurement': lambda d, a: _agent_log_measurement(d, a),
    'set_calorie_goal': lambda d, a: d['profile'].__setitem__(
        'daily_calories', clean_num(a.get('calories'))),
}


def _agent_log_weight(d, a):
    day = date.today().isoformat()
    lbs = clean_num(a.get('weight'), float)
    if lbs <= 0:
        raise ValueError('Weight must be above 0.')
    d['weights'] = [w for w in d['weights'] if w['date'] != day]
    d['weights'].append({'date': day, 'weight': lbs})
    d['weights'].sort(key=lambda w: w['date'])
    d['profile']['weight'] = lbs


def _agent_log_workout(d, a):
    # Same flat shape the /api/workouts endpoint writes — sets/reps/weight as
    # numbers, keyed on 'exercise'. stats.training_strain multiplies these
    # directly, so a nested set-array here would break the volume maths.
    exercises = []
    for ex in (a.get('exercises') or []):
        name = str(ex.get('exercise', '')).strip()
        if not name:
            continue
        exercises.append({
            'exercise': name,
            'sets': clean_num(ex.get('sets')),
            'reps': clean_num(ex.get('reps')),
            'weight': clean_num(ex.get('weight'), float),
        })
    if not exercises:
        raise ValueError('No exercises in that workout.')
    d['workouts'].append({
        'date': date.today().isoformat(),
        'time': datetime.now().strftime('%H:%M'),
        'name': str(a.get('name', 'Session')).strip() or 'Session',
        'duration': 0, 'intensity': 'Moderate', 'notes': 'Logged by coach',
        'exercises': exercises,
    })


def _agent_log_measurement(d, a):
    day = date.today().isoformat()
    row = {'date': day}
    for f in MEASURE_FIELDS:
        if a.get(f) not in (None, ''):
            val = clean_num(a[f], float)
            if val > 0:
                row[f] = val
    if len(row) == 1:
        raise ValueError('No measurements in that action.')
    d.setdefault('measurements', [])
    for m in d['measurements']:
        if m['date'] == day:
            m.update({k: v for k, v in row.items() if k != 'date'})
            break
    else:
        d['measurements'].append(row)
    d['measurements'].sort(key=lambda m: m['date'])


@bp.post('/coach/act')
def coach_act():
    """Execute a coach-proposed action the user has confirmed.

    The confirmation happens in the UI; this endpoint is the only path from a
    proposal to the data file, and it accepts nothing outside COACH_ACTIONS.
    """
    body = request.get_json(force=True)
    tool = str(body.get('tool', ''))
    handler = COACH_ACTIONS.get(tool)
    if not handler:
        return _err(f'Unknown coach action: {tool or "(none)"}.', 400)
    payload = body.get('input')
    if not isinstance(payload, dict):
        return _err('That action had no usable payload.')
    d = store.load()
    try:
        handler(d, payload)
    except Exception as e:
        return _err(str(e) or 'That action could not be applied.')
    store.save(d)
    return jsonify({'ok': True, 'tool': tool})


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


@bp.get('/export/backup.json')
def export_backup():
    """The user's data, for safekeeping off this machine.

    Credentials and derived AI output are stripped (see data.for_export) — this
    file routinely leaves the machine, including into AI assistants when asking
    for help, so it must not carry a live push-channel or webhook credential.
    """
    d = store.for_export(store.load())
    return Response(json.dumps(d, indent=2), mimetype='application/json',
                    headers={'Content-Disposition':
                             f'attachment; filename=golden-nutrition-{date.today().isoformat()}.json'})


@bp.post('/import/csv')
def import_csv():
    """Bring history from another app. Snapshots first; duplicates skipped."""
    body = request.get_json(force=True)
    kind = str(body.get('kind', ''))
    text = str(body.get('csv', ''))
    if not text.strip():
        return _err('Empty CSV.')
    d = store.load()
    snap = Path('nutrition_data.pre-import.json')
    snap.write_text(json.dumps(d, indent=2))
    try:
        imported, skipped = importer.import_kind(kind, text, d)
    except ValueError as e:
        return _err(e)
    store.save(d)
    return jsonify({'ok': True, 'imported': imported, 'skipped': skipped,
                    'snapshot': str(snap)})


@bp.post('/import/backup')
def import_backup():
    """Restore from a backup JSON. The current file is snapshotted first."""
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict) or 'profile' not in body or 'meals' not in body:
        return _err('That does not look like a Golden Nutrition backup '
                    '(expecting the JSON file from "Full backup").')
    current = store.load()
    snap = Path('nutrition_data.pre-restore.json')
    snap.write_text(json.dumps(current, indent=2))
    # Backups no longer carry credentials (data.for_export strips them), so a
    # restore must not wipe the live ones by writing the backup wholesale.
    # Machine-local secrets survive a restore of the user's records.
    #
    # Onto a FRESH machine there is nothing to preserve, and the naive version
    # of this leaves an empty string — indistinguishable from never-configured,
    # so the loss is silent. The restore knows exactly which keys it kept and
    # which it could not; it reports that verbatim rather than leaving a health
    # check to infer it afterwards.
    now = datetime.now().isoformat(timespec='seconds')
    body.setdefault('settings', {})
    preserved, needs_reentry = [], []
    for k in store.EXPORT_STRIP_SETTINGS:
        if k == store.SECRET_STATE_KEY:
            continue
        if str(body['settings'].get(k) or '').strip():
            continue
        kept = str(current.get('settings', {}).get(k) or '').strip()
        if kept:
            body['settings'][k] = kept
            preserved.append(k)
        else:
            body['settings'].pop(k, None)
            store.mark_secret_cleared(body, k, now)
            needs_reentry.append(k)
    store.save(body)
    restored = store.load()  # re-load runs the usual defaults/migration
    # ingest_token regenerates itself on the next /api/state, so it is not the
    # user's problem. Only report what a human actually has to re-enter.
    manual = [k for k in needs_reentry if k != 'ingest_token']
    return jsonify({'ok': True,
                    'meals': len(restored['meals']),
                    'workouts': len(restored['workouts']),
                    'weights': len(restored['weights']),
                    'snapshot': str(snap),
                    'secrets_preserved': preserved,
                    'secrets_need_reentry': manual})
