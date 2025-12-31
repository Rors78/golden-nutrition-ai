import streamlit as st
import json
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px

# Configuration
DATA_FILE = Path("nutrition_data.json")

# Page config
st.set_page_config(page_title="Golden Nutrition AI", layout="wide", page_icon="🏋️")

# Initialize session state
if 'user_data' not in st.session_state:
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r') as f:
            st.session_state.user_data = json.load(f)
    else:
        st.session_state.user_data = {
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

def save_data():
    """Save user data to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(st.session_state.user_data, f, indent=2)

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
        protein_pct = min(100, (total_protein / daily_protein * 100) if daily_protein > 0 else 0)
        st.metric("Protein", f"{total_protein}g / {daily_protein}g", f"{protein_pct:.0f}%")

    with col2:
        cal_pct = min(100, (total_calories / daily_calories * 100) if daily_calories > 0 else 0)
        st.metric("Calories", f"{total_calories} / {daily_calories}", f"{cal_pct:.0f}%")

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
        for meal in today_meals[-3:]:
            st.markdown(f"**{meal['time']}** - {meal['name']}: {meal.get('protein', 0)}g protein, {meal.get('calories', 0)} cal")
    else:
        st.info("No meals logged today")

    st.markdown("### Recent Workouts")
    if today_workouts:
        for workout in today_workouts[-2:]:
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
        meal = {
            'date': meal_date.isoformat(),
            'time': meal_time.strftime("%H:%M"),
            'name': meal_name,
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
        st.dataframe(df, use_container_width=True)

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
        st.dataframe(df, use_container_width=True)
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
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No supplements logged this week")

# TAB 5: AI Insights
with tab5:
    st.header("🧠 AI Auto-Adjust Insights")

    # Analyze last 7 days
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    recent_meals = [m for m in st.session_state.user_data['meals'] if m['date'] >= week_ago]
    recent_workouts = [w for w in st.session_state.user_data['workouts'] if w['date'] >= week_ago]

    # Calculate averages
    if recent_meals:
        avg_protein = sum(m.get('protein', 0) for m in recent_meals) / len(recent_meals)
        avg_calories = sum(m.get('calories', 0) for m in recent_meals) / len(recent_meals)

        st.markdown("### Weekly Averages (Last 7 Days)")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Avg Protein/Meal", f"{avg_protein:.1f}g")
        with col2:
            st.metric("Avg Calories/Meal", f"{avg_calories:.0f}")
        with col3:
            st.metric("Meals/Day", f"{len(recent_meals)/7:.1f}")

        # Protein chart
        st.markdown("### Daily Protein Intake (Last 7 Days)")

        # Group by date
        daily_protein = {}
        for meal in recent_meals:
            date_key = meal['date']
            if date_key not in daily_protein:
                daily_protein[date_key] = 0
            daily_protein[date_key] += meal.get('protein', 0)

        if daily_protein:
            df_protein = pd.DataFrame(list(daily_protein.items()), columns=['Date', 'Protein'])
            df_protein = df_protein.sort_values('Date')

            fig = px.bar(df_protein, x='Date', y='Protein',
                        title='Daily Protein Intake',
                        labels={'Protein': 'Protein (g)'})
            fig.add_hline(y=daily_protein, line_dash="dash",
                         annotation_text=f"Goal: {daily_protein}g",
                         line_color="green")
            st.plotly_chart(fig, use_container_width=True)

        # AI Recommendations
        st.markdown("### 🎯 Auto-Adjust Recommendations")

        total_daily_protein = sum(daily_protein.values()) / len(daily_protein) if daily_protein else 0

        if total_daily_protein < daily_protein * 0.8:
            st.warning(f"⚠️ You're averaging {total_daily_protein:.0f}g protein/day, below your {daily_protein}g goal")
            st.markdown("**Suggestions:**")
            st.markdown("- Add a protein shake (30g protein)")
            st.markdown("- Increase protein portions at main meals")
            st.markdown(f"- Add {daily_protein - total_daily_protein:.0f}g protein to reach goal")
        elif total_daily_protein >= daily_protein:
            st.success(f"✅ Great! You're hitting your {daily_protein}g protein goal!")
        else:
            st.info(f"📊 You're at {total_daily_protein:.0f}g/day. Close to your {daily_protein}g goal!")

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
