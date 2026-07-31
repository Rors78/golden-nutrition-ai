import streamlit as st
import json
import copy
import anthropic
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
import plotly.express as px

# Configuration
DATA_FILE = Path("nutrition_data.json")
CLAUDE_MODEL = "claude-opus-5"

DEFAULT_DATA = {
    'profile': {
        'name': '',
        'weight': 0,
        'goal_weight': 0,
        'daily_protein_g': 150,
        'daily_calories': 2000
    },
    'meals': [],
    'workouts': [],
    'supplements': [],
    'supplement_schedule': [],
    'weights': []
}

MACRO_FIELDS = ('protein', 'calories', 'carbs', 'fat', 'fiber')

# Page config
st.set_page_config(page_title="Golden Nutrition AI", layout="wide", page_icon="🏋️")


def load_data():
    """Load user data, recovering gracefully from a corrupted file."""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            data.setdefault('weights', [])
            data.setdefault('supplement_schedule', [])
            return data
        except (json.JSONDecodeError, OSError):
            backup = DATA_FILE.with_name(DATA_FILE.name + '.corrupt')
            DATA_FILE.replace(backup)
            st.warning(f"Data file was unreadable — backed it up to {backup} and started fresh.")
    return copy.deepcopy(DEFAULT_DATA)


# Initialize session state
if 'user_data' not in st.session_state:
    st.session_state.user_data = load_data()


def save_data():
    """Save user data atomically so a crash mid-write can't corrupt the file."""
    tmp = DATA_FILE.with_name(DATA_FILE.name + '.tmp')
    with open(tmp, 'w') as f:
        json.dump(st.session_state.user_data, f, indent=2)
    tmp.replace(DATA_FILE)


def _clean_num(v, cast=int):
    """Coerce a data_editor cell to a number, treating blanks/NaN as 0."""
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return cast(0)
        return cast(v)
    except (TypeError, ValueError):
        return cast(0)


def history_editor(list_key, window_start, int_fields=(), float_fields=(), bool_fields=(), post_process=None):
    """Inline-editable history table: edit cells, add rows, or delete rows, then save."""
    entries = st.session_state.user_data.setdefault(list_key, [])
    recent = [e for e in entries if e.get('date', '') >= window_start]
    older = [e for e in entries if e.get('date', '') < window_start]
    if not recent:
        return False

    df = pd.DataFrame(recent).sort_values('date', ascending=False).reset_index(drop=True)
    st.caption("Edit cells directly, add rows with ＋, or tick rows and press the 🗑 to delete. Then save.")
    edited = st.data_editor(df, num_rows="dynamic", key=f"edit_{list_key}", width="stretch")

    if st.button("💾 Save table changes", key=f"save_{list_key}"):
        cleaned = []
        for r in edited.to_dict('records'):
            row = {}
            for k, v in r.items():
                if k in int_fields:
                    v = _clean_num(v, int)
                elif k in float_fields:
                    v = _clean_num(v, float)
                elif k in bool_fields:
                    v = bool(v) and not (isinstance(v, float) and pd.isna(v))
                elif v is None or (isinstance(v, float) and pd.isna(v)):
                    v = ''
                row[k] = v
            if not str(row.get('date', '')).strip():
                continue  # a new row without a date isn't a real entry
            row['date'] = str(row['date'])[:10]
            cleaned.append(row)
        st.session_state.user_data[list_key] = older + cleaned
        if post_process:
            post_process()
        save_data()
        st.success("Changes saved")
        st.rerun()
    return True


# ---------------------------------------------------------------------------
# Claude AI helpers
# ---------------------------------------------------------------------------

MEAL_SCHEMA = {
    "type": "object",
    "properties": {
        "meals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Short name for the meal or food item"},
                    "protein": {"type": "integer", "description": "Estimated protein in grams"},
                    "calories": {"type": "integer", "description": "Estimated calories"},
                    "carbs": {"type": "integer", "description": "Estimated carbohydrates in grams"},
                    "fat": {"type": "integer", "description": "Estimated fat in grams"},
                    "fiber": {"type": "integer", "description": "Estimated fiber in grams"}
                },
                "required": ["name", "protein", "calories", "carbs", "fat", "fiber"],
                "additionalProperties": False
            }
        }
    },
    "required": ["meals"],
    "additionalProperties": False
}


@st.cache_resource
def get_claude_client():
    # Resolves credentials from ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
    # or an `ant auth login` profile
    return anthropic.Anthropic()


def _claude_create(**kwargs):
    """Call the Messages API with server-side refusal fallbacks when available."""
    client = get_claude_client()
    try:
        return client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **kwargs,
        )
    except TypeError:
        # Older SDK without the fallbacks parameter — plain call
        return client.messages.create(**kwargs)


def parse_meals_with_ai(description):
    """Turn a plain-language meal description into structured macro estimates."""
    response = _claude_create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=(
            "You are a nutrition expert. The user describes food they ate in plain "
            "language. Break it into individual meals/items and estimate protein (g), "
            "calories, carbs (g), fat (g), and fiber (g) for each, assuming realistic "
            "typical portion sizes unless quantities are given. Round to sensible "
            "whole numbers."
        ),
        messages=[{"role": "user", "content": description}],
        output_config={"format": {"type": "json_schema", "schema": MEAL_SCHEMA}},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to process this description.")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["meals"]


def generate_coaching_summary(week_data):
    """Ask Claude for a weekly coaching summary based on tracked data."""
    response = _claude_create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=(
            "You are Golden Nutrition AI, an expert fitness and nutrition coach for a "
            "dedicated lifter following a push/pull/legs program. Be direct, specific, "
            "and use the actual numbers from the data. Keep it under 400 words."
        ),
        messages=[{
            "role": "user",
            "content": (
                "Here is my last 7 days of tracking data as JSON:\n\n"
                f"{json.dumps(week_data, indent=2)}\n\n"
                "Give me a weekly coaching summary in markdown with three sections: "
                "**What went well**, **What to fix**, and **The one change for next week** "
                "(the single highest-impact adjustment)."
            ),
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to process this request.")
    return next(b.text for b in response.content if b.type == "text")


def show_ai_error(e):
    if isinstance(e, anthropic.AuthenticationError):
        st.error(
            "No valid Claude API credentials found. Set the ANTHROPIC_API_KEY "
            "environment variable (or run `ant auth login`), then restart the app."
        )
    else:
        st.error(f"AI request failed: {e}")


# Header
st.title("🏋️ Golden Nutrition AI")
st.subheader("Smart Fitness & Nutrition Tracking")

# Sidebar - User Profile
with st.sidebar:
    st.header("👤 Profile")

    profile = st.session_state.user_data['profile']

    name = st.text_input("Name", value=profile.get('name', ''))
    weight = st.number_input("Current Weight (lbs)", min_value=0, value=int(profile.get('weight', 0)), step=1)
    goal_weight = st.number_input("Goal Weight (lbs)", min_value=0, value=int(profile.get('goal_weight', 0)), step=1)
    daily_protein = st.number_input("Daily Protein Goal (g)", min_value=0, value=profile.get('daily_protein_g', 150), step=5)
    daily_calories = st.number_input("Daily Calorie Goal", min_value=0, value=profile.get('daily_calories', 2000), step=100)

    if st.button("Save Profile"):
        st.session_state.user_data['profile'] = {
            'name': name,
            'weight': weight,
            'goal_weight': goal_weight,
            'daily_protein_g': daily_protein,
            'daily_calories': daily_calories
        }
        save_data()
        st.success("Profile saved!")

    with st.expander("💾 Export Data (CSV)"):
        for key, label in [('meals', 'Meals'), ('workouts', 'Workouts'),
                           ('supplements', 'Supplements'), ('weights', 'Weigh-Ins')]:
            rows = st.session_state.user_data.get(key, [])
            if rows:
                st.download_button(f"⬇️ {label}",
                                   pd.DataFrame(rows).to_csv(index=False),
                                   file_name=f"{key}.csv", mime="text/csv",
                                   key=f"dl_{key}")
        if not any(st.session_state.user_data.get(k) for k in ('meals', 'workouts', 'supplements', 'weights')):
            st.caption("Nothing to export yet.")

# Main tabs
tab1, tab_weight, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard",
    "⚖️ Weight",
    "🍽️ Meal Tracker",
    "🏋️ Workout Log",
    "💊 Supplements",
    "🧠 AI Insights"
])

# TAB 1: Dashboard
with tab1:
    st.header("Today's Summary")

    # Goals come from the saved profile, not the live sidebar widgets
    saved_profile = st.session_state.user_data['profile']
    protein_goal = saved_profile.get('daily_protein_g', 150)
    calorie_goal = saved_profile.get('daily_calories', 2000)

    if saved_profile.get('weight') and saved_profile.get('goal_weight'):
        diff = saved_profile['weight'] - saved_profile['goal_weight']
        if diff == 0:
            st.caption(f"Weight: {saved_profile['weight']} lbs — at goal! 🎯")
        else:
            direction = "to lose" if diff > 0 else "to gain"
            st.caption(f"Weight: {saved_profile['weight']} lbs → goal {saved_profile['goal_weight']} lbs ({abs(diff)} lbs {direction})")

    today = date.today().isoformat()

    # Filter today's data
    today_meals = [m for m in st.session_state.user_data['meals'] if m['date'] == today]
    today_workouts = [w for w in st.session_state.user_data['workouts'] if w['date'] == today]

    # Calculate totals
    totals = {f: sum(m.get(f, 0) for m in today_meals) for f in MACRO_FIELDS}

    # Metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        protein_pct = min(100, (totals['protein'] / protein_goal * 100) if protein_goal > 0 else 0)
        st.metric("Protein", f"{totals['protein']}g / {protein_goal}g", f"{protein_pct:.0f}%")

    with col2:
        cal_pct = min(100, (totals['calories'] / calorie_goal * 100) if calorie_goal > 0 else 0)
        st.metric("Calories", f"{totals['calories']} / {calorie_goal}", f"{cal_pct:.0f}%")

    with col3:
        st.metric("Meals Logged", len(today_meals))

    with col4:
        st.metric("Workouts", len(today_workouts))

    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("Carbs", f"{totals['carbs']}g")
    with col6:
        st.metric("Fat", f"{totals['fat']}g")
    with col7:
        st.metric("Fiber", f"{totals['fiber']}g")

    # Progress bars
    st.markdown("### Today's Progress")
    st.progress(protein_pct / 100, text=f"Protein: {protein_pct:.0f}%")
    st.progress(cal_pct / 100, text=f"Calories: {cal_pct:.0f}%")

    # Recent activity
    st.markdown("### Recent Meals")
    if today_meals:
        for meal in sorted(today_meals, key=lambda m: m.get('time', ''))[-3:]:
            st.markdown(f"**{meal['time']}** - {meal['name']}: {meal.get('protein', 0)}g protein, {meal.get('calories', 0)} cal")
    else:
        st.info("No meals logged today")

    st.markdown("### Recent Workouts")
    if today_workouts:
        for workout in sorted(today_workouts, key=lambda w: w.get('time', ''))[-2:]:
            st.markdown(f"**{workout['time']}** - {workout['name']} ({workout.get('duration', 0)} min)")
    else:
        st.info("No workouts logged today")

# TAB: Weight Tracker
with tab_weight:
    st.header("⚖️ Weight Tracker")

    saved_profile = st.session_state.user_data['profile']
    weights = st.session_state.user_data.setdefault('weights', [])

    col1, col2 = st.columns(2)
    with col1:
        weigh_date = st.date_input("Date", value=date.today(), key="weigh_date")
        default_weight = float(saved_profile.get('weight') or 0) or 200.0
        weigh_lbs = st.number_input("Weight (lbs)", min_value=0.0, value=default_weight, step=0.5, key="weigh_lbs")

    if st.button("Log Weigh-In"):
        if weigh_lbs <= 0:
            st.error("Please enter a weight above 0.")
        else:
            # One entry per day — a re-log replaces that day's entry
            weights[:] = [w for w in weights if w['date'] != weigh_date.isoformat()]
            weights.append({'date': weigh_date.isoformat(), 'weight': weigh_lbs})
            weights.sort(key=lambda w: w['date'])
            # Keep the profile's current weight in sync with the latest weigh-in
            st.session_state.user_data['profile']['weight'] = weights[-1]['weight']
            save_data()
            st.success(f"Logged: {weigh_lbs} lbs")
            st.rerun()

    if weights:
        current = weights[-1]['weight']
        goal = saved_profile.get('goal_weight', 0)

        # Change over the last 7 days: compare to the oldest entry within the window
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        window = [w for w in weights if w['date'] >= week_ago]
        change_7d = current - window[0]['weight'] if len(window) > 1 else None

        # Trend from the last 30 days of entries
        month_ago = (date.today() - timedelta(days=30)).isoformat()
        trend_window = [w for w in weights if w['date'] >= month_ago]
        rate_per_week = None
        if len(trend_window) > 1:
            first, last = trend_window[0], trend_window[-1]
            days_span = (date.fromisoformat(last['date']) - date.fromisoformat(first['date'])).days
            if days_span > 0:
                rate_per_week = (last['weight'] - first['weight']) / days_span * 7

        col1, col2, col3 = st.columns(3)
        with col1:
            # When cutting, a negative change is good news
            good_direction = "inverse" if (goal and goal < current) else "normal"
            st.metric("Current Weight", f"{current:.1f} lbs",
                      delta=f"{change_7d:+.1f} lbs (7d)" if change_7d is not None else None,
                      delta_color=good_direction)
        with col2:
            if goal:
                st.metric("To Goal", f"{abs(current - goal):.1f} lbs",
                          help=f"Goal: {goal} lbs (set in Profile)")
            else:
                st.metric("To Goal", "—", help="Set a goal weight in the Profile sidebar")
        with col3:
            st.metric("Trend", f"{rate_per_week:+.1f} lbs/week" if rate_per_week is not None else "—",
                      help="Based on the last 30 days of weigh-ins")

        # Projected goal date from the current trend
        if goal and rate_per_week is not None and abs(rate_per_week) >= 0.05:
            to_go = goal - current
            if to_go == 0:
                st.success("🎯 You're at your goal weight!")
            elif (to_go < 0) == (rate_per_week < 0):
                days_needed = abs(to_go / (rate_per_week / 7))
                eta = date.today() + timedelta(days=round(days_needed))
                st.info(f"📅 At your current rate of {rate_per_week:+.1f} lbs/week, "
                        f"you'll reach {goal} lbs around **{eta.strftime('%B %d, %Y')}** "
                        f"({round(days_needed)} days).")
            else:
                st.warning(f"⚠️ Your current trend ({rate_per_week:+.1f} lbs/week) is moving "
                           f"away from your goal of {goal} lbs.")

        # Weight chart
        df_w = pd.DataFrame(weights)
        df_w.columns = ['Date', 'Weight']
        fig = px.line(df_w, x='Date', y='Weight', markers=True,
                      title='Weight Over Time', labels={'Weight': 'Weight (lbs)'})
        if goal:
            fig.add_hline(y=goal, line_dash="dash", annotation_text=f"Goal: {goal} lbs",
                          line_color="green")
        st.plotly_chart(fig, width="stretch")

        # Editable history
        st.markdown("### Weigh-In History")

        def _sync_weights():
            ws = st.session_state.user_data['weights']
            ws.sort(key=lambda w: w['date'])
            if ws:
                st.session_state.user_data['profile']['weight'] = ws[-1]['weight']

        history_editor('weights', window_start='0000-00-00',
                       float_fields=('weight',), post_process=_sync_weights)
    else:
        st.info("No weigh-ins yet. Log your first one above — daily weigh-ins give the best trend data.")

# TAB 2: Meal Tracker
with tab2:
    st.header("🍽️ Log Meal")

    # AI quick log
    st.markdown("### 🤖 AI Quick Log")
    st.caption("Describe what you ate in plain language — Claude estimates the macros. Entries are logged with today's date and the current time.")

    ai_desc = st.text_input("What did you eat?",
                            placeholder="e.g., chicken burrito with rice and beans, and a protein shake",
                            key="ai_meal_desc")
    if st.button("Estimate with AI"):
        if not ai_desc.strip():
            st.error("Describe what you ate first.")
        else:
            with st.spinner("Asking Claude..."):
                try:
                    st.session_state.ai_parsed_meals = parse_meals_with_ai(ai_desc.strip())
                except Exception as e:
                    show_ai_error(e)

    if st.session_state.get('ai_parsed_meals'):
        parsed = st.session_state.ai_parsed_meals
        st.dataframe(pd.DataFrame(parsed), width="stretch")
        total_p = sum(m['protein'] for m in parsed)
        total_c = sum(m['calories'] for m in parsed)
        st.caption(f"Total: {total_p}g protein, {total_c} calories")

        col_add, col_discard = st.columns(2)
        with col_add:
            if st.button("✅ Add All to Log"):
                now = datetime.now().time().strftime("%H:%M")
                for m in parsed:
                    st.session_state.user_data['meals'].append({
                        'date': date.today().isoformat(),
                        'time': now,
                        'name': m['name'],
                        'protein': m['protein'],
                        'calories': m['calories'],
                        'carbs': m.get('carbs', 0),
                        'fat': m.get('fat', 0),
                        'fiber': m.get('fiber', 0),
                        'notes': 'Estimated by Claude'
                    })
                save_data()
                del st.session_state.ai_parsed_meals
                st.success(f"Added {len(parsed)} meal(s)")
                st.rerun()
        with col_discard:
            if st.button("❌ Discard"):
                del st.session_state.ai_parsed_meals
                st.rerun()

    # Quick add from history
    all_meals = st.session_state.user_data['meals']
    if all_meals:
        st.markdown("### ⭐ Quick Add")
        st.caption("Re-log a meal you've had before — added with today's date and the current time.")
        seen, favorites = set(), []
        for m in reversed(all_meals):  # most recent first
            key = m['name'].strip().lower()
            if key and key not in seen:
                seen.add(key)
                favorites.append(m)
            if len(favorites) >= 12:
                break

        fav_idx = st.selectbox(
            "Recent meals", range(len(favorites)),
            format_func=lambda i: (f"{favorites[i]['name']} — {favorites[i].get('protein', 0)}g P / "
                                   f"{favorites[i].get('calories', 0)} cal"),
            key="quick_add_meal")
        if st.button("➕ Quick Add"):
            src = favorites[fav_idx]
            st.session_state.user_data['meals'].append({
                'date': date.today().isoformat(),
                'time': datetime.now().time().strftime("%H:%M"),
                'name': src['name'],
                'protein': src.get('protein', 0),
                'calories': src.get('calories', 0),
                'carbs': src.get('carbs', 0),
                'fat': src.get('fat', 0),
                'fiber': src.get('fiber', 0),
                'notes': src.get('notes', '')
            })
            save_data()
            st.success(f"Added: {src['name']}")
            st.rerun()

    st.markdown("---")
    st.markdown("### Manual Entry")

    col1, col2, col3 = st.columns(3)

    with col1:
        meal_date = st.date_input("Date", value=date.today())
        meal_time = st.time_input("Time", value=datetime.now().time())
        meal_name = st.text_input("Meal Name", placeholder="e.g., Chicken & Rice")

    with col2:
        protein = st.number_input("Protein (g)", min_value=0, value=30, step=5)
        calories = st.number_input("Calories", min_value=0, value=400, step=50)
        notes = st.text_area("Notes", placeholder="Optional notes...", key="meal_notes")

    with col3:
        carbs = st.number_input("Carbs (g)", min_value=0, value=0, step=5)
        fat = st.number_input("Fat (g)", min_value=0, value=0, step=5)
        fiber = st.number_input("Fiber (g)", min_value=0, value=0, step=1)

    if st.button("Add Meal"):
        if not meal_name.strip():
            st.error("Please enter a meal name before adding.")
        else:
            meal = {
                'date': meal_date.isoformat(),
                'time': meal_time.strftime("%H:%M"),
                'name': meal_name.strip(),
                'protein': protein,
                'calories': calories,
                'carbs': carbs,
                'fat': fat,
                'fiber': fiber,
                'notes': notes
            }
            st.session_state.user_data['meals'].append(meal)
            save_data()
            st.success(f"Added: {meal_name}")
            st.rerun()

    # Editable recent history
    st.markdown("### Recent Meals (Last 7 Days)")
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    if not history_editor('meals', window_start=week_ago,
                          int_fields=('protein', 'calories', 'carbs', 'fat', 'fiber')):
        st.info("No meals logged in the last 7 days")

# TAB 3: Workout Log
with tab3:
    st.header("🏋️ Log Workout")

    col1, col2 = st.columns(2)

    with col1:
        workout_date = st.date_input("Workout Date", value=date.today(), key="workout_date")
        workout_time = st.time_input("Time", value=datetime.now().time(), key="workout_time")
        workout_type = st.selectbox("Workout Type", [
            "Push Day A (Cutler Mode)",
            "Pull Day A (Cutler Mode)",
            "Leg Day A (Cutler Mode)",
            "Push Day B",
            "Pull Day B",
            "Leg Day B",
            "Cardio",
            "Custom"
        ])

    with col2:
        duration = st.number_input("Duration (minutes)", min_value=0, value=60, step=5)
        intensity = st.select_slider("Intensity", options=["Light", "Moderate", "Hard", "Very Hard"])
        workout_notes = st.text_area("Notes", placeholder="Optional notes...", key="workout_notes_area")

    st.markdown("#### Exercises")
    st.caption("Add a row per exercise — this powers the progression charts below.")
    ex_df = st.data_editor(
        pd.DataFrame([{"Exercise": "", "Sets": 3, "Reps": 10, "Weight (lbs)": 0.0}]),
        num_rows="dynamic", key="exercise_editor", width="stretch")

    if st.button("Add Workout"):
        exercises = []
        for r in ex_df.to_dict('records'):
            ex_name = str(r.get('Exercise') or '').strip()
            if not ex_name or (isinstance(r.get('Exercise'), float) and pd.isna(r.get('Exercise'))):
                continue
            exercises.append({
                'exercise': ex_name,
                'sets': _clean_num(r.get('Sets'), int),
                'reps': _clean_num(r.get('Reps'), int),
                'weight': _clean_num(r.get('Weight (lbs)'), float),
            })
        workout = {
            'date': workout_date.isoformat(),
            'time': workout_time.strftime("%H:%M"),
            'name': workout_type,
            'duration': duration,
            'intensity': intensity,
            'notes': workout_notes,
            'exercises': exercises
        }
        st.session_state.user_data['workouts'].append(workout)
        save_data()
        if "exercise_editor" in st.session_state:
            del st.session_state["exercise_editor"]
        st.success(f"Logged: {workout_type}" + (f" with {len(exercises)} exercise(s)" if exercises else ""))
        st.rerun()

    # Progression tracking
    all_exercise_rows = []
    for w in st.session_state.user_data['workouts']:
        for ex in w.get('exercises', []):
            if ex.get('exercise'):
                all_exercise_rows.append({
                    'date': w['date'],
                    'exercise': ex['exercise'],
                    'sets': ex.get('sets', 0),
                    'reps': ex.get('reps', 0),
                    'weight': ex.get('weight', 0),
                })

    if all_exercise_rows:
        st.markdown("### 📈 Progression")
        ex_names = sorted({r['exercise'] for r in all_exercise_rows})
        sel_ex = st.selectbox("Exercise", ex_names, key="prog_ex")
        rows = [r for r in all_exercise_rows if r['exercise'] == sel_ex]

        by_date = {}
        for r in rows:
            d = by_date.setdefault(r['date'], {'top': 0.0, 'volume': 0.0})
            d['top'] = max(d['top'], r['weight'])
            d['volume'] += r['sets'] * r['reps'] * r['weight']

        pr_weight = max(d['top'] for d in by_date.values())
        best_volume = max(d['volume'] for d in by_date.values())

        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            st.metric("All-Time PR", f"{pr_weight:g} lbs")
        with pc2:
            st.metric("Best Day Volume", f"{best_volume:,.0f} lbs",
                      help="sets × reps × weight, summed for the day")
        with pc3:
            st.metric("Sessions", len(by_date))

        df_prog = pd.DataFrame(
            [{'Date': d, 'Top Weight': v['top'], 'Volume': v['volume']} for d, v in sorted(by_date.items())]
        )
        fig_w = px.line(df_prog, x='Date', y='Top Weight', markers=True,
                        title=f'{sel_ex} — Top Weight Over Time',
                        labels={'Top Weight': 'Top Weight (lbs)'})
        st.plotly_chart(fig_w, width="stretch")

        fig_v = px.bar(df_prog, x='Date', y='Volume',
                       title=f'{sel_ex} — Training Volume Over Time',
                       labels={'Volume': 'Volume (lbs)'})
        st.plotly_chart(fig_v, width="stretch")

    # Show recent workouts
    st.markdown("### Recent Workouts (Last 7 Days)")

    week_ago = (date.today() - timedelta(days=7)).isoformat()
    recent_workouts = [w for w in st.session_state.user_data['workouts'] if w['date'] >= week_ago]

    if recent_workouts:
        display_rows = []
        for w in recent_workouts:
            row = {k: v for k, v in w.items() if k != 'exercises'}
            row['exercises'] = ", ".join(
                f"{e['exercise']} {e.get('sets', 0)}x{e.get('reps', 0)}@{e.get('weight', 0):g}"
                for e in w.get('exercises', [])) or "—"
            display_rows.append(row)
        df = pd.DataFrame(display_rows).sort_values('date', ascending=False)
        st.dataframe(df, width="stretch")

        # Workouts keep the classic delete mode: the nested exercise data
        # doesn't round-trip safely through an editable table
        if st.checkbox("Delete mode", key="workout_delete_mode"):
            workout_to_delete = st.selectbox("Select workout to delete",
                                            range(len(recent_workouts)),
                                            format_func=lambda x: f"{recent_workouts[x]['date']} {recent_workouts[x]['time']} - {recent_workouts[x]['name']}")
            if st.button("Delete Selected Workout"):
                st.session_state.user_data['workouts'].remove(recent_workouts[workout_to_delete])
                save_data()
                st.success("Workout deleted")
                st.rerun()
    else:
        st.info("No workouts logged in the last 7 days")

    # Cutler Mode workout templates
    with st.expander("📋 Cutler Mode Workout Templates"):
        st.markdown("""
        **Push Day A:**
        - Incline Dumbbell Press: 4x10
        - Overhead Shoulder Press: 4x12
        - Rope Triceps Extensions: 3x15
        - Side Laterals: 3x12
        - Cable Flys: 3x12
        - 15 mins incline treadmill walk

        **Pull Day A:**
        - Barbell Rows: 4x10
        - Lat Pulldowns: 4x12
        - Face Pulls: 3x15
        - Hammer Curls: 3x12
        - Cable Curls: 3x12

        **Leg Day A:**
        - Squats: 4x10
        - Romanian Deadlifts: 4x10
        - Leg Press: 3x15
        - Leg Curls: 3x12
        - Calf Raises: 4x15
        """)

# TAB 4: Supplements
with tab4:
    st.header("💊 Supplement Tracker")

    today = date.today().isoformat()
    supplements = st.session_state.user_data['supplements']
    schedule = st.session_state.user_data.setdefault('supplement_schedule', [])

    SUPP_OPTIONS = ["Multivitamin", "Protein Shake", "Creatine", "Fish Oil",
                    "Vitamin D", "BCAAs", "Pre-Workout", "Other"]
    TIME_OPTIONS = ["Morning", "Afternoon", "Evening", "Pre-Workout", "Post-Workout"]

    # Daily checklist driven by the schedule
    st.markdown("### ✅ Today's Checklist")
    if schedule:
        for idx, item in enumerate(schedule):
            logged = any(s['date'] == today and s['name'] == item['name']
                         and s['time'] == item['time'] and s.get('taken')
                         for s in supplements)
            checked = st.checkbox(f"{item['name']} ({item['time']})", value=logged, key=f"sched_{idx}")
            if checked and not logged:
                supplements.append({'date': today, 'name': item['name'], 'time': item['time'], 'taken': True})
                save_data()
                st.rerun()
            elif not checked and logged:
                supplements[:] = [s for s in supplements
                                  if not (s['date'] == today and s['name'] == item['name']
                                          and s['time'] == item['time'] and s.get('taken'))]
                save_data()
                st.rerun()

        done = sum(1 for item in schedule if any(
            s['date'] == today and s['name'] == item['name'] and s['time'] == item['time'] and s.get('taken')
            for s in supplements))
        st.progress(done / len(schedule), text=f"{done}/{len(schedule)} taken today")
    else:
        st.info("No supplement schedule yet — add your daily stack below and it becomes a one-tap checklist.")

    with st.expander("📅 Edit Schedule"):
        sc1, sc2 = st.columns(2)
        with sc1:
            new_supp = st.selectbox("Supplement", SUPP_OPTIONS, key="sched_new_name")
        with sc2:
            new_time = st.selectbox("Time of Day", TIME_OPTIONS, key="sched_new_time")
        if st.button("Add to Schedule"):
            entry = {'name': new_supp, 'time': new_time}
            if entry in schedule:
                st.warning("Already on the schedule.")
            else:
                schedule.append(entry)
                save_data()
                st.rerun()
        for idx, item in enumerate(schedule):
            rc1, rc2 = st.columns([4, 1])
            rc1.markdown(f"- {item['name']} ({item['time']})")
            if rc2.button("Remove", key=f"sched_rm_{idx}"):
                schedule.pop(idx)
                save_data()
                st.rerun()

    st.markdown("---")
    st.markdown("### Manual Log")

    col1, col2 = st.columns(2)

    with col1:
        supp_date = st.date_input("Date", value=date.today(), key="supp_date")
        supp_name = st.selectbox("Supplement", SUPP_OPTIONS)

    with col2:
        supp_time = st.selectbox("Time of Day", TIME_OPTIONS)
        taken = st.checkbox("Taken", value=True)

    if st.button("Log Supplement"):
        supplement = {
            'date': supp_date.isoformat(),
            'name': supp_name,
            'time': supp_time,
            'taken': taken
        }
        supplements.append(supplement)
        save_data()
        st.success(f"Logged: {supp_name}")
        st.rerun()

    # Editable recent history
    st.markdown("### This Week")
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    if not history_editor('supplements', window_start=week_ago, bool_fields=('taken',)):
        st.info("No supplements logged this week")

# TAB 5: AI Insights
with tab5:
    st.header("🧠 AI Auto-Adjust Insights")

    # Goals come from the saved profile
    protein_goal = st.session_state.user_data['profile'].get('daily_protein_g', 150)

    # Analyze last 7 days
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    recent_meals = [m for m in st.session_state.user_data['meals'] if m['date'] >= week_ago]
    recent_workouts = [w for w in st.session_state.user_data['workouts'] if w['date'] >= week_ago]
    recent_weights = [w for w in st.session_state.user_data.get('weights', []) if w['date'] >= week_ago]

    # Claude coaching summary
    st.markdown("### 🎓 Claude Coaching Summary")
    st.caption("A weekly review of your data by Claude — what went well, what to fix, and the one change to make next week.")

    if st.button("Generate Coaching Summary"):
        if not recent_meals and not recent_workouts:
            st.error("Log some meals or workouts first — there's no data from the last 7 days to review.")
        else:
            week_data = {
                'profile': st.session_state.user_data['profile'],
                'meals': recent_meals,
                'workouts': recent_workouts,
                'supplements': [s for s in st.session_state.user_data['supplements'] if s['date'] >= week_ago],
                'weigh_ins': recent_weights,
            }
            with st.spinner("Claude is reviewing your week..."):
                try:
                    st.session_state.coaching_summary = generate_coaching_summary(week_data)
                except Exception as e:
                    show_ai_error(e)

    if st.session_state.get('coaching_summary'):
        st.markdown(st.session_state.coaching_summary)

    st.markdown("---")

    # Calculate averages
    if recent_meals:
        days_logged = len({m['date'] for m in recent_meals})
        avg_protein = sum(m.get('protein', 0) for m in recent_meals) / len(recent_meals)
        avg_calories = sum(m.get('calories', 0) for m in recent_meals) / len(recent_meals)

        st.markdown("### Weekly Averages (Last 7 Days)")
        st.caption(f"Averaged over {days_logged} day{'s' if days_logged != 1 else ''} with logged meals")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Avg Protein/Meal", f"{avg_protein:.1f}g")
        with col2:
            st.metric("Avg Calories/Meal", f"{avg_calories:.0f}")
        with col3:
            st.metric("Meals/Day", f"{len(recent_meals)/days_logged:.1f}")

        col4, col5, col6 = st.columns(3)
        with col4:
            st.metric("Avg Carbs/Day", f"{sum(m.get('carbs', 0) for m in recent_meals)/days_logged:.0f}g")
        with col5:
            st.metric("Avg Fat/Day", f"{sum(m.get('fat', 0) for m in recent_meals)/days_logged:.0f}g")
        with col6:
            st.metric("Avg Fiber/Day", f"{sum(m.get('fiber', 0) for m in recent_meals)/days_logged:.0f}g")

        # Protein chart
        st.markdown("### Daily Protein Intake (Last 7 Days)")

        # Group by date
        protein_by_day = {}
        for meal in recent_meals:
            date_key = meal['date']
            if date_key not in protein_by_day:
                protein_by_day[date_key] = 0
            protein_by_day[date_key] += meal.get('protein', 0)

        if protein_by_day:
            df_protein = pd.DataFrame(list(protein_by_day.items()), columns=['Date', 'Protein'])
            df_protein = df_protein.sort_values('Date')

            fig = px.bar(df_protein, x='Date', y='Protein',
                        title='Daily Protein Intake',
                        labels={'Protein': 'Protein (g)'})
            fig.add_hline(y=protein_goal, line_dash="dash",
                         annotation_text=f"Goal: {protein_goal}g",
                         line_color="green")
            st.plotly_chart(fig, width="stretch")

        # AI Recommendations
        st.markdown("### 🎯 Auto-Adjust Recommendations")

        avg_daily_protein = sum(protein_by_day.values()) / days_logged

        if avg_daily_protein < protein_goal * 0.8:
            st.warning(f"⚠️ You're averaging {avg_daily_protein:.0f}g protein/day, below your {protein_goal}g goal")
            st.markdown("**Suggestions:**")
            st.markdown("- Add a protein shake (30g protein)")
            st.markdown("- Increase protein portions at main meals")
            st.markdown(f"- Add {protein_goal - avg_daily_protein:.0f}g protein to reach goal")
        elif avg_daily_protein >= protein_goal:
            st.success(f"✅ Great! You're hitting your {protein_goal}g protein goal!")
        else:
            st.info(f"📊 You're at {avg_daily_protein:.0f}g/day. Close to your {protein_goal}g goal!")

        # Workout consistency
        if recent_workouts:
            workouts_per_week = len(recent_workouts)
            st.markdown(f"### 🏋️ Workout Frequency: {workouts_per_week} workouts this week")

            if workouts_per_week < 3:
                st.warning("⚠️ Try to hit at least 3-4 workouts per week")
            elif workouts_per_week >= 5:
                st.success("✅ Excellent workout consistency!")
            else:
                st.info("📊 Good workout frequency")

        # Missed supplements
        recent_supps = [s for s in st.session_state.user_data['supplements'] if s['date'] >= week_ago]
        missed_supps = [s for s in recent_supps if not s.get('taken', True)]

        if missed_supps:
            st.markdown(f"### 💊 Missed Supplements: {len(missed_supps)}")
            for supp in missed_supps:
                st.markdown(f"- {supp['date']}: {supp['name']} ({supp['time']})")

    else:
        st.info("Log meals for 7 days to see AI insights and recommendations")

# Footer
st.markdown("---")
st.markdown("**Golden Nutrition AI** - Smart tracking for serious results 💪")
