"""Computed stats served to the frontend: totals, trends, insights, progression."""
import math
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


def body_comp(data):
    """US Navy tape-formula body-fat estimates from measurements + profile.

    Needs height (profile), sex (picks the formula), waist + neck per row —
    plus hips for the female formula. Rows missing inputs are skipped;
    implausible results (outside 2–60%) are dropped rather than shown.
    """
    p = data['profile']
    height = p.get('height_in') or 0
    sex = (p.get('sex') or '').lower()
    rows = sorted(data.get('measurements', []), key=lambda m: m['date'])
    series = []
    for m in rows:
        waist, neck, hips = m.get('waist_in'), m.get('neck_in'), m.get('hips_in')
        bf = None
        if height > 0 and waist and neck:
            if sex == 'male' and waist - neck > 0:
                bf = (86.010 * math.log10(waist - neck)
                      - 70.041 * math.log10(height) + 36.76)
            elif sex == 'female' and hips and waist + hips - neck > 0:
                bf = (163.205 * math.log10(waist + hips - neck)
                      - 97.684 * math.log10(height) - 78.387)
        if bf is not None and 2 <= bf <= 60:
            series.append({'date': m['date'], 'bf': round(bf, 1)})
    hint = None
    if rows and not series:
        if not height:
            hint = 'Add your height in Profile to unlock body-fat estimates.'
        elif sex not in ('male', 'female'):
            hint = 'Set sex in Profile to pick the right body-fat formula.'
        else:
            hint = ('Log waist and neck (plus hips for the female formula) '
                    'to estimate body fat.')
    # Age of the reading, so a stale measurement stops being presented as
    # current. A tape set from 90 days ago is structurally identical to one
    # from this morning, and confidently drawing it asserts a body that no
    # longer exists — healthy-by-absence wearing a different hat.
    age_days = None
    if series:
        try:
            age_days = (date.today() - date.fromisoformat(series[-1]['date'])).days
        except ValueError:
            age_days = None
    return {
        'series': series,
        'current': series[-1]['bf'] if series else None,
        'measured_on': series[-1]['date'] if series else None,
        'age_days': age_days,
        # Degrades with age rather than flipping at one threshold: a 3-week-old
        # tape is still worth showing, a 3-month-old one is a historical note.
        'confidence': (None if age_days is None
                       else 'current' if age_days <= 21
                       else 'aging' if age_days <= 60
                       else 'stale'),
        'change': (round(series[-1]['bf'] - series[0]['bf'], 1)
                   if len(series) >= 2 else None),
        'hint': hint,
        'method': 'US Navy tape formula',
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


def days_since_user_entry(data):
    """Days since the user last logged anything real, or None if never.

    Derived from entry dates, NOT the data file's mtime: the app rewrites
    that file on ordinary activity (minting an ingest token, saving
    settings), so mtime measures the app being alive, not the user showing
    up. A false-green audit caught the quiet version of this.
    """
    days = [e['date'] for key in ('meals', 'workouts', 'weights', 'vitals',
                                  'supplements', 'measurements')
            for e in (data.get(key) or []) if e.get('date')]
    if not days:
        return None
    try:
        return (date.today() - date.fromisoformat(max(days))).days
    except ValueError:
        return None


def sentinel_alerts(data, backup_age_days=None, last_log_age_days=None):
    """Conditions worth a phone tap — returns [] when everything is fine.

    Pure function: filesystem facts (backup age) are computed by the caller
    (scripts/sentinel.py) and passed in. `last_log_age_days` is accepted for
    compatibility but the quiet-logging check derives its own answer from
    entry dates — see days_since_user_entry.
    """
    alerts = []
    if backup_age_days is None:
        alerts.append('No backups found — install the nightly backup job.')
    elif backup_age_days > 2:
        alerts.append(f'Newest backup is {backup_age_days:.0f} days old — '
                      'the backup job may have stopped.')
    quiet = days_since_user_entry(data)
    if quiet is None:
        alerts.append('Nothing logged yet — log a meal, a lift, or a weigh-in '
                      'to start the history the coaching runs on.')
    elif quiet >= 3:
        alerts.append(f'Nothing logged in {quiet} days — the streak misses you.')
    ts = training_strain(data)
    if ts.get('suggestion'):
        alerts.append(ts['suggestion'])
    rd = readiness(data)
    if rd.get('has_data') and rd.get('level') == 'recover':
        alerts.append(f"Readiness {rd['score']} — {rd['guidance']}")
    wx = weight_extras(data)
    if wx.get('plateau'):
        alerts.append(wx['plateau'])
    return alerts


def next_targets(data):
    """Next-session load suggestions via simplified double progression.

    Per exercise, compare the top set of the last two sessions: reps held or
    beaten at the same weight (and ≥6 reps) → earn +5 lbs; reps slipped by
    2+ → consolidate at the same weight; otherwise keep building reps.
    Exercises untouched for 21 days are skipped — suggestions expire.
    """
    hist = {}
    for w in data['workouts']:
        for ex in w.get('exercises', []):
            name = ex.get('exercise')
            if not name or not ex.get('weight'):
                continue
            days = hist.setdefault(name, {})
            cur = days.get(w['date'])
            cand = (ex['weight'], ex.get('reps', 0))
            if cur is None or cand > cur:
                days[w['date']] = cand
    stale = (date.today() - timedelta(days=21)).isoformat()
    out = []
    for name, days in hist.items():
        seq = sorted(days.items())
        d1, (w1, r1) = seq[-1]
        if d1 < stale:
            continue
        prev = seq[-2][1] if len(seq) >= 2 else None
        if prev and prev[0] == w1 and r1 >= prev[1] and r1 >= 6:
            action, nxt = 'increase', w1 + 5
            why = (f'Held {w1} lbs for {prev[1]}→{r1} reps across two sessions '
                   '— earn the next plate.')
        elif prev and prev[0] == w1 and r1 <= prev[1] - 2:
            action, nxt = 'hold', w1
            why = f'Reps slipped {prev[1]}→{r1} at {w1} lbs — consolidate before adding.'
        else:
            action, nxt = 'build', w1
            why = f'Build reps at {w1} lbs before adding weight.'
        out.append({'exercise': name, 'last_weight': w1, 'last_reps': r1,
                    'last_date': d1, 'action': action, 'next_weight': nxt,
                    'why': why})
    out.sort(key=lambda x: x['last_date'], reverse=True)
    return out


def energy_balance(data):
    """Adaptive TDEE from the last 21 days of weigh-ins + logged calories.

    Energy-balance identity: TDEE ≈ average intake − weekly weight slope ×
    3500/7. Only days with ≥800 logged calories count as logged — partial
    days would bias the estimate down. Needs ≥10 logged days and ≥8
    weigh-ins spanning two weeks; below that, honest silence beats a wrong
    number.
    """
    cutoff = (date.today() - timedelta(days=20)).isoformat()
    weights = sorted((w for w in data['weights'] if w['date'] >= cutoff),
                     key=lambda w: w['date'])
    by_day = {}
    for m in data['meals']:
        if m['date'] >= cutoff:
            by_day[m['date']] = by_day.get(m['date'], 0) + (m.get('calories') or 0)
    logged = [v for v in by_day.values() if v >= 800]
    span = ((date.fromisoformat(weights[-1]['date'])
             - date.fromisoformat(weights[0]['date'])).days
            if len(weights) >= 2 else 0)
    if len(logged) < 10 or len(weights) < 8 or span < 13:
        return {'has_data': False,
                'note': 'Needs ~2 weeks of daily weigh-ins and complete food logs.'}

    avg_intake = sum(logged) / len(logged)
    xs = [date.fromisoformat(w['date']).toordinal() for w in weights]
    ys = [w['weight'] for w in weights]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys))
             / sum((x - mx) ** 2 for x in xs))          # lbs/day
    rate_wk = round(slope * 7, 2)
    tdee = avg_intake - rate_wk * 500                    # 3500 kcal/lb ÷ 7

    goal, cur = data['profile'].get('goal_weight') or 0, ys[-1]
    target_rate = (-1.0 if goal and goal < cur - 1 else
                   0.5 if goal and goal > cur + 1 else 0.0)
    rec = int(round((tdee + target_rate * 500) / 25) * 25)
    current_goal = data['profile'].get('daily_calories') or 0
    confidence = ('high' if len(logged) >= 17 and len(weights) >= 15 else
                  'medium' if len(logged) >= 12 and len(weights) >= 10 else 'low')
    return {'has_data': True,
            'tdee': int(round(tdee / 25) * 25),
            'avg_intake': round(avg_intake),
            'rate_wk': rate_wk,
            'logged_days': len(logged), 'weigh_ins': len(weights),
            'target_rate': target_rate,
            'recommended_calories': rec,
            'current_goal': current_goal, 'delta': rec - current_goal,
            'confidence': confidence}


def training_strain(data):
    """Volume-based training-load radar. Volume (sets×reps×weight) is the
    load proxy — honest but blind to RPE and cardio, so treat it as a
    compass, not a verdict.

    - acwr: last-7-day volume vs the average week of the last 28 days
      (0.8–1.3 is the classically quoted sweet spot).
    - monotony: Foster-style mean/std of the last 7 daily loads (rest days
      count as zero) — high means the same grind every single day.
    - rising_weeks: consecutive week-over-week volume increases ending now.
    """
    daily = {}
    cutoff = (date.today() - timedelta(days=27)).isoformat()
    for w in data['workouts']:
        if w['date'] >= cutoff:
            v = sum(ex.get('sets', 0) * ex.get('reps', 0) * ex.get('weight', 0)
                    for ex in w.get('exercises', []))
            daily[w['date']] = daily.get(w['date'], 0) + v

    week_ago = (date.today() - timedelta(days=6)).isoformat()
    acute = sum(v for dt, v in daily.items() if dt >= week_ago)
    prior21 = sum(v for dt, v in daily.items() if dt < week_ago)
    if prior21 <= 0:
        return {'has_data': False}
    chronic = (acute + prior21) / 4
    acwr = round(acute / chronic, 2)
    zone = ('spike' if acwr > 1.5 else 'pushing' if acwr > 1.3 else
            'sweet' if acwr >= 0.8 else 'easing')

    loads = [daily.get((date.today() - timedelta(days=i)).isoformat(), 0)
             for i in range(7)]
    mean = sum(loads) / 7
    var = sum((x - mean) ** 2 for x in loads) / 7
    monotony = round(mean / var ** 0.5, 2) if var > 0 else None
    strain = round(acute * monotony) if monotony else None

    wv = weekly_volume(data)
    rising = 0
    for i in range(len(wv) - 1, 0, -1):
        if wv[i]['volume'] > wv[i - 1]['volume'] > 0:
            rising += 1
        else:
            break

    suggestion = None
    if acwr > 1.5:
        suggestion = (f'Acute load is {acwr}× your 4-week norm — spike zone. '
                      'Pull the next few sessions back before your joints file a complaint.')
    elif rising >= 4:
        suggestion = (f'{rising} straight weeks of climbing volume — bank a deload '
                      'week: half the sets, keep the weights, come back growing.')
    elif monotony is not None and monotony > 2.5:
        suggestion = (f'Every day is the same grind (monotony {monotony}) — alternate '
                      'hard and easy days; recovery lives in the contrast.')
    elif acwr < 0.5:
        suggestion = ('Volume has fallen well under your norm — ramp back in over a '
                      'week or two rather than jumping straight to the old numbers.')

    return {'has_data': True, 'acwr': acwr, 'zone': zone, 'monotony': monotony,
            'strain': strain, 'rising_weeks': rising, 'acute_7d': round(acute),
            'chronic_weekly': round(chronic), 'suggestion': suggestion}


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


def watch_insights(data):
    """Buy-window verdict per price watch, from its own history."""
    out = []
    for w in data.get('watches', []):
        prices = [p['price'] for p in w.get('history', []) if p.get('price') is not None]
        if not prices:
            out.append({'item': w['item'], 'verdict': None})
            continue
        latest, best = prices[-1], min(prices)
        mid = sorted(prices)[len(prices) // 2]
        if latest <= best:
            verdict, text = 'best', 'lowest price seen — buy window'
        elif latest <= mid:
            verdict, text = 'typical', 'around its usual price'
        else:
            verdict, text = 'high', f'above typical — best seen {best}'
        out.append({'item': w['item'], 'verdict': verdict, 'text': text,
                    'latest': latest, 'best': best,
                    'vs_best_pct': round((latest - best) / best * 100) if best else 0,
                    'points': len(prices)})
    return out


# Rule-based coach-fit groups, by training direction. Presentation-level
# guidance only — every coach works for every goal if the user likes the voice.
COACH_FIT = {
    'cut': ('wicks', 'goggins', 'simmons', 'casseyho', 'phelps', 'austin'),
    'gain': ('cutler', 'nippard', 'arnold', 'hall', 'heria', 'serena'),
    'maintain': ('lalanne', 'jetli', 'adriene', 'pavel', 'biles', 'fraser'),
}


def coach_fit(data):
    """Top-3 coach suggestions for the user's current direction."""
    prof = data['profile']
    weight, goal = prof.get('weight') or 0, prof.get('goal_weight') or 0
    if weight and goal and abs(weight - goal) >= 2:
        direction = 'cut' if goal < weight else 'gain'
    else:
        direction = 'maintain'
    age = prof.get('age') or 0
    ids = list(COACH_FIT[direction])
    if age >= 55 and direction != 'maintain':
        ids = ['lalanne'] + [i for i in ids if i != 'lalanne']  # longevity first at 55+
    label = {'cut': 'cutting', 'gain': 'building', 'maintain': 'maintaining'}[direction]
    return {'direction': direction, 'label': label, 'ids': ids[:3]}


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
    has_any = days_since_user_entry(data) is not None
    briefing = data.get('briefing') or {}
    # The briefing needs something to brief on. Offering it first on an empty
    # install put the one action guaranteed to fail at the top of the screen —
    # and it is what let a contentless briefing get generated at all (SCARS #10).
    if has_any and briefing.get('date') != today.isoformat():
        actions.append({'id': 'briefing', 'tab': 'dashboard',
                        'text': "Get today's briefing from your coach."})
    today_status = plan_by_date.get(today.isoformat())
    if today_status == 'today':
        plan_day = next((x for x in (data.get('plan') or {}).get('plan', {}).get('week', [])
                         if today.strftime('%A').lower() in str(x.get('day', '')).lower()), None)
        title = (plan_day or {}).get('title', 'your session')
        text = f"Today is {title} — load it in Workouts."
        # If the overload autopilot has earned an increase on one of today's
        # planned lifts, put the number in the call to action.
        for t in next_targets(data):
            if t['action'] == 'increase' and plan_day and any(
                    t['exercise'].lower() in str(line).lower()
                    for line in plan_day.get('details', [])):
                text = (f"Today is {title} — {t['exercise']} earns "
                        f"{t['next_weight']:g} lbs. Load it in Workouts.")
                break
        actions.append({'id': 'train', 'tab': 'workouts', 'text': text})
    protein_today = sum(m.get('protein', 0) for m in data['meals']
                        if m['date'] == today.isoformat())
    if now.hour >= 15 and protein_today < protein_goal * 0.5:
        actions.append({'id': 'protein', 'tab': 'meals',
                        'text': f"{protein_goal - protein_today}g of protein still to go — "
                                "ask for a meal suggestion."})
    # The morning-only gate is right once weigh-ins are a habit; before the
    # first one there is no habit to time, and an empty install after noon
    # would otherwise show nothing to do.
    if today.isoformat() not in weight_dates and (now.hour < 12 or not weight_dates):
        actions.append({'id': 'weigh', 'tab': 'weight',
                        'text': ('Step on the scale — one number starts the trend.'
                                 if not weight_dates
                                 else 'Morning weigh-in — daily beats perfect.')})
    if schedule and now.hour >= 18:
        left = sum(1 for item in schedule
                   if not any(s['date'] == today.isoformat() and s['name'] == item['name']
                              and s['time'] == item['time'] and s.get('taken')
                              for s in data['supplements']))
        if left:
            actions.append({'id': 'supps', 'tab': 'supplements',
                            'text': f"{left} supplement{'s' if left > 1 else ''} still unticked today."})

    # ── radar: cross-tab signals worth a glance (not actions, awareness) ──
    # Priority order: training load and metabolism first — they change what
    # today should look like; shopping intel last.
    radar = []
    ts = training_strain(data)
    if ts.get('suggestion'):
        radar.append({'tab': 'workouts', 'level': 'warn', 'text': ts['suggestion']})
    en = energy_balance(data)
    if en.get('has_data') and abs(en['delta']) >= 100:
        radar.append({'tab': 'meals',
                      'level': 'good' if en['delta'] > 0 else 'warn',
                      'text': (f"Measured TDEE ~{en['tdee']} — the math says "
                               f"{en['recommended_calories']} calories; your goal is "
                               f"{en['current_goal']}. One tap to adopt in Meals.")})
    low = [item['name'] for item in schedule
           if item.get('servings_left') is not None and item['servings_left'] <= 7]
    if low:
        radar.append({'tab': 'deals', 'level': 'warn',
                      'text': f"Running low: {', '.join(sorted(set(low))[:3])}"
                              f"{' +' + str(len(set(low)) - 3) if len(set(low)) > 3 else ''}"
                              " — restock radar is live in Deals."})
    for ins in watch_insights(data):
        if ins.get('verdict') == 'best' and ins.get('points', 0) >= 2:
            radar.append({'tab': 'deals', 'level': 'good',
                          'text': f"{ins['item']} is at the lowest price seen — buy window open."})
            break
    wx = weight_extras(data)
    if wx.get('has_data'):
        nm = wx.get('next_milestone')
        if nm and nm['to_go'] <= 2:
            radar.append({'tab': 'weight', 'level': 'good',
                          'text': f"Only {nm['to_go']} lbs from your {nm['target']} plate."})
        if wx.get('plateau'):
            radar.append({'tab': 'weight', 'level': 'warn',
                          'text': 'Weight has been flat three weeks running — plateau playbook is in Weight.'})
    mb = muscle_balance(data)
    if mb.get('warning'):
        radar.append({'tab': 'workouts', 'level': 'warn', 'text': mb['warning']})

    return {'week_grid': grid, 'streaks': streaks, 'actions': actions[:2],
            'radar': radar[:4], 'onboarding': onboarding(data)}


# What each engine needs before it can say anything true. These are the real
# thresholds from the functions themselves, not marketing numbers — the point
# is that a new user can see what their next entry actually unlocks instead of
# staring at a wall of zeros.
ONBOARDING_STEPS = (
    ('profile', 'Set your weight and goal',
     'Unlocks pace tracking, calorie targets, and the plan line.'),
    ('weigh', 'Log one weigh-in',
     'Starts the trend. Three weeks of daily weigh-ins measures your true '
     'day-to-day noise.'),
    ('meal', 'Log one meal',
     'Today\'s rings come alive. Ten fully-logged days unlock adaptive TDEE.'),
    ('workout', 'Log one workout',
     'Starts the strain radar and the progression engine.'),
    ('tape', 'Take one tape measurement',
     'Unlocks body-fat estimates and the change-over-time view.'),
)


def onboarding(data):
    """First-run progress: what is done, what is next, what it unlocks.

    An empty install currently renders as zeros in every ring — technically
    honest and completely uninformative. This turns the same emptiness into a
    path, and it disappears on its own once every step is done.
    """
    profile = data.get('profile') or {}
    done = {
        'profile': bool(profile.get('weight')) and bool(profile.get('goal_weight')),
        'weigh': bool(data.get('weights')),
        'meal': bool(data.get('meals')),
        'workout': bool(data.get('workouts')),
        'tape': bool(data.get('measurements')),
    }
    steps = [{'id': i, 'title': t, 'unlocks': u, 'done': done.get(i, False)}
             for i, t, u in ONBOARDING_STEPS]
    complete = sum(1 for s in steps if s['done'])
    return {
        'active': complete < len(steps),
        'steps': steps,
        'complete': complete,
        'total': len(steps),
        # Nothing logged at all is a different state from partway through:
        # it is the only time the app has literally nothing to show.
        'cold': days_since_user_entry(data) is None,
    }


# ── VESSEL: the body as the primary object ──────────────────────────────────
#
# One fully-derived payload; the canvas computes nothing. Navy BF, ACWR, goal
# projection and confidence all stay here where the tests are — reimplementing
# any of them in the renderer would create two sources of truth that diverge
# silently, which is the backend_name() failure shape one layer up.
#
# Contract rules, enforced by tests:
#   - every block carries an explicit `have`; never infer presence from nulls
#   - never send 0 for unknown. Zero is a real weight, a real ACR, a real
#     calorie count. Absent is `have: false`.
#   - `confidence` is rendered, not hidden. The app never asserts a number it
#     cannot stand behind.

# The six sites this app actually stores. The reference render wanted nine
# (shoulder, rib, calf too) — those have no field, no storage, and no UI, so
# the figure derives them from neighbours and says so rather than inventing
# measurements. `derived` is the honest word for a ring nobody taped.
VESSEL_SITES = ('neck_in', 'chest_in', 'waist_in', 'hips_in', 'arm_in', 'thigh_in')

# Population-typical circumference as a fraction of height, used only to draw
# a generic figure before the first tape set. Explicitly marked estimated so
# the renderer can dim it — a cold-install figure is a prompt, not a portrait.
TYPICAL_BY_HEIGHT = {
    'neck_in': 0.216, 'chest_in': 0.575, 'waist_in': 0.500,
    'hips_in': 0.550, 'arm_in': 0.196, 'thigh_in': 0.313,
}

# Height used for the factory figure when the profile has no height either.
# The figure it produces is a silhouette, not a claim: fidelity stays
# 'generic', measured_sites stays empty, and the renderer dims it to 45%.
GENERIC_HEIGHT_IN = 70


def tape_change(data, days=None):
    """Per-site change between two tape sets, in RADIAL millimetres.

    Circumference is what you measure; radius is what you see. A 1 inch drop
    around the waist is only ~4 mm off the surface, and quoting the inch makes
    a change feel larger than it looks in the mirror. Converting to radial
    displacement is what turns six numbers into a map of where the body moved.

    Noise floor: repeat tape measurements at the same site scatter by roughly
    ±0.25 in circumference even done carefully, which is ~1 mm radial. Anything
    under that is reported as `flat` rather than as a direction, because a
    trend built from measurement noise is worse than no trend.
    """
    rows = sorted(data.get('measurements') or [], key=lambda m: m['date'])
    if len(rows) < 2:
        return {'has_data': False,
                'note': ('Two tape sets are needed before change means anything.'
                         if rows else 'Log a tape set to start the map.')}
    latest = rows[-1]
    # Compare against the oldest set inside the window, so the reading answers
    # "what changed over this period" rather than "since the last time I taped",
    # which varies with how often the user happens to measure.
    if days:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        earlier = [r for r in rows[:-1] if r['date'] >= cutoff]
        base = earlier[0] if earlier else rows[-2]
    else:
        base = rows[0]

    NOISE_MM = 1.0
    sites = []
    for key in VESSEL_SITES:
        a, b = base.get(key), latest.get(key)
        if not a or not b:
            continue
        # circumference inches -> radius inches -> millimetres
        d_mm = round((b - a) / math.pi / 2 * 25.4, 1)
        sites.append({
            'site': key,
            'from': a, 'to': b,
            'delta_in': round(b - a, 2),
            'delta_mm': d_mm,
            'direction': ('flat' if abs(d_mm) < NOISE_MM
                          else 'down' if d_mm < 0 else 'up'),
            # Below the noise floor the sign is not trustworthy; say so rather
            # than drawing a colour that implies a direction.
            'significant': abs(d_mm) >= NOISE_MM,
        })
    if not sites:
        return {'has_data': False,
                'note': 'No site was measured in both sets — same sites, both times.'}
    try:
        span = (date.fromisoformat(latest['date']) - date.fromisoformat(base['date'])).days
    except ValueError:
        span = None
    moved = [s for s in sites if s['significant']]
    return {
        'has_data': True,
        'from_date': base['date'], 'to_date': latest['date'], 'span_days': span,
        'sites': sites,
        'noise_floor_mm': NOISE_MM,
        # The largest real movement, for the headline. None when nothing cleared
        # the floor — an honest "nothing measurably changed yet".
        'biggest': (max(moved, key=lambda s: abs(s['delta_mm'])) if moved else None),
        'unchanged': not moved,
    }


def vessel(data):
    """Everything the VESSEL renderer needs, fully derived. Pure function."""
    p = data.get('profile') or {}
    height = p.get('height_in') or 0
    tape_rows = sorted(data.get('measurements') or [], key=lambda m: m['date'])
    latest = tape_rows[-1] if tape_rows else None
    previous = tape_rows[-2] if len(tape_rows) > 1 else None
    bc = body_comp(data)

    # ── body ──
    if latest:
        confidence = {'current': 'measured', 'aging': 'measured',
                      'stale': 'stale'}.get(bc.get('confidence'), 'measured')
        tape = {k: latest.get(k) for k in VESSEL_SITES}
        measured = [k for k in VESSEL_SITES if latest.get(k)]
    elif height:
        confidence = 'estimated'
        tape = {k: round(height * f, 1) for k, f in TYPICAL_BY_HEIGHT.items()}
        measured = []
    else:
        # Factory figure: no tape, no height. Draw typical proportions at a
        # default height rather than nothing — an empty frame reads as broken,
        # and a broken-looking instrument never earns the first measurement.
        confidence = 'unmeasured'
        tape = {k: round(GENERIC_HEIGHT_IN * f, 1)
                for k, f in TYPICAL_BY_HEIGHT.items()}
        measured = []

    age_days = None
    if latest:
        try:
            age_days = (date.today() - date.fromisoformat(latest['date'])).days
        except ValueError:
            age_days = None

    body = {
        # There is always a figure to draw now — the ladder (full/estimated/
        # generic) says how much of it is real, and have gates nothing visual.
        'have': True,
        'confidence': confidence,
        'measured_on': latest['date'] if latest else None,
        'age_days': age_days,
        'height_in': height or None,
        'tape_in': tape,
        'measured_sites': measured,
        'previous_tape_in': ({k: previous.get(k) for k in VESSEL_SITES}
                             if previous else None),
        # How many rungs of the degradation ladder are lit. Drives opacity.
        'fidelity': ('full' if latest else 'estimated' if height else 'generic'),
    }

    # ── composition ──
    composition = {'have': bc.get('current') is not None,
                   'bf_pct': bc.get('current'),
                   'method': 'navy',
                   'confidence': bc.get('confidence'),
                   'age_days': bc.get('age_days')}

    # ── fuel ──
    totals = today_summary(data)['totals']
    energy = energy_balance(data)
    kcal_target = (energy.get('recommended_calories') if energy.get('has_data')
                   else p.get('daily_calories')) or None
    fuel = {
        'have': True,  # today always exists; the numbers may be zero and that is real
        'kcal': totals.get('calories', 0),
        'kcal_target': kcal_target,
        'protein_g': totals.get('protein', 0),
        'protein_target_g': p.get('daily_protein_g') or None,
        'target_source': ('adaptive_tdee' if energy.get('has_data')
                          else 'profile' if p.get('daily_calories') else None),
        'confidence': (energy.get('confidence') if energy.get('has_data')
                       else 'low'),
    }

    # ── load ──
    strain = training_strain(data)
    load = {'have': bool(strain.get('has_data')),
            'acr': strain.get('acwr'),
            'monotony': strain.get('monotony'),
            'state': strain.get('zone'),
            'corridor': [0.8, 1.3]}

    # ── voyage ──
    w = weight_stats(data)
    voyage = {'have': bool(w.get('has_data') is not False and w.get('current')),
              'start_lb': (w.get('series') or [{}])[0].get('weight') if w.get('series') else None,
              'current_lb': w.get('current'),
              'goal_lb': w.get('goal') or None,
              'rate_lb_wk': w.get('rate_per_week'),
              'eta': w.get('eta_date_iso'),
              'confidence': ('high' if len(w.get('series') or []) >= 8
                             else 'medium' if len(w.get('series') or []) >= 3
                             else 'low')}

    return {'as_of': datetime.now().isoformat(timespec='seconds'),
            'body': body, 'composition': composition, 'fuel': fuel,
            'load': load, 'voyage': voyage, 'change': tape_change(data)}


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
