# 🏋️ Golden Nutrition AI

Smart fitness and nutrition tracking app with AI-powered insights. Built with Streamlit for an intuitive, data-driven approach to reaching your fitness goals.

## ✨ Features

### 📊 Dashboard
- Real-time daily summary of protein, calories, meals, and workouts
- Progress bars showing goal completion
- Recent activity feed

### ⚖️ Weight Tracker
- Log daily weigh-ins (one entry per day)
- Weight-over-time chart with your goal line
- 7-day change and lbs/week trend
- Projected date you'll hit your goal weight at the current rate
- Latest weigh-in automatically updates your profile weight

### 🤖 Claude AI (real AI, powered by the Claude API)
- **AI Quick Log** — describe what you ate in plain language ("chicken burrito and a protein shake") and Claude estimates protein and calories for each item; review and add to your log in one click
- **Coaching Summary** — Claude reviews your last 7 days of meals, workouts, supplements, and weigh-ins and gives you a coaching write-up: what went well, what to fix, and the one highest-impact change for next week
- Requires Claude API credentials (see Installation); everything else in the app works without them

### 🍽️ Meal Tracker
- Full macros: protein, calories, carbs, fat, and fiber per meal
- ⭐ Quick Add: re-log any recent meal with one click
- Date/time tracking and optional notes
- Edit the last 7 days inline — change cells, add rows, or delete rows right in the table

### 🏋️ Workout Logger
- Pre-loaded Cutler Mode workout templates (Push/Pull/Legs)
- Structured exercise logging: sets, reps, and weight per exercise
- 📈 Progression tracking per exercise: all-time PR, best-day volume, top-weight and volume charts over time
- Track duration, intensity, and notes
- 7-day workout history

### 💊 Supplement Tracker
- ✅ Daily checklist: define your daily stack once, then tick off each supplement as you take it
- Manual logging with time of day and missed-supplement tracking
- Edit this week's history inline

### 💾 Data
- One-click CSV export of meals, workouts, supplements, and weigh-ins (sidebar)
- All data in a local `nutrition_data.json` you own

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

**Windows:**
```powershell
pip install -r requirements.txt
```

**Linux/macOS:**
```bash
pip3 install -r requirements.txt
```

### Dependencies
- **streamlit** - Web app framework
- **pandas** - Data analysis
- **plotly** - Interactive charts
- **anthropic** - Claude API SDK (for the AI features)

### Claude API setup (for AI features)

The AI Quick Log and Coaching Summary use the Claude API (model: Claude Opus 5). Set your API key before launching:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # from https://platform.claude.com
```

(or run `ant auth login` if you use the Anthropic CLI). Without credentials, the rest of the app works normally and the AI buttons show a setup hint.

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

## 🧪 Development

Run the test suite (end-to-end app tests via Streamlit's AppTest — no API key needed):

```bash
pip install pytest
python -m pytest tests/ -v
```

Tests also run automatically on every push and pull request via GitHub Actions.

## 📄 License

MIT — see the [LICENSE](LICENSE) file.

---

**Golden Nutrition AI** - Because serious results require serious tracking 💪
