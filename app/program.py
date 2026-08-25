"""The program engine: the app writes the training block, not just records it.

Deterministic periodization — no AI, no network, pure arithmetic that a
lifter can audit. The shape is the classic four-lift wave cycle (the 5/3/1
family): three loading weeks, a deload, a training-max bump, three more
loading weeks, and a final week that tests the new max. Every number
derives from the user's own logged lifts; anything estimated says so.

The engine deliberately composes with what already exists rather than
duplicating it: training maxes come from the same 90-day e1RM sweep the
strength-standards ladder uses, accessories are chosen against the
muscle-balance engine's weakest groups, and the daily auto-regulation
factor is applied at session start by the frontend, not baked in here.
"""
from datetime import date

from . import stats

MAIN_LIFTS = ('Overhead Press', 'Deadlift', 'Bench Press', 'Back Squat')
LOWER = ('Back Squat', 'Deadlift')          # +10 lb TM bump; upper gets +5

# Conservative bodyweight multiples for a lift never logged. These start a
# beginner light on purpose: a first block that is too easy costs a week,
# one that is too heavy costs a shoulder.
FALLBACK_RATIO = {'Back Squat': 0.80, 'Bench Press': 0.60,
                  'Deadlift': 1.00, 'Overhead Press': 0.40}

# (percent of TM, reps, amrap?) per loading week; week 4 is the deload.
WAVES = {
    1: ((65, 5, False), (75, 5, False), (85, 5, True)),
    2: ((70, 3, False), (80, 3, False), (90, 3, True)),
    3: ((75, 5, False), (85, 3, False), (95, 1, True)),
    4: ((40, 5, False), (50, 5, False), (60, 5, False)),
}

# Accessory pools keyed by the muscle-balance group they feed.
ACCESSORY_POOL = {
    'Back': ('Barbell Row', 'Lat Pulldown'),
    'Chest': ('Incline Dumbbell Press', 'Dips'),
    'Shoulders': ('Lateral Raise', 'Face Pull'),
    'Arms': ('Barbell Curl', 'Triceps Pushdown'),
    'Legs': ('Romanian Deadlift', 'Walking Lunge'),
    'Core': ('Hanging Leg Raise', 'Plank'),
}

ALL_GROUPS = tuple(ACCESSORY_POOL)


def _round5(x):
    return int(round(x / 5.0) * 5)


def _training_maxes(data):
    """TM = 90% of the best 90-day e1RM per lift; bodyweight fallback."""
    ss = stats.strength_standards(data)
    best = {l['lift']: l['e1rm'] for l in ss.get('lifts', [])} if ss.get('has_data') else {}
    weights = sorted(data.get('weights', []), key=lambda w: w['date'])
    bw = weights[-1]['weight'] if weights else (data['profile'].get('weight') or 180)
    tms = {}
    for lift in MAIN_LIFTS:
        if lift in best:
            tms[lift] = {'tm': _round5(best[lift] * 0.9), 'estimated': False,
                         'source': f"90% of your {best[lift]} lb e1RM"}
        else:
            tms[lift] = {'tm': _round5(bw * FALLBACK_RATIO[lift] * 0.9),
                         'estimated': True,
                         'source': f'estimated from {round(bw)} lb bodyweight — '
                                   'log the lift and regenerate to true it up'}
    return tms


def _weak_groups(data):
    """The two muscle-balance groups getting the least volume; on a young
    log (no balance data) default to the classically neglected pair."""
    mb = stats.muscle_balance(data)
    groups = mb.get('groups') or []
    trained = {g['group']: g['pct'] for g in groups}
    ranked = sorted(ALL_GROUPS, key=lambda g: trained.get(g, 0))
    return ranked[:2]


def generate(data, days=4):
    """Build the 8-week block. Pure function of the data file."""
    days = 4 if days not in (3, 4) else days
    tms = _training_maxes(data)
    weak = _weak_groups(data)
    accessories = [ACCESSORY_POOL[g][0] for g in weak] \
        + [ACCESSORY_POOL[g][1] for g in weak]

    weeks = []
    for wk in range(1, 9):
        # weeks 1-3 -> waves 1-3, week 4 deload, weeks 5-7 -> waves 1-3
        # again (with bumped TMs), week 8 deload-and-test.
        wave = WAVES[4] if wk in (4, 8) else WAVES[wk if wk < 4 else wk - 4]
        bump = wk >= 5
        sessions = []
        lifts = MAIN_LIFTS if days == 4 else MAIN_LIFTS[:3] if wk % 2 else MAIN_LIFTS[1:]
        for i, lift in enumerate(lifts):
            tm = tms[lift]['tm'] + (bump and (10 if lift in LOWER else 5) or 0)
            sets = [{'pct': p, 'reps': r, 'amrap': a,
                     'weight': max(45, _round5(tm * p / 100))}
                    for p, r, a in wave]
            sessions.append({
                'lift': lift,
                'sets': sets,
                'supplemental': {'exercise': lift, 'sets': 5, 'reps': 5,
                                 'weight': max(45, _round5(tm * 0.65))},
                'accessories': [accessories[i % len(accessories)],
                                accessories[(i + 1) % len(accessories)]],
            })
        weeks.append({'week': wk, 'deload': wk in (4, 8),
                      'test': wk == 8, 'sessions': sessions})
    return {
        'created': date.today().isoformat(),
        'method': 'wave-531', 'days_per_week': days,
        'tms': tms, 'weak_groups': weak, 'weeks': weeks,
    }


def status(data):
    """Where the block stands today: computed, never stored, so it cannot
    drift from the calendar. Sessions-done counts this week's logged
    workouts that contain a programmed main lift."""
    prog = data.get('program')
    if not prog:
        return {'has_program': False}
    try:
        started = date.fromisoformat(prog['created'])
    except (KeyError, ValueError):
        return {'has_program': False}
    week = min(8, max(1, (date.today() - started).days // 7 + 1))
    finished = (date.today() - started).days >= 56
    wk = prog['weeks'][week - 1]
    iso_week = date.today().isocalendar()[:2]
    done = 0
    for w in data.get('workouts', []):
        try:
            d = date.fromisoformat(w['date'])
        except (KeyError, ValueError):
            continue
        if d.isocalendar()[:2] != iso_week:
            continue
        names = ' '.join((e.get('exercise') or '').lower()
                         for e in w.get('exercises', []))
        if any(l.lower() in names for l in MAIN_LIFTS):
            done += 1
    nxt = wk['sessions'][min(done, len(wk['sessions']) - 1)]
    return {'has_program': True, 'week': week, 'deload': wk['deload'],
            'test': wk['test'], 'finished': finished,
            'done_this_week': done,
            'sessions_this_week': len(wk['sessions']),
            'next_session': nxt}
