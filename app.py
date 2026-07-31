import streamlit as st
import json
import copy
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
import plotly.express as px

# Configuration
DATA_FILE = Path("nutrition_data.json")

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
    'supplements': []
}

# Page config
st.set_page_config(page_title="Golden Nutrition AI", layout="wide", page_icon="🏋️")


def load_data():
    """Load user data, recovering gracefully from a corrupted file."""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
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


# Header
st.title("🏋️ Golden Nutrition AI")
st.subheader("Smart Fitness & Nutrition Tracking")

# Sidebar - User Profile
with st.sidebar:
    st.header("👤 Profile")

    profile = st.session_state.user_data['profile']

    name = st.text_input("Name", value=profile.get('name', ''))
    weight = st.number_input("Current Weight (lbs)", min_value=0, value=profile.get('weight', 0), step=1)
    goal_weight = st.number_input("Goal Weight (lbs)", min_value=0, value=profile.get('goal_weight', 0), step=1)
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

# Main tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard",
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
    total_protein = sum(m.get('protein', 0) for m in today_meals)
    total_calories = sum(m.get('calories', 0) for m in today_meals)

    # Metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        protein_pct = min(100, (total_protein / protein_goal * 100) if protein_goal > 0 else 0)
        st.metric("Protein", f"{total_protein}g / {protein_goal}g", f"{protein_pct:.0f}%")

    with col2:
        cal_pct = min(100, (total_calories / calorie_goal * 100) if calorie_goal > 0 else 0)
        st.metric("Calories", f"{total_calories} / {calorie_goal}", f"{cal_pct:.0f}%")

    with col3:
        st.metric("Meals Logged", len(today_meals))

    with col4:
        st.metric("Workouts", len(today_workouts))

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

# TAB 2: Meal Tracker
with tab2:
    st.header("🍽️ Log Meal")

    col1, col2 = st.columns(2)

    with col1:
        meal_date = st.date_input("Date", value=date.today())
        meal_time = st.time_input("Time", value=datetime.now().time())
        meal_name = st.text_input("Meal Name", placeholder="e.g., Chicken & Rice")

    with col2:
        protein = st.number_input("Protein (g)", min_value=0, value=30, step=5)
        calories = st.number_input("Calories", min_value=0, value=400, step=50)
        notes = st.text_area("Notes", placeholder="Optional notes...")

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
                'notes': notes
            }
            st.session_state.user_data['meals'].append(meal)
            save_data()
            st.success(f"Added: {meal_name}")
            st.rerun()

    # Show recent meals
    st.markdown("### Recent Meals (Last 7 Days)")

    week_ago = (date.today() - timedelta(days=7)).isoformat()
    recent_meals = [m for m in st.session_state.user_data['meals'] if m['date'] >= week_ago]

    if recent_meals:
        df = pd.DataFrame(recent_meals)
        df = df.sort_values('date', ascending=False)
        st.dataframe(df, width="stretch")

        # Delete meal option
        if st.checkbox("Delete mode"):
            meal_to_delete = st.selectbox("Select meal to delete",
                                         range(len(recent_meals)),
                                         format_func=lambda x: f"{recent_meals[x]['date']} {recent_meals[x]['time']} - {recent_meals[x]['name']}")
            if st.button("Delete Selected Meal"):
                st.session_state.user_data['meals'].remove(recent_meals[meal_to_delete])
                save_data()
                st.success("Meal deleted")
                st.rerun()
    else:
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
        workout_notes = st.text_area("Exercises / Notes", placeholder="List exercises, sets, reps...")

    if st.button("Add Workout"):
        workout = {
            'date': workout_date.isoformat(),
            'time': workout_time.strftime("%H:%M"),
            'name': workout_type,
            'duration': duration,
            'intensity': intensity,
            'notes': workout_notes
        }
        st.session_state.user_data['workouts'].append(workout)
        save_data()
        st.success(f"Logged: {workout_type}")
        st.rerun()

    # Show recent workouts
    st.markdown("### Recent Workouts (Last 7 Days)")

    week_ago = (date.today() - timedelta(days=7)).isoformat()
    recent_workouts = [w for w in st.session_state.user_data['workouts'] if w['date'] >= week_ago]

    if recent_workouts:
        df = pd.DataFrame(recent_workouts)
        df = df.sort_values('date', ascending=False)
        st.dataframe(df, width="stretch")

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

    col1, col2 = st.columns(2)

    with col1:
        supp_date = st.date_input("Date", value=date.today(), key="supp_date")
        supp_name = st.selectbox("Supplement", [
            "Multivitamin",
            "Protein Shake",
            "Creatine",
            "Fish Oil",
            "Vitamin D",
            "BCAAs",
            "Pre-Workout",
            "Other"
        ])

    with col2:
        supp_time = st.selectbox("Time of Day", ["Morning", "Afternoon", "Evening", "Pre-Workout", "Post-Workout"])
        taken = st.checkbox("Taken", value=True)

    if st.button("Log Supplement"):
        supplement = {
            'date': supp_date.isoformat(),
            'name': supp_name,
            'time': supp_time,
            'taken': taken
        }
        st.session_state.user_data['supplements'].append(supplement)
        save_data()
        st.success(f"Logged: {supp_name}")
        st.rerun()

    # Show this week's supplements
    st.markdown("### This Week")
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    recent_supps = [s for s in st.session_state.user_data['supplements'] if s['date'] >= week_ago]

    if recent_supps:
        df = pd.DataFrame(recent_supps)
        df = df.sort_values('date', ascending=False)
        st.dataframe(df, width="stretch")

        if st.checkbox("Delete mode", key="supp_delete_mode"):
            supp_to_delete = st.selectbox("Select supplement entry to delete",
                                         range(len(recent_supps)),
                                         format_func=lambda x: f"{recent_supps[x]['date']} - {recent_supps[x]['name']} ({recent_supps[x]['time']})")
            if st.button("Delete Selected Supplement"):
                st.session_state.user_data['supplements'].remove(recent_supps[supp_to_delete])
                save_data()
                st.success("Supplement entry deleted")
                st.rerun()
    else:
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
