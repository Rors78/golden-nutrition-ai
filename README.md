# 🏋️ Golden Nutrition AI

Smart fitness and nutrition tracking app with AI-powered insights. Built with Streamlit for an intuitive, data-driven approach to reaching your fitness goals.

## ✨ Features

### 📊 Dashboard
- Real-time daily summary of protein, calories, meals, and workouts
- Progress bars showing goal completion
- Recent activity feed

### 🍽️ Meal Tracker
- Log meals with protein and calorie counts
- Date/time tracking
- Optional notes for each meal
- View and manage last 7 days of meals
- Delete individual meals

### 🏋️ Workout Logger
- Pre-loaded Cutler Mode workout templates (Push/Pull/Legs)
- Track duration and intensity
- Custom workout support
- Detailed exercise notes
- 7-day workout history

### 💊 Supplement Tracker
- Log daily supplements (multivitamin, protein, creatine, etc.)
- Track time of day taken
- Mark missed supplements
- Weekly supplement history

### 🧠 AI Auto-Adjust Engine
- Weekly averages (protein per meal, calories, meals per day)
- Daily protein intake visualization
- Smart recommendations based on your goals:
  - Protein deficit warnings with suggestions
  - Workout frequency analysis
  - Missed supplement tracking
- Auto-calculates needed adjustments to hit goals

### 👤 User Profile
- Track current weight and goal weight
- Set daily protein and calorie targets
- Persistent profile data

## 🚀 Installation

### Requirements

```bash
pip install streamlit pandas plotly
```

### Dependencies
- **streamlit** - Web app framework
- **pandas** - Data analysis
- **plotly** - Interactive charts

## 📱 Usage

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

## 📋 Quick Start

1. **Set up your profile** (sidebar):
   - Enter your name, current weight, goal weight
   - Set daily protein and calorie goals
   - Click "Save Profile"

2. **Log your first meal**:
   - Go to "Meal Tracker" tab
   - Enter meal details (name, protein, calories)
   - Click "Add Meal"

3. **Track workouts**:
   - Go to "Workout Log" tab
   - Select workout type (or use Cutler Mode templates)
   - Add duration and intensity
   - Click "Add Workout"

4. **Get AI insights** (after 7 days of data):
   - Go to "AI Insights" tab
   - View weekly averages, charts, and recommendations
   - Get personalized suggestions to hit your goals

## 🎯 Cutler Mode Workouts

Pre-loaded workout templates based on proven bodybuilding programs:

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

## 💾 Data Storage

All data is saved to `nutrition_data.json` in the same directory as the app. This includes:
- User profile
- Meal history
- Workout logs
- Supplement tracking

Data persists between sessions automatically.

## 🧮 AI Auto-Adjust Logic

The AI engine analyzes your last 7 days and provides:

**Protein Tracking:**
- Compares daily average to your goal
- Warns if below 80% of target
- Suggests specific amounts to add (protein shakes, meal adjustments)
- Shows daily protein chart with goal line

**Workout Consistency:**
- Counts workouts per week
- Recommends 3-4 minimum
- Celebrates 5+ workouts

**Supplement Compliance:**
- Identifies missed supplements
- Lists specific dates and times
- Helps maintain consistency

## 📊 Example Insights

After logging data for a week, you'll see:

```
⚠️ You're averaging 120g protein/day, below your 150g goal

Suggestions:
- Add a protein shake (30g protein)
- Increase protein portions at main meals
- Add 30g protein to reach goal
```

```
✅ Excellent workout consistency! (5 workouts this week)
```

## 🔧 Customization

Edit the app to customize:
- Default protein/calorie goals
- Supplement list
- Workout templates
- Chart styles

## 📈 Perfect For

- Bodybuilders tracking macros
- Fitness enthusiasts monitoring progress
- Anyone serious about nutrition goals
- Meal prep planning
- Accountability and consistency

## 🌟 Why Golden Nutrition AI?

- **No subscription fees** - Run locally, own your data
- **Simple interface** - Easy to log meals and workouts
- **Smart insights** - AI tells you exactly what to adjust
- **Cutler Mode** - Proven workout templates included
- **Visual progress** - Charts and graphs motivate you
- **Persistent data** - Never lose your tracking history

## 📝 Tips for Best Results

1. **Log consistently** - Daily entries provide best insights
2. **Be accurate** - Estimate protein and calories as close as possible
3. **Check AI tab weekly** - Review recommendations every Sunday
4. **Adjust goals** - Update profile as you progress
5. **Use notes** - Add meal prep or workout details for reference

## 🎉 Spring Ready!

Perfect timing to start tracking for spring goals. Log meals and workouts daily, let the AI guide your adjustments, and watch your progress compound week after week.

## 📄 License

Personal use only.

---

**Golden Nutrition AI** - Because serious results require serious tracking 💪
