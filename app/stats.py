"""Computed stats served to the frontend: totals, trends, insights, progression."""
import re
from datetime import date, datetime, timedelta

from .data import MACRO_FIELDS


def _week_ago():
    return (date.today() - timedelta(days=7)).isoformat()


def today_summary(data):
    today = date.today().isoformat()
    meals = [m for m in data['meals'] if m['date'] == today]
    workouts = [w for w in data['workouts'] if w['date'] == today]
    totals = {f: sum(m.get(f, 0) for m in meals) for f in MACRO_FIELDS}
    return {
        'totals': totals,
        'meal_count': len(meals),
        'workout_count': len(workouts),
        'recent_meals': sorted(meals, key=lambda m: m.get('time', ''))[-3:],
        'recent_workouts': sorted(workouts, key=lambda w: w.get('time', ''))[-2:],
    }


def weight_stats(data):
    weights = sorted(data.get('weights', []), key=lambda w: w['date'])
    if not weights:
        return {'has_data': False}
    current = weights[-1]['weight']
    goal = data['profile'].get('goal_weight', 0)

    window = [w for w in weights if w['date'] >= _week_ago()]
    change_7d = round(current - window[0]['weight'], 1) if len(window) > 1 else None

    month_ago = (date.today() - timedelta(days=30)).isoformat()
    trend = [w for w in weights if w['date'] >= month_ago]
    rate_per_week = None
    if len(trend) > 1:
        days = (date.fromisoformat(trend[-1]['date']) - date.fromisoformat(trend[0]['date'])).days
        if days > 0:
            rate_per_week = round((trend[-1]['weight'] - trend[0]['weight']) / days * 7, 2)

    eta, eta_days, eta_date_iso, off_track = None, None, None, False
    if goal and rate_per_week is not None and abs(rate_per_week) >= 0.05:
        to_go = goal - current
        if to_go != 0 and (to_go < 0) == (rate_per_week < 0):
            eta_days = round(abs(to_go / (rate_per_week / 7)))
            eta_d = date.today() + timedelta(days=eta_days)
            eta = eta_d.strftime('%B %d, %Y')
            eta_date_iso = eta_d.isoformat()
        elif to_go != 0:
            off_track = True

    # 7-day rolling average: the signal under the daily noise
    series_avg = []
    for w in weights:
        start = (date.fromisoformat(w['date']) - timedelta(days=6)).isoformat()
        vals = [x['weight'] for x in weights if start <= x['date'] <= w['date']]
        series_avg.append({'date': w['date'], 'avg': round(sum(vals) / len(vals), 2)})

    # Pace verdict: rate as % of bodyweight per week
    pace = None
    if rate_per_week is not None and current:
        pct = abs(rate_per_week) / current * 100
        direction = 'losing' if rate_per_week < 0 else 'gaining'
        if pct < 0.25:
            pace = {'level': 'info',
                    'text': f"{direction.capitalize()} {abs(rate_per_week):.1f} lbs/week "
                            f"({pct:.2f}% of bodyweight) — maintenance territory."}
        elif pct <= 1.0:
            pace = {'level': 'good',
                    'text': f"{direction.capitalize()} {abs(rate_per_week):.1f} lbs/week "
                            f"({pct:.2f}% of bodyweight) — a healthy, sustainable pace."}
        elif pct <= 1.5:
            pace = {'level': 'warn',
                    'text': f"{direction.capitalize()} {abs(rate_per_week):.1f} lbs/week "
                            f"({pct:.2f}% of bodyweight) — aggressive. Guard sleep, protein, and strength."}
        else:
            pace = {'level': 'warn',
                    'text': f"{direction.capitalize()} {abs(rate_per_week):.1f} lbs/week "
                            f"({pct:.2f}% of bodyweight) — too fast to hold muscle. Ease off."}

    # BMI (context only — needs height on the profile)
    bmi = None
    height_in = data['profile'].get('height_in', 0)
    if height_in and current:
        val = round(703 * current / (height_in ** 2), 1)
        cat = ('underweight' if val < 18.5 else 'normal range' if val < 25
               else 'overweight range' if val < 30 else 'obese range')
        bmi = {'value': val, 'category': cat}

    return {
        'has_data': True,
        'current': current,
        'goal': goal,
        'change_7d': change_7d,
        'total_change': round(current - weights[0]['weight'], 1),
        'since': weights[0]['date'],
        'rate_per_week': rate_per_week,
        'pace': pace,
        'bmi': bmi,
        'eta': eta,
        'eta_days': eta_days,
        'eta_date_iso': eta_date_iso,
        'off_track': off_track,
        'cutting': bool(goal and goal < current),
        'series': weights,
        'series_avg': series_avg,
    }


def weight_extras(data):
    """Milestones, weekly check-in averages, plateau detection, weigh-in streak."""
    weights = sorted(data.get('weights', []), key=lambda w: w['date'])
    if not weights:
        return {'has_data': False}
    prof = data['profile']
    goal = prof.get('goal_weight', 0)
    current = weights[-1]['weight']
    start = weights[0]['weight']

    # weigh-in streak: consecutive days ending today (an unweighed today doesn't break it)
    dates = {w['date'] for w in weights}
    day = date.today()
    if day.isoformat() not in dates:
        day -= timedelta(days=1)
    streak = 0
    while day.isoformat() in dates:
        streak += 1
        day -= timedelta(days=1)

    # weekly check-ins: Monday-start calendar-week averages, last 8 weeks
    by_week = {}
    for w in weights:
        d = date.fromisoformat(w['date'])
        wk = (d - timedelta(days=d.weekday())).isoformat()
        by_week.setdefault(wk, []).append(w['weight'])
    this_monday = date.today() - timedelta(days=date.today().weekday())
    weeks = []
    for i in range(7, -1, -1):
        wk = (this_monday - timedelta(weeks=i)).isoformat()
        if wk in by_week:
            weeks.append({'week_start': wk,
                          'avg': round(sum(by_week[wk]) / len(by_week[wk]), 1),
                          'n': len(by_week[wk])})
    for i, row in enumerate(weeks):
        row['delta'] = None if i == 0 else round(row['avg'] - weeks[i - 1]['avg'], 1)

    # plateau: three consecutive flat check-ins with real distance left to the goal
    plateau = None
    deltas = [w['delta'] for w in weeks[-3:] if w['delta'] is not None]
    if goal and len(deltas) == 3 and all(abs(x) < 0.3 for x in deltas) and abs(current - goal) > 2:
        plateau = (f"Three flat weeks in a row with {abs(round(current - goal, 1))} lbs "
                   "still to go — a classic plateau. Nudge intake by ~200 calories in the "
                   "right direction, add a weekly walk, and hold the line on protein.")

    # 5-lb milestones from the starting weight toward the goal
    milestones, next_milestone = [], None
    if goal and abs(start - goal) >= 1:
        cutting = goal < start
        marks = []
        if cutting:
            m = int(start / 5) * 5
            if m >= start:
                m -= 5
            while m > goal and len(marks) < 40:
                marks.append(m)
                m -= 5
        else:
            m = (int(start / 5) + 1) * 5
            if m <= start:
                m += 5
            while m < goal and len(marks) < 40:
                marks.append(m)
                m += 5
        marks.append(goal)
        for mark in marks:
            crossed_on = next((w['date'] for w in weights
                               if (w['weight'] <= mark if cutting else w['weight'] >= mark)), None)
            milestones.append({'target': mark, 'crossed': crossed_on is not None,
                               'date': crossed_on})
        nxt = next((m for m in milestones if not m['crossed']), None)
        if nxt:
            next_milestone = {'target': nxt['target'],
                              'to_go': round(abs(current - nxt['target']), 1)}

    return {'has_data': True, 'streak': streak, 'weeks': weeks, 'plateau': plateau,
            'milestones': milestones, 'next_milestone': next_milestone,
            'start': start, 'cutting': bool(goal and goal < start)}


def insights(data):
    week_ago = _week_ago()
    meals = [m for m in data['meals'] if m['date'] >= week_ago]
    workouts = [w for w in data['workouts'] if w['date'] >= week_ago]
    supps = [s for s in data['supplements'] if s['date'] >= week_ago]
    protein_goal = data['profile'].get('daily_protein_g', 150)

    if not meals:
        return {'has_data': False, 'protein_goal': protein_goal,
                'workout_count': len(workouts)}

    days_logged = len({m['date'] for m in meals})
    protein_by_day = {}
    for m in meals:
        protein_by_day[m['date']] = protein_by_day.get(m['date'], 0) + m.get('protein', 0)
    avg_daily_protein = sum(protein_by_day.values()) / days_logged

    if avg_daily_protein < protein_goal * 0.8:
        verdict = {'level': 'warn',
                   'text': f"You're averaging {avg_daily_protein:.0f}g protein/day, "
                           f"below your {protein_goal}g goal. Add "
                           f"{protein_goal - avg_daily_protein:.0f}g/day — a shake is 30g."}
    elif avg_daily_protein >= protein_goal:
        verdict = {'level': 'good',
                   'text': f"You're hitting your {protein_goal}g protein goal. Keep it rolling."}
    else:
        verdict = {'level': 'info',
                   'text': f"You're at {avg_daily_protein:.0f}g/day — close to your {protein_goal}g goal."}

    return {
        'has_data': True,
        'protein_goal': protein_goal,
        'days_logged': days_logged,
        'avg_protein_meal': round(sum(m.get('protein', 0) for m in meals) / len(meals), 1),
        'avg_calories_meal': round(sum(m.get('calories', 0) for m in meals) / len(meals)),
        'meals_per_day': round(len(meals) / days_logged, 1),
        'avg_carbs_day': round(sum(m.get('carbs', 0) for m in meals) / days_logged),
        'avg_fat_day': round(sum(m.get('fat', 0) for m in meals) / days_logged),
        'avg_fiber_day': round(sum(m.get('fiber', 0) for m in meals) / days_logged),
        'protein_by_day': dict(sorted(protein_by_day.items())),
        'avg_daily_protein': round(avg_daily_protein),
        'verdict': verdict,
        'workout_count': len(workouts),
        'missed_supps': [s for s in supps if not s.get('taken', True)],
    }


def progression(data):
    """Per-exercise: sorted [{date, top, volume}] from structured workout logs."""
    out = {}
    for w in data['workouts']:
        for ex in w.get('exercises', []):
            name = ex.get('exercise')
            if not name:
                continue
            day = out.setdefault(name, {}).setdefault(w['date'], {'top': 0.0, 'volume': 0.0, 'e1rm': 0.0})
            day['top'] = max(day['top'], ex.get('weight', 0))
            day['volume'] += ex.get('sets', 0) * ex.get('reps', 0) * ex.get('weight', 0)
            # Epley estimated 1RM from the heaviest set: w * (1 + reps/30)
            wt, reps = ex.get('weight', 0), ex.get('reps', 0)
            if wt and reps:
                day['e1rm'] = max(day['e1rm'], round(wt * (1 + reps / 30), 1))
    return {
        name: [{'date': d, **v} for d, v in sorted(days.items())]
        for name, days in out.items()
    }


# First matching group wins — order matters (leg extension vs tricep extension,
# overhead press vs bench press). Keyword matching is imperfect by design.
MUSCLE_GROUPS = (
    ('Core', ('plank', 'crunch', 'ab ', 'abs', 'sit-up', 'situp', 'oblique', 'russian')),
    ('Legs', ('squat', 'leg', 'lunge', 'rdl', 'hamstring', 'calf', 'quad',
              'glute', 'hip thrust', 'adductor', 'abductor')),
    ('Back', ('row', 'pulldown', 'pull-up', 'pullup', 'chin', 'deadlift',
              'shrug', 'lat ', 'lats', 'back')),
    ('Shoulders', ('shoulder', 'overhead', 'ohp', 'lateral', 'delt', 'military',
                   'arnold', 'face pull', 'rear', 'upright')),
    ('Chest', ('bench', 'chest', 'fly', 'flye', 'dip', 'push-up', 'pushup',
               'press')),
    ('Arms', ('curl', 'tricep', 'bicep', 'pushdown', 'skull', 'hammer',
              'extension', 'preacher', 'kickback')),
)


def _muscle_group(name):
    low = f' {name.lower()} '
    for group, keys in MUSCLE_GROUPS:
        if any(k in low for k in keys):
            return group
    return 'Other'


def muscle_balance(data, days=28):
    """Volume share per muscle group over the window — spots the skipped legs."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    vols = {}
    for w in data['workouts']:
        if w['date'] < cutoff:
            continue
        for ex in w.get('exercises', []):
            if not ex.get('exercise'):
                continue
            vol = ex.get('sets', 0) * ex.get('reps', 0) * ex.get('weight', 0)
            if vol > 0:
                g = _muscle_group(ex['exercise'])
                vols[g] = vols.get(g, 0) + vol
    total = sum(vols.values())
    groups = [{'group': g, 'volume': round(v), 'pct': round(v / total * 100)}
              for g, v in sorted(vols.items(), key=lambda kv: -kv[1])]
    warning = None
    if total > 0:
        legs = next((g['pct'] for g in groups if g['group'] == 'Legs'), 0)
        if legs < 15:
            warning = (f"Legs are only {legs}% of your last-{days}-day volume — "
                       "Cutler built his legacy on leg day.")
    return {'groups': groups, 'days': days, 'warning': warning}


def recent_prs(data, limit=8):
    """All-time top-weight PRs, chronologically detected. A first session
    establishes the baseline — it is never itself a PR."""
    best = {}
    prs = []
    days = {}
    for w in sorted(data['workouts'], key=lambda w: w['date']):
        for ex in w.get('exercises', []):
            name, wt = ex.get('exercise'), ex.get('weight', 0)
            if name and wt > 0:
                days.setdefault(w['date'], {}).setdefault(name, 0)
                days[w['date']][name] = max(days[w['date']][name], wt)
    for day in sorted(days):
        for name, wt in days[day].items():
            prev = best.get(name)
            if prev is not None and wt > prev:
                prs.append({'date': day, 'exercise': name,
                            'weight': wt, 'prev': prev})
            if prev is None or wt > prev:
                best[name] = wt
    return prs[-limit:][::-1]


def weekly_volume(data, weeks=8):
    """Per-week training volume + session count, oldest first."""
    out = []
    for i in range(weeks - 1, -1, -1):
        start = date.today() - timedelta(days=7 * (i + 1) - 1)
        end = date.today() - timedelta(days=7 * i)
        vol, sessions = 0.0, 0
        for w in data['workouts']:
            if start.isoformat() <= w['date'] <= end.isoformat():
                sessions += 1
                for ex in w.get('exercises', []):
                    vol += ex.get('sets', 0) * ex.get('reps', 0) * ex.get('weight', 0)
        out.append({'week_start': start.isoformat(), 'volume': round(vol),
                    'sessions': sessions})
    return out


def training_summary(data):
    """This week's training load + consecutive-week streak (3+ sessions/week)."""
    week_ago = _week_ago()
    recent = [w for w in data['workouts'] if w['date'] >= week_ago]
    volume = 0.0
    for w in recent:
        for ex in w.get('exercises', []):
            volume += ex.get('sets', 0) * ex.get('reps', 0) * ex.get('weight', 0)

    # Streak: consecutive 7-day blocks (ending today) with 3+ sessions
    streak = 0
    block = 0
    while True:
        start = (date.today() - timedelta(days=7 * (block + 1) - 1)).isoformat()
        end = (date.today() - timedelta(days=7 * block)).isoformat()
        count = sum(1 for w in data['workouts'] if start <= w['date'] <= end)
        if count >= 3:
            streak += 1
            block += 1
        else:
            break
        if block > 260:  # five years of streak is enough arithmetic
            break

    return {
        'sessions_7d': len(recent),
        'minutes_7d': sum(w.get('duration', 0) for w in recent),
        'volume_7d': round(volume),
        'streak_weeks': streak,
    }


DAY_NAMES = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday',
             'saturday', 'sunday')


def plan_progress(data):
    """Track the coach's weekly plan against workouts actually logged this
    calendar week: per-day status + adherence over the days elapsed so far."""
    week = (data.get('plan') or {}).get('plan', {}).get('week', [])
    if not week:
        return {'has_plan': False}
    monday = date.today() - timedelta(days=date.today().weekday())
    workout_dates = {w['date'] for w in data['workouts']}
    days, done, due = [], 0, 0
    for entry in week:
        name = str(entry.get('day', '')).lower()
        idx = next((i for i, d in enumerate(DAY_NAMES) if d in name), None)
        if idx is None:
            continue
        day_date = monday + timedelta(days=idx)
        is_rest = bool(re.search(r'rest|recovery|off',
                                 f"{entry.get('title', '')} {entry.get('focus', '')}", re.I))
        if is_rest:
            status = 'rest'
        elif day_date.isoformat() in workout_dates:
            status = 'done'
        elif day_date == date.today():
            status = 'today'
        elif day_date < date.today():
            status = 'missed'
        else:
            status = 'upcoming'
        if not is_rest and day_date <= date.today():
            due += 1
            if status == 'done':
                done += 1
        days.append({'day': entry.get('day'), 'date': day_date.isoformat(),
                     'status': status})
    return {'has_plan': True, 'days': days, 'done': done, 'due': due,
            'pct': round(done / due * 100) if due else None}


def quick_meals(data, limit=12):
    """Most recent distinct meals by name, newest first."""
    seen, out = set(), []
    for m in reversed(data['meals']):
        key = m['name'].strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(m)
        if len(out) >= limit:
            break
    return out


def nutrition_trend(data, days=14):
    """Per-day macro totals vs goals, plus the protein-goal streak."""
    prof = data['profile']
    p_goal = prof.get('daily_protein_g') or 0
    c_goal = prof.get('daily_calories') or 0
    by_day = {}
    for m in data['meals']:
        t = by_day.setdefault(m['date'], {f: 0 for f in MACRO_FIELDS})
        for f in MACRO_FIELDS:
            t[f] += m.get(f, 0)
    series = []
    for i in range(days - 1, -1, -1):
        day = (date.today() - timedelta(days=i)).isoformat()
        t = by_day.get(day, {f: 0 for f in MACRO_FIELDS})
        series.append({'date': day, **{f: round(t[f], 1) for f in MACRO_FIELDS}})
    streak = 0
    if p_goal:
        day = date.today()
        today_t = by_day.get(day.isoformat())
        if not today_t or today_t['protein'] < p_goal:
            day -= timedelta(days=1)  # today isn't over yet — it can't break a streak
        while True:
            t = by_day.get(day.isoformat())
            if not t or t['protein'] < p_goal:
                break
            streak += 1
            day -= timedelta(days=1)
    hits = sum(1 for s in series if p_goal and s['protein'] >= p_goal)
    return {'series': series, 'protein_goal': p_goal, 'calorie_goal': c_goal,
            'protein_streak': streak, 'hit_days_14': hits}


def supplement_adherence(data, days=7):
    """% of scheduled supplement slots actually taken over the last `days`."""
    schedule = data.get('supplement_schedule', [])
    if not schedule:
        return {'has_schedule': False}
    taken = 0
    slots = len(schedule) * days
    for i in range(days):
        day = (date.today() - timedelta(days=i)).isoformat()
        for item in schedule:
            if any(s['date'] == day and s['name'] == item['name']
                   and s['time'] == item['time'] and s.get('taken')
                   for s in data['supplements']):
                taken += 1
    return {'has_schedule': True, 'taken': taken, 'slots': slots,
            'pct': round(taken / slots * 100) if slots else 0}


VITAL_FIELDS = ('steps', 'resting_hr', 'hrv_ms', 'sleep_h', 'bp_sys', 'bp_dia')


def vitals_summary(data):
    """Latest readings + 7-day averages from the wearable/manual vitals log."""
    vitals = sorted(data.get('vitals', []), key=lambda v: v['date'])
    if not vitals:
        return {'has_data': False}

    def latest(field):
        for v in reversed(vitals):
            if v.get(field) is not None:
                return {'value': v[field], 'date': v['date']}
        return None

    week_ago = _week_ago()
    recent = [v for v in vitals if v['date'] >= week_ago]

    def avg7(field):
        vals = [v[field] for v in recent if v.get(field) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    bp = None
    for v in reversed(vitals):
        if v.get('bp_sys') is not None and v.get('bp_dia') is not None:
            level = 'urgent' if v['bp_sys'] >= 180 or v['bp_dia'] >= 120 else \
                    'high' if v['bp_sys'] >= 140 or v['bp_dia'] >= 90 else \
                    'elevated' if v['bp_sys'] >= 130 or v['bp_dia'] >= 80 else 'normal'
            bp = {'sys': v['bp_sys'], 'dia': v['bp_dia'], 'date': v['date'], 'level': level}
            break

    latest_all = {f: latest(f) for f in VITAL_FIELDS}
    avg7_all = {f: avg7(f) for f in ('steps', 'resting_hr', 'hrv_ms', 'sleep_h')}

    # Deltas vs the 7-day average, tagged with which direction is good news
    GOOD_UP = {'steps': True, 'resting_hr': False, 'hrv_ms': True, 'sleep_h': True}
    deltas = {}
    for f, up_good in GOOD_UP.items():
        cur, avg = latest_all.get(f), avg7_all.get(f)
        if cur is not None and avg not in (None, 0):
            diff = round(cur['value'] - avg, 1)
            deltas[f] = {'diff': diff,
                         'good': (diff >= 0) == up_good if diff != 0 else True}

    # Sleep debt vs target over the last 7 logged days
    target = data.get('settings', {}).get('sleep_target', 7.5)
    sleep_days = [v for v in recent if v.get('sleep_h') is not None]
    sleep_debt = {'hours': round(sum(max(0, target - v['sleep_h']) for v in sleep_days), 1),
                  'days': len(sleep_days), 'target': target} if sleep_days else None

    # Early-warning signals: the classic overtraining / illness tells
    signals = []

    def tail_avg(field, n=3):
        vals = [v[field] for v in vitals if v.get(field) is not None][-n:]
        return sum(vals) / len(vals) if vals else None

    def prior_avg(field, skip=3, span=7):
        vals = [v[field] for v in vitals if v.get(field) is not None][:-skip][-span:]
        return sum(vals) / len(vals) if vals else None

    rhr_now, rhr_base = tail_avg('resting_hr'), prior_avg('resting_hr')
    if rhr_now and rhr_base and rhr_now >= rhr_base + 3:
        signals.append({'level': 'warn',
                        'text': f"Resting heart rate is running ~{rhr_now - rhr_base:.0f} bpm above "
                                f"your recent baseline ({rhr_now:.0f} vs {rhr_base:.0f}) — a classic "
                                "early fatigue or oncoming-illness signal. Favor recovery and watch it."})
    hrv_now, hrv_base = tail_avg('hrv_ms'), prior_avg('hrv_ms')
    if hrv_now and hrv_base and hrv_now <= hrv_base * 0.85:
        signals.append({'level': 'warn',
                        'text': f"HRV is suppressed ~{(1 - hrv_now / hrv_base) * 100:.0f}% below your "
                                f"recent baseline ({hrv_now:.0f} vs {hrv_base:.0f} ms) — the nervous "
                                "system is asking for an easier day."})
    if sleep_debt and sleep_debt['hours'] >= 5:
        signals.append({'level': 'warn',
                        'text': f"You're carrying {sleep_debt['hours']}h of sleep debt over the last "
                                f"{sleep_debt['days']} logged nights (target {target}h) — recovery, "
                                "appetite control, and lifts all pay for that."})
    week_dates = {(date.today() - timedelta(days=i)).isoformat() for i in range(7)}
    if len({v['date'] for v in vitals} & week_dates) == 7:
        signals.append({'level': 'good',
                        'text': 'Vitals logged all 7 days this week — the trends you see here are real.'})

    return {
        'has_data': True,
        'latest': latest_all,
        'avg7': avg7_all,
        'deltas': deltas,
        'sleep_debt': sleep_debt,
        'signals': signals,
        'bp': bp,
        'series': vitals,
        'steps_goal': data.get('settings', {}).get('daily_steps', 8000),
    }


def readiness(data):
    """0-100 readiness from today's vitals vs the user's own 28-day baselines.
    Components: sleep (40%), HRV (35%), resting HR (25%) — renormalized over
    whichever are available. Informational guidance, never medical advice."""
    vitals = sorted(data.get('vitals', []), key=lambda v: v['date'])
    if not vitals:
        return {'has_data': False}
    latest = vitals[-1]
    prior = [v for v in vitals if v['date'] < latest['date']]
    cutoff = (date.today() - timedelta(days=28)).isoformat()

    def baseline(field):
        vals = [v[field] for v in prior if v['date'] >= cutoff and v.get(field) is not None]
        return sum(vals) / len(vals) if vals else None

    clamp = lambda x: max(0, min(100, round(x)))
    comps = {}
    if latest.get('sleep_h') is not None:
        target = max(7.5, baseline('sleep_h') or 0)
        comps['sleep'] = {'score': clamp(100 * latest['sleep_h'] / target),
                          'value': latest['sleep_h'], 'baseline': round(target, 1)}
    if latest.get('hrv_ms') is not None and baseline('hrv_ms'):
        b = baseline('hrv_ms')
        comps['hrv'] = {'score': clamp(100 * latest['hrv_ms'] / b),
                        'value': latest['hrv_ms'], 'baseline': round(b, 1)}
    if latest.get('resting_hr') is not None and baseline('resting_hr'):
        b = baseline('resting_hr')
        comps['resting_hr'] = {'score': clamp(100 * b / latest['resting_hr']),
                               'value': latest['resting_hr'], 'baseline': round(b, 1)}
    if not comps:
        return {'has_data': False}

    weights = {'sleep': 0.4, 'hrv': 0.35, 'resting_hr': 0.25}
    total_w = sum(weights[k] for k in comps)
    score = round(sum(comps[k]['score'] * weights[k] for k in comps) / total_w)
    if score >= 80:
        level, guidance = 'primed', 'Green light — a big session will land well today.'
    elif score >= 60:
        level, guidance = 'ready', 'Solid. Train as planned; save the heroics for a primed day.'
    elif score >= 40:
        level, guidance = 'caution', 'Recovery is lagging — trim volume or intensity today.'
    else:
        level, guidance = 'recover', 'The body is asking for rest. Easy movement, food, sleep.'
    return {'has_data': True, 'score': score, 'level': level,
            'guidance': guidance, 'date': latest['date'], 'components': comps}


def readiness_series(data, days=28):
    """Readiness score per logged day over the window, each scored against the
    28 days of history *before that day* (same components as readiness())."""
    vitals = sorted(data.get('vitals', []), key=lambda v: v['date'])
    if not vitals:
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    clamp = lambda x: max(0, min(100, round(x)))
    out = []
    for i, entry in enumerate(vitals):
        if entry['date'] < cutoff:
            continue
        base_start = (date.fromisoformat(entry['date']) - timedelta(days=28)).isoformat()
        prior = [v for v in vitals[:i] if v['date'] >= base_start]

        def baseline(field):
            vals = [v[field] for v in prior if v.get(field) is not None]
            return sum(vals) / len(vals) if vals else None

        scores, weights = [], []
        if entry.get('sleep_h') is not None:
            target = max(7.5, baseline('sleep_h') or 0)
            scores.append(clamp(100 * entry['sleep_h'] / target)); weights.append(0.4)
        if entry.get('hrv_ms') is not None and baseline('hrv_ms'):
            scores.append(clamp(100 * entry['hrv_ms'] / baseline('hrv_ms'))); weights.append(0.35)
        if entry.get('resting_hr') is not None and baseline('resting_hr'):
            scores.append(clamp(100 * baseline('resting_hr') / entry['resting_hr'])); weights.append(0.25)
        if scores:
            out.append({'date': entry['date'],
                        'score': round(sum(s * w for s, w in zip(scores, weights)) / sum(weights))})
    return out


def vitals_weeks(data):
    """Weekly recovery report: Monday-start averages of the four daily vitals
    over the last 8 weeks, with week-over-week deltas."""
    fields = ('steps', 'resting_hr', 'hrv_ms', 'sleep_h')
    vitals = data.get('vitals', [])
    if not vitals:
        return []
    by_week = {}
    for v in vitals:
        d = date.fromisoformat(v['date'])
        wk = (d - timedelta(days=d.weekday())).isoformat()
        by_week.setdefault(wk, []).append(v)
    this_monday = date.today() - timedelta(days=date.today().weekday())
    weeks = []
    for i in range(7, -1, -1):
        wk = (this_monday - timedelta(weeks=i)).isoformat()
        if wk not in by_week:
            continue
        row = {'week_start': wk, 'n': len(by_week[wk])}
        for f in fields:
            vals = [v[f] for v in by_week[wk] if v.get(f) is not None]
            row[f] = round(sum(vals) / len(vals), 1) if vals else None
        weeks.append(row)
    for i, row in enumerate(weeks):
        for f in fields:
            prev = weeks[i - 1][f] if i else None
            row[f'{f}_delta'] = (round(row[f] - prev, 1)
                                 if row.get(f) is not None and prev is not None else None)
    return weeks


def step_stats(data):
    """Step-goal streak (unlogged today doesn't break it) + 14-day hit count."""
    goal = data.get('settings', {}).get('daily_steps', 8000) or 0
    if not goal:
        return {'has_goal': False}
    hit_dates = {v['date'] for v in data.get('vitals', [])
                 if v.get('steps') is not None and v['steps'] >= goal}
    logged = {v['date'] for v in data.get('vitals', []) if v.get('steps') is not None}
    day = date.today()
    if day.isoformat() not in logged:
        day -= timedelta(days=1)
    streak = 0
    while day.isoformat() in hit_dates:
        streak += 1
        day -= timedelta(days=1)
    last14 = {(date.today() - timedelta(days=i)).isoformat() for i in range(14)}
    return {'has_goal': True, 'goal': goal, 'streak': streak,
            'hits_14': len(hit_dates & last14)}


def consecutive_days(dates_set):
    """Days-in-a-row ending today that appear in the given date set."""
    streak, day = 0, date.today()
    while day.isoformat() in dates_set:
        streak += 1
        day -= timedelta(days=1)
    return streak


def achievements(data):
    """The trophy wall — earned by data, never by hand. Cutler-approved."""
    workouts = data['workouts']
    meals = data['meals']
    trn = training_summary(data)
    adh = supplement_adherence(data)

    day_volume = {}
    for w in workouts:
        vol = sum(e.get('sets', 0) * e.get('reps', 0) * e.get('weight', 0)
                  for e in w.get('exercises', []))
        day_volume[w['date']] = day_volume.get(w['date'], 0) + vol
    biggest_day = round(max(day_volume.values())) if day_volume else 0

    prog = progression(data)
    pr_count = sum(1 for series in prog.values()
                   if len(series) > 1 and series[-1]['top'] > max(s['top'] for s in series[:-1]))

    meal_days = {m['date'] for m in meals}
    protein_goal = data['profile'].get('daily_protein_g', 150)
    protein_by_day = {}
    for m in meals:
        protein_by_day[m['date']] = protein_by_day.get(m['date'], 0) + m.get('protein', 0)
    sniper_days = {d for d, p in protein_by_day.items() if p >= protein_goal * 0.95}

    defs = [
        ('first_blood', 'First Blood', 'Log your first workout.',
         len(workouts) >= 1, len(workouts), 1),
        ('iron_week', 'Iron Week', '3+ sessions in a week.',
         trn['streak_weeks'] >= 1, trn['sessions_7d'], 3),
        ('month_of_iron', 'Month of Iron', 'Four straight weeks of 3+ sessions.',
         trn['streak_weeks'] >= 4, trn['streak_weeks'], 4),
        ('peanut', "Ain't Nothin' But a Peanut", '25 workouts logged.',
         len(workouts) >= 25, len(workouts), 25),
        ('quad_stomp', 'Quad Stomp', '10,000 lbs of volume in a single day.',
         biggest_day >= 10000, biggest_day, 10000),
        ('pr_machine', 'PR Machine', 'Set a new all-time top on any lift.',
         pr_count >= 1, pr_count, 1),
        ('feeder', 'The Feeder', 'Log meals 7 days in a row.',
         consecutive_days(meal_days) >= 7, consecutive_days(meal_days), 7),
        ('centurion', 'Centurion', '100 meals logged.',
         len(meals) >= 100, len(meals), 100),
        ('macro_sniper', 'Macro Sniper', 'Hit your protein goal 3 days running.',
         len(sniper_days) >= 3, len(sniper_days), 3),
        ('clean_stack', 'Clean Stack', 'A full week of 100% supplement adherence.',
         bool(adh.get('has_schedule')) and adh.get('pct') == 100,
         adh.get('pct', 0) if adh.get('has_schedule') else 0, 100),
        ('scale_watcher', 'Scale Watcher', 'Weigh in 7 days in a row.',
         consecutive_days({w['date'] for w in data['weights']}) >= 7,
         consecutive_days({w['date'] for w in data['weights']}), 7),
        ('wired_in', 'Wired In', 'First vitals synced from the wrist (or logged).',
         len(data.get('vitals', [])) >= 1, len(data.get('vitals', [])), 1),
    ]
    return [{'id': i, 'name': n, 'desc': d, 'earned': e,
             'progress': min(p, target), 'target': target}
            for i, n, d, e, p, target in defs]


def dashboard_extras(data):
    """Command-center intelligence: week grid, streaks, next best actions."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    protein_goal = data['profile'].get('daily_protein_g', 150) or 150
    schedule = data.get('supplement_schedule', [])
    prog = plan_progress(data)
    plan_by_date = ({x['date']: x['status'] for x in prog['days']}
                    if prog.get('has_plan') else {})
    workout_dates = {w['date'] for w in data['workouts']}
    weight_dates = {w['date'] for w in data['weights']}
    vitals_dates = {v['date'] for v in data.get('vitals', [])}

    # ── week-at-a-glance grid ──
    grid = []
    for i in range(7):
        d = monday + timedelta(days=i)
        iso = d.isoformat()
        future = d > today
        if future:
            workout = plan_by_date.get(iso, 'future') if plan_by_date.get(iso) in ('rest',) else 'future'
        elif iso in workout_dates:
            workout = 'done'
        elif plan_by_date.get(iso) == 'rest':
            workout = 'rest'
        elif plan_by_date.get(iso) == 'missed':
            workout = 'missed'
        else:
            workout = 'none'
        protein = sum(m.get('protein', 0) for m in data['meals'] if m['date'] == iso)
        taken = sum(1 for item in schedule
                    if any(s['date'] == iso and s['name'] == item['name']
                           and s['time'] == item['time'] and s.get('taken')
                           for s in data['supplements']))
        grid.append({
            'date': iso,
            'day': d.strftime('%a'),
            'is_today': d == today,
            'future': future,
            'workout': workout,
            'protein_pct': min(100, round(protein / protein_goal * 100)),
            'weighed': iso in weight_dates,
            'vitals': iso in vitals_dates,
            'supps_pct': round(taken / len(schedule) * 100) if schedule else None,
        })

    # ── streaks ──
    streaks = {
        'meals': consecutive_days({m['date'] for m in data['meals']}),
        'weights': consecutive_days(weight_dates),
        'vitals': consecutive_days(vitals_dates),
        'workout_weeks': training_summary(data)['streak_weeks'],
    }

    # ── next best action (rule-based, top 2) ──
    actions = []
    now = datetime.now()
    briefing = data.get('briefing') or {}
    if briefing.get('date') != today.isoformat():
        actions.append({'id': 'briefing', 'tab': 'dashboard',
                        'text': "Get today's briefing from your coach."})
    today_status = plan_by_date.get(today.isoformat())
    if today_status == 'today':
        plan_day = next((x for x in (data.get('plan') or {}).get('plan', {}).get('week', [])
                         if today.strftime('%A').lower() in str(x.get('day', '')).lower()), None)
        title = (plan_day or {}).get('title', 'your session')
        actions.append({'id': 'train', 'tab': 'workouts',
                        'text': f"Today is {title} — load it in Workouts."})
    protein_today = sum(m.get('protein', 0) for m in data['meals']
                        if m['date'] == today.isoformat())
    if now.hour >= 15 and protein_today < protein_goal * 0.5:
        actions.append({'id': 'protein', 'tab': 'meals',
                        'text': f"{protein_goal - protein_today}g of protein still to go — "
                                "ask for a meal suggestion."})
    if today.isoformat() not in weight_dates and now.hour < 12:
        actions.append({'id': 'weigh', 'tab': 'weight',
                        'text': 'Morning weigh-in — daily beats perfect.'})
    if schedule and now.hour >= 18:
        left = sum(1 for item in schedule
                   if not any(s['date'] == today.isoformat() and s['name'] == item['name']
                              and s['time'] == item['time'] and s.get('taken')
                              for s in data['supplements']))
        if left:
            actions.append({'id': 'supps', 'tab': 'supplements',
                            'text': f"{left} supplement{'s' if left > 1 else ''} still unticked today."})

    return {'week_grid': grid, 'streaks': streaks, 'actions': actions[:2]}


def checklist(data):
    today = date.today().isoformat()
    items = []
    for item in data.get('supplement_schedule', []):
        taken = any(s['date'] == today and s['name'] == item['name']
                    and s['time'] == item['time'] and s.get('taken')
                    for s in data['supplements'])
        left = item.get('servings_left')
        items.append({**item, 'taken': taken,
                      'low': left is not None and left <= 7})
    return items


def adherence_series(data, days=30):
    """Per-day stack adherence % for the trend chart (assumes today's schedule)."""
    schedule = data.get('supplement_schedule', [])
    if not schedule:
        return []
    out = []
    for i in range(days - 1, -1, -1):
        day = (date.today() - timedelta(days=i)).isoformat()
        taken = sum(1 for item in schedule
                    if any(s['date'] == day and s['name'] == item['name']
                           and s['time'] == item['time'] and s.get('taken')
                           for s in data['supplements']))
        out.append({'date': day, 'pct': round(taken / len(schedule) * 100)})
    return out
