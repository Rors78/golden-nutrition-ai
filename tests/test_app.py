"""End-to-end tests for the Golden Nutrition AI Streamlit app.

Each test runs the full app script with streamlit's AppTest framework in an
isolated temp directory, so the real nutrition_data.json is never touched.
The Claude AI features are button-gated and never execute during a render,
so no API credentials are needed to run these tests.
"""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def seed_week_of_data():
    data = {
        "profile": {"name": "Test", "weight": 200, "goal_weight": 185,
                    "daily_protein_g": 150, "daily_calories": 2200},
        "meals": [], "workouts": [], "supplements": [],
        "supplement_schedule": [{"name": "Creatine", "time": "Morning"}],
        "weights": [],
    }
    for i in range(6):
        d = (date.today() - timedelta(days=i)).isoformat()
        data["meals"].append({"date": d, "time": "12:00", "name": f"Meal {i}",
                              "protein": 45, "calories": 650, "carbs": 60,
                              "fat": 20, "fiber": 8, "notes": ""})
        data["meals"].append({"date": d, "time": "19:00", "name": f"Dinner {i}",
                              "protein": 50, "calories": 800, "carbs": 70,
                              "fat": 25, "fiber": 10, "notes": ""})
        data["workouts"].append({
            "date": d, "time": "07:00", "name": "Push Day A (Cutler Mode)",
            "duration": 60, "intensity": "Hard", "notes": "",
            "exercises": [
                {"exercise": "Incline Dumbbell Press", "sets": 4, "reps": 10, "weight": 70 + i},
                {"exercise": "Overhead Shoulder Press", "sets": 4, "reps": 12, "weight": 50},
            ],
        })
        data["weights"].append({"date": d, "weight": 200 + i * 0.2})
    data["weights"].sort(key=lambda w: w["date"])
    data["supplements"].append({"date": date.today().isoformat(), "name": "Creatine",
                                "time": "Morning", "taken": True})
    return data


def run_app():
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def all_markdown(at):
    return " | ".join(w.value for w in at.markdown)


def test_renders_with_empty_data():
    at = run_app()
    metrics = {m.label for m in at.metric}
    assert {"Protein", "Calories", "Meals Logged", "Workouts"} <= metrics


def test_renders_with_week_of_data():
    with open("nutrition_data.json", "w") as f:
        json.dump(seed_week_of_data(), f)

    at = run_app()
    metrics = {m.label: m.value for m in at.metric}
    texts = all_markdown(at)

    # Dashboard macros
    assert metrics["Protein"] == "95g / 150g"
    assert metrics["Carbs"] == "130g"
    assert metrics["Fiber"] == "18g"

    # Weight tracking
    assert metrics["Current Weight"] == "200.0 lbs"
    assert metrics["To Goal"] == "15.0 lbs"
    assert "lbs/week" in metrics["Trend"]
    infos = " | ".join(w.body for w in at.info)
    assert "reach 185 lbs around" in infos

    # Workout progression
    assert metrics["All-Time PR"] == "75 lbs"  # 70 + 5 (oldest day is i=5)
    assert "Progression" in texts

    # AI sections present (never executed on render)
    assert "AI Quick Log" in texts
    assert "Claude Coaching Summary" in texts

    # Quick add and checklist
    assert "Quick Add" in texts
    assert "Today's Checklist" in texts


def test_corrupt_data_file_recovery():
    with open("nutrition_data.json", "w") as f:
        f.write("{this is not json")

    at = run_app()
    warnings = " | ".join(w.body for w in at.warning)
    assert "backed it up" in warnings
    assert Path("nutrition_data.json.corrupt").exists()


def test_old_data_without_new_fields_still_works():
    """Data written by the v1 app (no macros/weights/schedule) must still load."""
    old = {
        "profile": {"name": "", "weight": 0, "goal_weight": 0,
                    "daily_protein_g": 150, "daily_calories": 2000},
        "meals": [{"date": date.today().isoformat(), "time": "12:00",
                   "name": "Legacy meal", "protein": 40, "calories": 500, "notes": ""}],
        "workouts": [{"date": date.today().isoformat(), "time": "07:00",
                      "name": "Cardio", "duration": 30, "intensity": "Light", "notes": ""}],
        "supplements": [],
    }
    with open("nutrition_data.json", "w") as f:
        json.dump(old, f)

    at = run_app()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Protein"] == "40g / 150g"
    assert metrics["Carbs"] == "0g"  # missing macro fields default to 0
