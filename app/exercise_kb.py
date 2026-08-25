"""The form library: how to actually perform the movements the app
prescribes. Classic, widely-taught coaching content — setup, execution
cues, the faults every coach sees and their fixes, breathing, and safety.
Instructional reference, not medical advice; anything painful is a reason
to stop and get eyes on the lift, not to push through.

Names are matched the same loose way the standards ladder matches lifts:
lowercase substring with excludes, so "3x5 Back Squat (paused)" still
finds the squat guide.
"""

EXERCISES = {
    'Back Squat': {
        'aka': ('squat',),
        'exclude': ('front', 'split', 'bulgarian', 'hack', 'goblet'),
        'animated': True,
        'setup': [
            'Bar on the upper traps (high bar) or rear delts (low bar) — never the neck.',
            'Grip just outside shoulders, elbows pulled down, upper back tight.',
            'Feet shoulder-width, toes out 15–30°, bar over midfoot.',
        ],
        'cues': [
            'Big breath into the belly, brace like taking a punch.',
            'Break hips and knees together; sit down between the legs.',
            'Knees track over toes the whole way — pushed out, never caving.',
            'Depth: hip crease below the top of the knee.',
            'Drive the floor away; chest up out of the hole.',
        ],
        'faults': [
            ('Knees cave inward on the way up', 'Lighten the bar; cue "spread the floor"; strengthen abductors.'),
            ('Heels lift', 'Weight back over midfoot; work ankle mobility or raise the heels slightly.'),
            ('Good-morning squat (hips shoot up first)', 'Brace harder, slow the descent, lead with the chest on the drive.'),
        ],
        'breath': 'Breathe and brace at the top; hold through the rep; exhale over the sticking point or at lockout.',
        'safety': 'Squat in a rack with safeties set just below your bottom position. Learn to fail forward onto the safeties, not backward.',
    },
    'Bench Press': {
        'aka': ('bench',),
        'exclude': ('incline', 'decline', 'close', 'dumbbell', 'db'),
        'animated': True,
        'setup': [
            'Eyes under the bar, feet planted, glutes and shoulders on the bench.',
            'Shoulder blades pinched back and down — build a shelf.',
            'Grip so the forearms are vertical at the chest.',
        ],
        'cues': [
            'Unrack to over the shoulders, not over the face.',
            'Lower under control to the lower chest, elbows ~45–60° from the torso.',
            'Touch, do not bounce.',
            'Press slightly back toward the face — the bar path is a shallow J.',
            'Keep the wrists stacked over the elbows.',
        ],
        'faults': [
            ('Elbows flared to 90°', 'Tuck to ~45–60°; shoulders will thank you.'),
            ('Butt lifts off the bench', 'Lighter bar; plant the feet and keep tension without bridging.'),
            ('Bar drifts toward the belly', 'Touch lower chest, press back up and over the shoulders.'),
        ],
        'breath': 'Inhale at lockout, hold down-and-up, exhale past the sticking point.',
        'safety': 'Never bench heavy without safeties or a spotter. No suicide grip — thumbs around the bar.',
    },
    'Deadlift': {
        'aka': ('deadlift',),
        'exclude': ('romanian', 'rdl', 'stiff', 'single', 'deficit'),
        'animated': True,
        'setup': [
            'Bar over midfoot, about an inch from the shins.',
            'Hinge down and grip just outside the legs; shins touch the bar.',
            'Chest up, lats on ("protect your armpits"), back flat.',
        ],
        'cues': [
            'Pull the slack out of the bar before it leaves the floor.',
            'Push the floor away — the bar drags up the legs in a straight line.',
            'Hips and shoulders rise together.',
            'Finish tall: squeeze glutes, no lean-back.',
            'Return by hinging first, then bending the knees.',
        ],
        'faults': [
            ('Rounded lower back', 'Reset lighter; chest up, brace, film your setup from the side.'),
            ('Bar drifts away from the legs', 'Lats on; drag the bar up the shins and thighs.'),
            ('Hitching / knee re-bend at lockout', 'Lighter pull; drive hips through instead of leaning back.'),
        ],
        'breath': 'Breathe and brace at the floor before every pull; never mid-rep.',
        'safety': 'A neutral spine is the whole game. When in doubt, drop the weight — literally: a controlled drop beats a rounded save.',
    },
    'Overhead Press': {
        'aka': ('overhead press', 'ohp', 'military press', 'shoulder press'),
        'exclude': ('dumbbell', 'db', 'seated'),
        'animated': True,
        'setup': [
            'Bar racked on the front delts, grip just outside shoulders, forearms vertical.',
            'Feet hip-width, glutes and abs tight — the torso is a pillar.',
        ],
        'cues': [
            'Tuck the chin; press up past the face.',
            'Once the bar passes the forehead, push the head through.',
            'Lock out with the bar over the shoulder blades — arms by the ears.',
            'Squeeze glutes throughout; no lower-back arch.',
        ],
        'faults': [
            ('Leaning back to press', 'Squeeze glutes, brace abs; lighten until the torso stays vertical.'),
            ('Bar loops forward around the face', 'Chin tuck, vertical bar path, head through at the top.'),
            ('Wrists bent back', 'Bar low on the palm, knuckles up, wrist stacked over forearm.'),
        ],
        'breath': 'Breathe at the bottom, brace, press; exhale at or near lockout.',
        'safety': 'The lower back is the fuse: if it hurts, the brace failed or the weight is ego. Reset both.',
    },
    'Barbell Row': {
        'aka': ('barbell row', 'bent over row', 'bent-over row', 'pendlay'),
        'exclude': ('dumbbell', 'db', 'cable', 'seated', 'machine'),
        'animated': True,
        'setup': [
            'Hinge to ~45° (Pendlay: parallel), knees soft, back flat.',
            'Grip just outside the legs; let the bar hang under the shoulders.',
        ],
        'cues': [
            'Pull the bar to the lower ribs / upper belly.',
            'Elbows drive back, not out; squeeze the blades together at the top.',
            'Torso stays still — no heaving.',
            'Lower under control; a dead stop on the floor each rep keeps it honest.',
        ],
        'faults': [
            ('Body English / bouncing the torso', 'Drop weight; pause each rep at the top for a beat.'),
            ('Pulling with the biceps only', 'Think "elbows to the hips"; lead with the blades.'),
            ('Upper back rounds', 'Chest proud, brace, reduce range or load.'),
        ],
        'breath': 'Brace before each pull; exhale as the bar lowers.',
        'safety': 'The hinge position is a loaded spine position — treat setup as seriously as a deadlift.',
    },
    'Romanian Deadlift': {
        'aka': ('romanian', 'rdl'),
        'exclude': (),
        'animated': False,
        'setup': [
            'Start standing, bar in hands at the thighs (from a rack, not the floor).',
            'Soft knees — the angle barely changes for the whole set.',
        ],
        'cues': [
            'Push the hips straight back; the bar slides down the thighs.',
            'Go only as low as the flat back allows — usually mid-shin.',
            'Feel the hamstrings load like springs, then drive the hips forward.',
        ],
        'faults': [
            ('Turning it into a squat', 'Knees stay soft and still; the hips do the travel.'),
            ('Rounding at the bottom', 'Shorten the range; depth is earned by hamstring flexibility.'),
        ],
        'breath': 'Brace at the top of every rep.',
        'safety': 'A hamstring stretch is right; lower-back pump or pain means the back took over.',
    },
    'Lat Pulldown': {
        'aka': ('pulldown', 'lat pull'),
        'exclude': (),
        'animated': False,
        'setup': ['Thighs snug under the pads; grip a bit wider than shoulders.'],
        'cues': [
            'Slight lean back, chest up; pull the bar to the collarbones.',
            'Elbows down and into the sides — think "put your elbows in your pockets".',
            'Control the return to a full stretch without the plates crashing.',
        ],
        'faults': [
            ('Heaving backward each rep', 'Fix the torso angle; lighten the stack.'),
            ('Pulling behind the neck', 'To the collarbones — behind-neck adds risk and nothing else.'),
        ],
        'breath': 'Exhale on the pull, inhale on the return.',
        'safety': 'Shoulder-friendly by design; keep it that way with a full, controlled stretch.',
    },
    'Barbell Curl': {
        'aka': ('curl',),
        'exclude': ('leg', 'hamstring', 'nordic'),
        'animated': False,
        'setup': ['Grip shoulder-width, elbows pinned at the sides.'],
        'cues': [
            'Curl without the elbows drifting forward.',
            'Squeeze at the top; lower for a slow two-count.',
            'The torso is furniture: it does not move.',
        ],
        'faults': [
            ('Swinging the hips', 'Back against a wall kills it instantly; or halve the weight.'),
        ],
        'breath': 'Exhale up, inhale down.',
        'safety': 'Elbow tendons hate bouncing at the bottom — full control beats full stretch at speed.',
    },
    'Lateral Raise': {
        'aka': ('lateral', 'side raise', 'side lateral'),
        'exclude': (),
        'animated': False,
        'setup': ['Dumbbells at the sides, slight forward lean, soft elbows.'],
        'cues': [
            'Lead with the elbows out to the sides, up to shoulder height — no higher.',
            'Pinkies slightly up, like pouring two jugs.',
            'Lower slower than you lifted.',
        ],
        'faults': [
            ('Shrugging the traps', 'Lighter weight; think "long neck", push the shoulders down.'),
            ('Swinging', 'These are light by nature — 10–20s reps done strictly.'),
        ],
        'breath': 'Exhale up, inhale down.',
        'safety': 'Above shoulder height buys impingement, not delts.',
    },
    'Face Pull': {
        'aka': ('face pull',),
        'exclude': (),
        'animated': False,
        'setup': ['Rope at upper-chest height; step back until the stack floats.'],
        'cues': [
            'Pull the rope to the bridge of the nose, hands finishing beside the ears.',
            'External rotation at the end — knuckles point backward.',
            'Squeeze the rear delts and mid-back for a beat.',
        ],
        'faults': [
            ('Turning it into a row', 'Elbows high, hands to the face, lighter stack.'),
        ],
        'breath': 'Exhale on the pull.',
        'safety': 'The antidote to pressing volume — hard to do wrong at sensible weight.',
    },
    'Triceps Pushdown': {
        'aka': ('pushdown', 'tricep'),
        'exclude': (),
        'animated': False,
        'setup': ['Elbows pinned to the ribs; slight forward lean.'],
        'cues': ['Only the forearms move.', 'Full lockout, squeeze, controlled return to 90°.'],
        'faults': [('Elbows flaring and drifting', 'Lighter; pin the elbows and shorten the set.')],
        'breath': 'Exhale down, inhale up.',
        'safety': 'Elbow-friendly when strict; jerky lockouts are how elbows start clicking.',
    },
    'Incline Dumbbell Press': {
        'aka': ('incline',),
        'exclude': (),
        'animated': False,
        'setup': ['Bench at 30–45°; kick the dumbbells up from the knees.'],
        'cues': [
            'Lower to the upper chest, elbows ~45°.',
            'Press up and slightly in; dumbbells finish over the collarbones.',
        ],
        'faults': [('Bench too steep', '30–45° hits upper chest; 60°+ is a shoulder press.')],
        'breath': 'Inhale down, exhale up.',
        'safety': 'Never drop dumbbells outward past a dead stretch — bail them toward the hips.',
    },
    'Dips': {
        'aka': ('dip',),
        'exclude': (),
        'animated': False,
        'setup': ['Full support at lockout, slight forward lean for chest emphasis.'],
        'cues': ['Lower until the upper arms are about parallel.', 'Press without the shoulders rolling forward.'],
        'faults': [('Sinking too deep', 'Depth past parallel loads the shoulder capsule — earn it slowly.')],
        'breath': 'Inhale down, exhale up.',
        'safety': 'If the collarbone-front aches, cut depth or swap for incline press.',
    },
    'Walking Lunge': {
        'aka': ('lunge',),
        'exclude': (),
        'animated': False,
        'setup': ['Torso tall, steps long enough for a vertical front shin.'],
        'cues': ['Back knee kisses the floor.', 'Drive through the front heel; travel, do not bounce.'],
        'faults': [('Knee dives past the toes', 'Longer stride; weight through the heel.')],
        'breath': 'Exhale on each drive.',
        'safety': 'Balance first, load second — bodyweight until the wobble is gone.',
    },
    'Hanging Leg Raise': {
        'aka': ('leg raise',),
        'exclude': (),
        'animated': False,
        'setup': ['Dead hang, shoulders packed (pulled down away from the ears).'],
        'cues': ['Curl the pelvis — tailbone tucks under as the legs rise.', 'Lower with control; no swinging between reps.'],
        'faults': [('Hip-flexor swing with a flat back', 'The rep starts when the pelvis tilts; bend the knees to regress.')],
        'breath': 'Exhale as the legs rise.',
        'safety': 'Kipping is for another sport.',
    },
    'Plank': {
        'aka': ('plank',),
        'exclude': (),
        'animated': False,
        'setup': ['Elbows under shoulders, feet together, one straight line ear-to-ankle.'],
        'cues': ['Squeeze glutes, tuck the pelvis slightly, push the floor away.', 'Stop the set when the hips sag — that rep is over.'],
        'faults': [('Sagging hips / raised butt', 'Shorter, harder holds beat long saggy ones.')],
        'breath': 'Keep breathing — a plank you cannot breathe in is too hard.',
        'safety': 'Pain-free by definition; lower-back complaints mean the pelvis lost its tuck.',
    },
}


def lookup(name):
    """Loose match: lowercase substring with excludes, longest alias wins."""
    n = (name or '').lower()
    best, best_len = None, 0
    for canon, e in EXERCISES.items():
        for alias in (canon.lower(),) + tuple(e['aka']):
            if alias in n and not any(x in n for x in e['exclude']):
                if len(alias) > best_len:
                    best, best_len = canon, len(alias)
    if not best:
        return None
    e = EXERCISES[best]
    return {'name': best, 'animated': e['animated'], 'setup': e['setup'],
            'cues': e['cues'],
            'faults': [{'fault': f, 'fix': fx} for f, fx in e['faults']],
            'breath': e['breath'], 'safety': e['safety']}


def catalog():
    return [{'name': k, 'animated': v['animated']} for k, v in EXERCISES.items()]
