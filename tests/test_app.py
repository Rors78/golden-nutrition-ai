"""End-to-end API tests for the Golden Nutrition AI Flask app.

Each test runs against a fresh app in an isolated temp cwd, so the real
nutrition_data.json is never touched. AI endpoints are monkeypatched — no
Claude backend or credentials are needed.
"""
import json
from datetime import date, timedelta

import pytest

from app import create_app
from app import ai


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app()
    app.testing = True
    return app.test_client()


def seed(client_dir_data):
    with open("nutrition_data.json", "w") as f:
        json.dump(client_dir_data, f)


def week_of_data():
    data = {
        "profile": {"name": "Test", "weight": 200, "goal_weight": 185,
                    "height_in": 70,
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
        data["workouts"].append({
            "date": d, "time": "07:00", "name": "Push Day A (Cutler Mode)",
            "duration": 60, "intensity": "Hard", "notes": "",
            "exercises": [{"exercise": "Incline Dumbbell Press", "sets": 4,
                           "reps": 10, "weight": 70 + i}],
        })
        data["weights"].append({"date": d, "weight": 200 + i * 0.2})
    data["weights"].sort(key=lambda w: w["date"])
    return data


def test_index_serves_spa(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Golden" in res.data
    assert b"app.js" in res.data


def test_state_with_empty_data(client):
    state = client.get("/api/state").get_json()
    assert state["profile"]["daily_protein_g"] == 150
    assert state["stats"]["today"]["totals"]["protein"] == 0
    assert state["stats"]["weight"] == {"has_data": False}


def test_full_week_stats(client):
    seed(week_of_data())
    state = client.get("/api/state").get_json()

    today = state["stats"]["today"]["totals"]
    assert today["protein"] == 45 and today["carbs"] == 60

    w = state["stats"]["weight"]
    assert w["current"] == 200.0
    assert w["rate_per_week"] == -1.4  # losing 0.2/day
    assert w["eta_days"] == 75
    assert w["total_change"] == -1.0
    assert w["series_avg"][-1]["avg"] == 200.5  # mean of the 6 seeded entries
    assert w["pace"]["level"] == "good"         # 0.7% BW/week: sustainable
    assert w["bmi"] == {"value": 28.7, "category": "overweight range"}
    assert w["eta_date_iso"] is not None

    prog = state["stats"]["progression"]["Incline Dumbbell Press"]
    assert max(p["top"] for p in prog) == 75

    ins = state["stats"]["insights"]
    assert ins["avg_daily_protein"] == 45
    assert ins["verdict"]["level"] == "warn"  # 45g/day vs 150g goal

    trn = state["stats"]["training"]
    assert trn["sessions_7d"] == 6 and trn["minutes_7d"] == 360
    assert trn["volume_7d"] == 17400  # sum of 4x10x(70..75)
    assert trn["streak_weeks"] == 1   # this week qualifies, previous doesn't

    assert state["stats"]["checklist"] == [
        {"name": "Creatine", "time": "Morning", "taken": False, "low": False}]


def test_meal_lifecycle(client):
    r = client.post("/api/meals", json={"name": "Chicken & rice", "protein": 50,
                                        "calories": 600, "carbs": 55, "fat": 12, "fiber": 4})
    assert r.status_code == 200
    assert client.post("/api/meals", json={"name": "  "}).status_code == 400

    state = client.get("/api/state").get_json()
    assert state["meals"][0]["name"] == "Chicken & rice"

    r = client.put("/api/entry/meals/0", json={"protein": 55})
    assert r.status_code == 200
    assert client.get("/api/state").get_json()["meals"][0]["protein"] == 55

    assert client.delete("/api/entry/meals/0").status_code == 200
    assert client.get("/api/state").get_json()["meals"] == []


def _log_workout(client, day, exercises):
    client.post("/api/workouts", json={"date": day, "time": "07:00",
                                       "name": "Custom", "duration": 60,
                                       "intensity": "Hard", "exercises": exercises})


def test_dashboard_radar_and_action_know_the_new_engines(client):
    data = week_of_data()
    today = date.today()
    # 5 weeks of climbing volume → deload warning; bench held reps → increase
    data["workouts"] = []
    for wk in range(5):
        for d_off in (1, 3, 5):
            day = (today - timedelta(days=7 * wk + d_off)).isoformat()
            data["workouts"].append({
                "date": day, "time": "07:00", "name": "Legs", "duration": 60,
                "intensity": "Hard",
                "exercises": [{"exercise": "Squats", "sets": 5, "reps": 10,
                               "weight": 100 + (4 - wk) * 25}]})
    for d_off, reps in ((5, 8), (1, 9)):
        data["workouts"].append({
            "date": (today - timedelta(days=d_off)).isoformat(), "time": "08:00",
            "name": "Push", "duration": 60, "intensity": "Hard",
            "exercises": [{"exercise": "Bench Press", "sets": 4, "reps": reps,
                           "weight": 185}]})
    # 21 days of intake + falling weight → TDEE delta vs the 2200 goal
    data["meals"], data["weights"] = [], []
    for i in range(21):
        day = (today - timedelta(days=i)).isoformat()
        data["meals"].append({"date": day, "time": "12:00", "name": "Day food",
                              "protein": 150, "calories": 2000, "carbs": 150,
                              "fat": 60, "fiber": 20, "notes": ""})
        data["weights"].append({"date": day, "weight": 197 + 3 * i / 20})
    # today's plan includes bench → the train action should call the number
    day_name = today.strftime("%A")
    data["plan"] = {"coach": "cutler", "plan": {"week": [
        {"day": day_name, "title": "Push Day", "focus": "Chest",
         "details": ["Bench Press: 4×8 @ 185 lbs"]}]}}
    seed(data)

    dash = client.get("/api/state").get_json()["stats"]["dashboard"]
    radar_text = " ".join(r["text"] for r in dash["radar"]).lower()
    # the strain radar fires (spike outranks deload when both apply)
    assert "acute load" in radar_text or "deload" in radar_text
    assert "tdee" in radar_text
    train = next(a for a in dash["actions"] if a["id"] == "train")
    assert "Bench Press earns 190" in train["text"]


def test_sentinel_alerts():
    from app.stats import sentinel_alerts

    # trouble on every front
    data = week_of_data()
    data["workouts"] = []
    for wk in range(5):
        for d_off in (1, 3, 5):
            day = (date.today() - timedelta(days=7 * wk + d_off)).isoformat()
            data["workouts"].append({
                "date": day, "time": "07:00", "name": "Legs", "duration": 60,
                "intensity": "Hard",
                "exercises": [{"exercise": "Squats", "sets": 5, "reps": 10,
                               "weight": 100 + (4 - wk) * 25}]})
    data["vitals"] = [{"date": date.today().isoformat(), "sleep_h": 2.0}]
    alerts = sentinel_alerts(data, backup_age_days=5, last_log_age_days=4)
    joined = " ".join(alerts).lower()
    assert "backup" in joined            # stale backup
    assert "nothing logged" in joined    # logging went quiet
    assert "deload" in joined            # strain warning
    assert "readiness" in joined         # cratered recovery

    # a healthy day is silent
    quiet = sentinel_alerts(week_of_data(), backup_age_days=0.3,
                            last_log_age_days=0.1)
    assert quiet == []

    # no backups at all is itself an alert
    assert any("backup" in a.lower()
               for a in sentinel_alerts(week_of_data(), backup_age_days=None,
                                        last_log_age_days=0.1))


def test_recipe_box(client):
    items = [{"name": "Chicken", "protein": 60, "calories": 330, "carbs": 0,
              "fat": 8, "fiber": 0},
             {"name": "Rice", "protein": 8, "calories": 400, "carbs": 88,
              "fat": 2, "fiber": 2}]
    r = client.post("/api/recipes", json={"name": "Chicken & rice",
                                          "servings": 2, "items": items})
    assert r.status_code == 200
    st = client.get("/api/state").get_json()
    assert len(st["recipes"]) == 1 and st["recipes"][0]["servings"] == 2

    # 1.5 servings: per serving 34g P / 365 cal → 51g / 547.5
    client.post("/api/recipes/0/log", json={"servings": 1.5})
    meal = client.get("/api/state").get_json()["meals"][-1]
    assert meal["name"] == "Chicken & rice ×1.5"
    assert meal["protein"] == 51
    assert meal["calories"] == 547.5

    # validations
    assert client.post("/api/recipes", json={"servings": 2, "items": items}).status_code == 400
    assert client.post("/api/recipes", json={"name": "Empty", "items": []}).status_code == 400
    assert client.post("/api/recipes/9/log", json={}).status_code == 404
    assert client.delete("/api/recipes/9").status_code == 404
    assert client.delete("/api/recipes/0").status_code == 200
    assert client.get("/api/state").get_json()["recipes"] == []


def test_next_targets_double_progression(client):
    data = week_of_data()
    data["workouts"] = []
    today = date.today()

    def log(days_ago, exercise, weight, reps):
        data["workouts"].append({
            "date": (today - timedelta(days=days_ago)).isoformat(),
            "time": "07:00", "name": "Push", "duration": 60, "intensity": "Hard",
            "exercises": [{"exercise": exercise, "sets": 4, "reps": reps,
                           "weight": weight}]})

    log(5, "Bench Press", 185, 8)      # held 8 reps at 185 twice → +5
    log(1, "Bench Press", 185, 9)
    log(5, "Barbell Rows", 155, 10)    # reps slipped 10 → 7 → hold
    log(1, "Barbell Rows", 155, 7)
    log(1, "Cable Flys", 40, 12)       # single session → build
    log(30, "Deadlift", 315, 5)        # stale (>21d) → excluded
    seed(data)

    nt = {t["exercise"]: t for t in
          client.get("/api/state").get_json()["stats"]["next_targets"]}
    assert nt["Bench Press"]["action"] == "increase"
    assert nt["Bench Press"]["next_weight"] == 190
    assert nt["Barbell Rows"]["action"] == "hold"
    assert nt["Barbell Rows"]["next_weight"] == 155
    assert nt["Cable Flys"]["action"] == "build"
    assert "Deadlift" not in nt


def test_energy_balance_adaptive_tdee(client):
    # ~1 week of data → honest silence
    seed(week_of_data())
    e = client.get("/api/state").get_json()["stats"]["energy"]
    assert e["has_data"] is False

    # 21 days: 2000 cal/day logged, weight sliding 200 → 197 (~-1.05 lb/wk)
    data = week_of_data()
    data["meals"], data["weights"] = [], []
    for i in range(21):
        day = (date.today() - timedelta(days=i)).isoformat()
        data["meals"].append({"date": day, "time": "12:00", "name": "Day food",
                              "protein": 150, "calories": 2000, "carbs": 150,
                              "fat": 60, "fiber": 20, "notes": ""})
        data["weights"].append({"date": day, "weight": 197 + 3 * i / 20})
    seed(data)   # profile: goal_weight 185 (cutting), daily_calories 2200
    e = client.get("/api/state").get_json()["stats"]["energy"]
    assert e["has_data"] is True
    assert e["rate_wk"] == pytest.approx(-1.05, abs=0.01)
    # TDEE = 2000 + 1.05*500 = 2525; cutting at -1 lb/wk → 2025
    assert e["tdee"] == 2525
    assert e["recommended_calories"] == 2025
    assert e["delta"] == 2025 - 2200
    assert e["confidence"] == "high"

    # one-tap adoption
    r = client.post("/api/profile/calorie-goal", json={"calories": 2025})
    assert r.status_code == 200
    assert client.get("/api/state").get_json()["profile"]["daily_calories"] == 2025
    assert client.post("/api/profile/calorie-goal",
                       json={"calories": 200}).status_code == 400


def test_training_strain(client):
    # ~1 week of history only → no chronic baseline, radar stays silent
    seed(week_of_data())
    s = client.get("/api/state").get_json()["stats"]["strain"]
    assert s["has_data"] is False

    # five weeks of steadily climbing volume: 3 sessions/week, weight rising
    # 100 → 200 by 25/wk (weekly volume 15,000 → 30,000)
    data = week_of_data()
    data["workouts"] = []
    for wk in range(5):                       # wk 0 = the current week
        for d_off in (1, 3, 5):
            day = (date.today() - timedelta(days=7 * wk + d_off)).isoformat()
            data["workouts"].append({
                "date": day, "time": "07:00", "name": "Legs", "duration": 60,
                "intensity": "Hard",
                "exercises": [{"exercise": "Squats", "sets": 5, "reps": 10,
                               "weight": 100 + (4 - wk) * 25}],
            })
    seed(data)
    s = client.get("/api/state").get_json()["stats"]["strain"]
    assert s["has_data"] is True
    # acute 30,000 vs chronic (30,000+67,500)/4 = 24,375 → 1.23, sweet zone
    assert s["acute_7d"] == 30000
    assert s["acwr"] == pytest.approx(1.23, abs=0.01)
    assert s["zone"] == "sweet"
    assert s["monotony"] is not None
    assert s["rising_weeks"] == 4
    assert "deload" in s["suggestion"].lower()


PNG_1PX = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
           "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def test_ai_contexts_include_body_data(client, monkeypatch):
    data = week_of_data()
    data["profile"]["sex"] = "male"          # height_in 70 already set
    data["measurements"] = [{"date": date.today().isoformat(),
                             "waist_in": 34, "neck_in": 15}]
    seed(data)
    captured = {}

    monkeypatch.setattr(ai, "daily_briefing",
                        lambda p, persona, context: captured.update(brief=context) or "ok")
    assert client.post("/api/briefing").status_code == 200
    assert '"body_comp"' in captured["brief"]
    assert '"tape_latest"' in captured["brief"]
    assert json.loads(captured["brief"])["body_comp"]["bf_pct"] == pytest.approx(17.5, abs=0.1)

    monkeypatch.setattr(ai, "coaching_summary",
                        lambda wd, persona: captured.update(week=wd) or "ok")
    assert client.post("/api/coach").status_code == 200
    wd = captured["week"]
    assert wd["measurements"] and wd["body_comp"]["bf_pct"] is not None
    assert "recent_prs" in wd and "readiness" in wd

    monkeypatch.setattr(ai, "coach_chat",
                        lambda persona, hist, msg, snap: captured.update(chat=snap) or "ok")
    assert client.post("/api/coach/chat", json={"message": "hey"}).status_code == 200
    assert '"body_comp"' in captured["chat"]


def test_progress_photos(client):
    r = client.post("/api/photos", json={"image": PNG_1PX})
    assert r.status_code == 200
    name = r.get_json()["file"]
    assert name.endswith(".png")

    st = client.get("/api/state").get_json()
    assert len(st["photos"]) == 1 and st["photos"][0]["file"] == name
    assert client.get(f"/api/photos/{name}").status_code == 200

    # second same-day photo gets a distinct filename
    name2 = client.post("/api/photos", json={"image": PNG_1PX}).get_json()["file"]
    assert name2 != name

    # unknown names and non-listed files are refused
    assert client.get("/api/photos/nope.jpg").status_code == 404
    assert client.get("/api/photos/nutrition_data.json").status_code == 404
    # junk payloads
    assert client.post("/api/photos", json={"image": "hello"}).status_code == 400

    # delete removes both the entry and the file
    assert client.delete("/api/photos/0").status_code == 200
    st = client.get("/api/state").get_json()
    assert len(st["photos"]) == 1
    assert client.get(f"/api/photos/{name}").status_code == 404
    assert client.delete("/api/photos/5").status_code == 404


def test_measurements_merge_and_body_comp(client):
    data = week_of_data()
    data["profile"]["sex"] = "male"          # height_in 70 already set
    seed(data)
    today = date.today().isoformat()
    yday = (date.today() - timedelta(days=1)).isoformat()

    r = client.post("/api/measurements", json={"date": yday, "waist_in": 34.5,
                                               "neck_in": 15})
    assert r.status_code == 200
    client.post("/api/measurements", json={"date": yday, "chest_in": 42})
    st = client.get("/api/state").get_json()
    assert len(st["measurements"]) == 1      # same date merged, not duplicated
    assert st["measurements"][0]["waist_in"] == 34.5
    assert st["measurements"][0]["chest_in"] == 42

    client.post("/api/measurements", json={"date": today, "waist_in": 34,
                                           "neck_in": 15})
    bc = client.get("/api/state").get_json()["stats"]["body_comp"]
    # Navy male, waist 34 / neck 15 / height 70 → ~17.5%
    assert bc["current"] == pytest.approx(17.5, abs=0.1)
    assert len(bc["series"]) == 2
    assert bc["change"] < 0                  # waist came down

    assert client.post("/api/measurements", json={"date": today}).status_code == 400
    assert client.get("/api/export/measurements.csv").status_code == 200


def test_body_comp_female_and_hints():
    from app.stats import body_comp
    base = {"profile": {"height_in": 65, "sex": "female"},
            "measurements": [{"date": "2026-08-01", "waist_in": 30,
                              "neck_in": 13, "hips_in": 38}]}
    bf = body_comp(base)["series"][0]["bf"]
    assert 28.4 <= bf <= 28.7                # Navy female formula

    no_height = {"profile": {"height_in": 0, "sex": "male"},
                 "measurements": [{"date": "2026-08-01", "waist_in": 34, "neck_in": 15}]}
    assert "height" in body_comp(no_height)["hint"]

    no_sex = {"profile": {"height_in": 70, "sex": ""},
              "measurements": [{"date": "2026-08-01", "waist_in": 34, "neck_in": 15}]}
    assert "sex" in body_comp(no_sex)["hint"].lower()


def test_system_pulse(client):
    from pathlib import Path
    seed(week_of_data())
    s = client.get("/api/system").get_json()
    assert s["data_file"]["counts"]["meals"] == 6
    assert s["data_file"]["bytes"] > 0
    assert s["backups"]["count"] == 0
    assert any("backup" in w.lower() for w in s["warnings"])

    # stage two snapshots — count and freshness reported, warning gone
    Path("backups").mkdir()
    Path("backups/nutrition_data-2026-01-01.json").write_text("{}")
    Path(f"backups/nutrition_data-{date.today().isoformat()}.json").write_text("{}")
    s = client.get("/api/system").get_json()
    assert s["backups"]["count"] == 2
    assert s["backups"]["age_days"] <= 0.1
    assert not any("backup job" in w for w in s["warnings"])


def test_barcode_normalize():
    from app.food_db import normalize
    per_serving = {"status": 1, "product": {
        "product_name": "Nutella", "brands": "Ferrero", "serving_size": "15 g",
        "nutriments": {"proteins_serving": 0.9, "energy-kcal_serving": 80.7,
                       "carbohydrates_serving": 8.6, "fat_serving": 4.7}}}
    hit = normalize(per_serving)
    assert hit["basis"] == "serving" and hit["brand"] == "Ferrero"
    assert hit["macros"]["calories"] == 80.7
    assert hit["macros"]["fiber"] == 0            # missing macro defaults to 0

    per_100g = {"status": 1, "product": {
        "product_name": "Oats",
        "nutriments": {"proteins_100g": 13.5, "energy-kcal_100g": 379}}}
    hit = normalize(per_100g)
    assert hit["basis"] == "100g" and hit["macros"]["protein"] == 13.5

    assert normalize({"status": 0}) is None
    assert normalize({"status": 1, "product": {"product_name": "Mystery",
                                               "nutriments": {}}}) is None


def test_barcode_endpoint(client, monkeypatch):
    from app import food_db
    hit = {"name": "Whey Gold", "brand": "ON", "serving_size": "31 g",
           "basis": "serving",
           "macros": {"protein": 24, "calories": 120, "carbs": 3,
                      "fat": 1.5, "fiber": 0}}
    monkeypatch.setattr(food_db, "lookup_barcode", lambda code: hit)
    r = client.get("/api/food/barcode/0748927024081")
    assert r.status_code == 200 and r.get_json()["macros"]["protein"] == 24

    monkeypatch.setattr(food_db, "lookup_barcode", lambda code: None)
    assert client.get("/api/food/barcode/00000000").status_code == 404

    def boom(code):
        raise OSError("timed out")
    monkeypatch.setattr(food_db, "lookup_barcode", boom)
    assert client.get("/api/food/barcode/12345678").status_code == 502


def test_barcode_junk_input_rejected(client):
    # validation raises before any network I/O
    assert client.get("/api/food/barcode/nonsense").status_code == 400


def test_workout_split_sets_per_exercise(client):
    """Live sessions save one row per (weight, reps) group of the same
    exercise — both rows must persist and progression must merge them."""
    today = date.today().isoformat()
    _log_workout(client, today, [
        {"exercise": "Squats", "sets": 3, "reps": 10, "weight": 185},
        {"exercise": "Squats", "sets": 1, "reps": 8, "weight": 205},
    ])
    state = client.get("/api/state").get_json()
    rows = state["workouts"][-1]["exercises"]
    assert [r["weight"] for r in rows] == [185, 205]
    day = next(p for p in state["stats"]["progression"]["Squats"]
               if p["date"] == today)
    assert day["top"] == 205
    assert day["volume"] == 3 * 10 * 185 + 1 * 8 * 205


def test_muscle_balance_and_weekly_volume(client):
    today = date.today().isoformat()
    _log_workout(client, today, [
        {"exercise": "Barbell Squat", "sets": 4, "reps": 10, "weight": 100},   # 4000 Legs
        {"exercise": "Bench Press", "sets": 4, "reps": 10, "weight": 100},     # 4000 Chest
        {"exercise": "Leg Extension", "sets": 2, "reps": 10, "weight": 100},   # 2000 Legs (not Arms)
    ])
    st = client.get("/api/state").get_json()["stats"]
    groups = {g["group"]: g for g in st["muscle_balance"]["groups"]}
    assert groups["Legs"]["volume"] == 6000 and groups["Legs"]["pct"] == 60
    assert groups["Chest"]["volume"] == 4000 and groups["Chest"]["pct"] == 40
    assert st["muscle_balance"]["warning"] is None
    wv = st["weekly_volume"]
    assert len(wv) == 8
    assert wv[-1]["volume"] == 10000 and wv[-1]["sessions"] == 1
    assert wv[0]["volume"] == 0

    # a chest-only log two days later should trip the legs warning… if legs fell under 15%
    _log_workout(client, today, [
        {"exercise": "Cable Fly", "sets": 10, "reps": 10, "weight": 400}])
    mb = client.get("/api/state").get_json()["stats"]["muscle_balance"]
    legs_pct = next(g["pct"] for g in mb["groups"] if g["group"] == "Legs")
    assert legs_pct < 15 and "leg" in mb["warning"].lower()


def test_recent_prs_and_e1rm(client):
    d = [(date.today() - timedelta(days=n)).isoformat() for n in range(4)]
    _log_workout(client, d[3], [{"exercise": "Deadlift", "sets": 3, "reps": 5, "weight": 200}])
    _log_workout(client, d[2], [{"exercise": "Deadlift", "sets": 3, "reps": 5, "weight": 210}])
    _log_workout(client, d[1], [{"exercise": "Deadlift", "sets": 3, "reps": 5, "weight": 205}])
    _log_workout(client, d[0], [{"exercise": "Deadlift", "sets": 3, "reps": 5, "weight": 220}])
    st = client.get("/api/state").get_json()["stats"]
    # first session is baseline, 210 and 220 are PRs, 205 is not; newest first
    assert [(p["weight"], p["prev"]) for p in st["recent_prs"]] == [(220, 210), (210, 200)]
    assert st["recent_prs"][0]["exercise"] == "Deadlift"
    # Epley e1RM on the best day: 220 * (1 + 5/30)
    e1rms = [s["e1rm"] for s in st["progression"]["Deadlift"]]
    assert max(e1rms) == round(220 * (1 + 5 / 30), 1)


def test_declining_weights_produce_no_prs(client):
    d = [(date.today() - timedelta(days=n)).isoformat() for n in range(3)]
    for day, wt in zip(reversed(d), [150, 140, 130]):
        _log_workout(client, day, [{"exercise": "Row", "sets": 3, "reps": 8, "weight": wt}])
    assert client.get("/api/state").get_json()["stats"]["recent_prs"] == []


def test_dashboard_radar(client):
    assert client.get("/api/state").get_json()["stats"]["dashboard"]["radar"] == []
    # low supplement -> deals warn
    client.post("/api/schedule", json={"name": "Fish Oil", "time": "Evening", "servings": 3})
    # a watch at its best price with 2 points -> deals good
    seed_watches = [{"item": "Whey", "created": "2026-07-01", "history": [
        {"date": "2026-07-01", "price": 60}, {"date": "2026-07-15", "price": 52}]}]
    # near milestone: 200 start, goal 185, current 190.5 -> 190 plate 0.5 away
    days = [(date.today() - timedelta(days=n)).isoformat() for n in range(2)]
    client.post("/api/weights", json={"date": days[1], "weight": 200})
    client.post("/api/weights", json={"date": days[0], "weight": 190.5})
    client.post("/api/profile", json={"weight": 190.5, "goal_weight": 185})
    client.post("/api/schedule", json={"name": "Fish Oil", "time": "Evening", "servings": 3})
    with open("nutrition_data.json") as f:
        data = json.load(f)
    data["watches"] = seed_watches
    with open("nutrition_data.json", "w") as f:
        json.dump(data, f)

    radar = client.get("/api/state").get_json()["stats"]["dashboard"]["radar"]
    by_tab = {}
    for r in radar:
        by_tab.setdefault(r["tab"], []).append(r)
    deals = {r["level"] for r in by_tab["deals"]}
    assert deals == {"warn", "good"}  # low stock + buy window
    assert any("190 plate" in r["text"] for r in by_tab["weight"])
    assert len(radar) <= 4


def test_backup_export_and_restore(client):
    client.post("/api/meals", json={"name": "Original meal", "protein": 40})
    r = client.get("/api/export/backup.json")
    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    backup = r.get_json()
    assert backup["meals"][0]["name"] == "Original meal"

    # garbage is rejected and nothing changes
    assert client.post("/api/import/backup", json={"nope": True}).status_code == 400
    assert client.post("/api/import/backup", data="not json",
                       content_type="application/json").status_code == 400
    assert client.get("/api/state").get_json()["meals"][0]["name"] == "Original meal"

    # a real restore replaces the data and snapshots what was there
    backup["meals"][0]["name"] = "Restored meal"
    backup["weights"] = [{"date": date.today().isoformat(), "weight": 190}]
    r = client.post("/api/import/backup", json=backup)
    assert r.status_code == 200 and r.get_json()["weights"] == 1
    state = client.get("/api/state").get_json()
    assert state["meals"][0]["name"] == "Restored meal"
    with open("nutrition_data.pre-restore.json") as f:
        assert json.load(f)["meals"][0]["name"] == "Original meal"


def test_backup_script_rotates(client, tmp_path):
    import subprocess, sys, shutil
    from pathlib import Path
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    root = Path(__file__).resolve().parent.parent
    shutil.copy2(root / "scripts" / "backup_data.py", repo / "scripts" / "backup_data.py")
    (repo / "nutrition_data.json").write_text('{"profile": {}}')
    # pre-seed 20 fake old snapshots; the run should prune to KEEP=14
    (repo / "backups").mkdir()
    for i in range(20):
        (repo / "backups" / f"nutrition_data-2026-01-{i + 1:02d}.json").write_text("{}")
    out = subprocess.run([sys.executable, str(repo / "scripts" / "backup_data.py")],
                         capture_output=True, text=True)
    assert out.returncode == 0
    snaps = list((repo / "backups").glob("nutrition_data-*.json"))
    assert len(snaps) == 14
    assert (repo / "backups" / f"nutrition_data-{date.today().isoformat()}.json").exists()


def test_remedy_cabinet(client):
    # everything is locked until the key turns
    assert client.post("/api/remedies/cabinet", json={"id": "x"}).status_code == 403
    client.post("/api/remedies/unlock", json={"key": "golden"})

    kb = client.get("/api/remedies").get_json()["remedies"]
    rid = kb[0]["id"]
    assert client.post("/api/remedies/cabinet", json={"id": "not-a-remedy"}).status_code == 404
    r = client.post("/api/remedies/cabinet", json={"id": rid})
    assert r.status_code == 200 and r.get_json()["cabinet"] == [rid]
    # idempotent add
    client.post("/api/remedies/cabinet", json={"id": rid})
    assert client.get("/api/state").get_json()["remedy_cabinet"] == [rid]

    assert client.delete(f"/api/remedies/cabinet/{rid}").status_code == 200
    assert client.delete(f"/api/remedies/cabinet/{rid}").status_code == 404
    assert client.get("/api/state").get_json()["remedy_cabinet"] == []


def test_remedy_of_day(client):
    assert client.get("/api/state").get_json()["remedy_of_day"] is None  # locked
    client.post("/api/remedies/unlock", json={"key": "GOLDEN"})
    rod1 = client.get("/api/state").get_json()["remedy_of_day"]
    rod2 = client.get("/api/state").get_json()["remedy_of_day"]
    assert rod1 is not None and rod1["evidence"] >= 4
    assert rod1["id"] == rod2["id"]  # deterministic within a day


def test_coach_fit(client):
    # empty profile -> maintaining
    fit = client.get("/api/state").get_json()["stats"]["coach_fit"]
    assert fit["direction"] == "maintain" and len(fit["ids"]) == 3

    client.post("/api/profile", json={"weight": 200, "goal_weight": 185})
    fit = client.get("/api/state").get_json()["stats"]["coach_fit"]
    assert fit["direction"] == "cut" and fit["label"] == "cutting"
    assert fit["ids"] == ["wicks", "goggins", "simmons"]

    client.post("/api/profile", json={"weight": 160, "goal_weight": 180, "age": 60})
    fit = client.get("/api/state").get_json()["stats"]["coach_fit"]
    assert fit["direction"] == "gain"
    assert fit["ids"][0] == "lalanne"  # 55+ puts longevity first


def test_roster_dossiers_complete(client):
    coaches = client.get("/api/state").get_json()["coaches"]
    assert len(coaches) == 20
    assert len({c["id"] for c in coaches}) == 20
    for c in coaches:
        for field in ("name", "goal", "style", "vibe", "workout",
                      "nutrition", "supplements", "voice", "caveats"):
            assert c.get(field, "").strip(), f"{c['id']} missing {field}"
    from app.stats import COACH_FIT
    ids = {c["id"] for c in coaches}
    for group in COACH_FIT.values():
        assert set(group) <= ids  # fit groups only name real coaches


def test_watch_insights(client):
    seed({"watches": [
        {"item": "Whey 5lb", "created": "2026-07-01", "history": [
            {"date": "2026-07-01", "price": 60}, {"date": "2026-07-10", "price": 55},
            {"date": "2026-07-20", "price": 50}]},
        {"item": "Creatine", "created": "2026-07-01", "history": [
            {"date": "2026-07-01", "price": 20}, {"date": "2026-07-10", "price": 18},
            {"date": "2026-07-20", "price": 25}]},
        {"item": "Fish Oil", "created": "2026-07-01", "history": []},
    ]})
    ins = {i["item"]: i for i in
           client.get("/api/state").get_json()["stats"]["watch_insights"]}
    assert ins["Whey 5lb"]["verdict"] == "best" and ins["Whey 5lb"]["vs_best_pct"] == 0
    assert ins["Creatine"]["verdict"] == "high" and ins["Creatine"]["vs_best_pct"] == 39
    assert "18" in ins["Creatine"]["text"]
    assert ins["Fish Oil"]["verdict"] is None


def test_deals_unit_price_passthrough(client, monkeypatch):
    fake = [{"item": "Whey 5lb", "store": "BulkCo", "price": "$49.99", "deal": "",
             "url": "", "unit_price": "$0.60/serving"}]
    monkeypatch.setattr(ai, "find_deals", lambda items, location="": fake)
    r = client.post("/api/deals", json={"items": "whey"})
    assert r.status_code == 200
    assert r.get_json()["results"][0]["unit_price"] == "$0.60/serving"
    assert client.get("/api/state").get_json()["deals"]["results"][0]["unit_price"] == "$0.60/serving"


def test_nutrition_trend(client):
    today = date.today().isoformat()
    yday = (date.today() - timedelta(days=1)).isoformat()
    # yesterday hit the 150g default goal; today hasn't (yet)
    client.post("/api/meals", json={"name": "Big day", "date": yday,
                                    "protein": 160, "calories": 1800})
    client.post("/api/meals", json={"name": "Light lunch", "date": today,
                                    "protein": 40, "calories": 500})
    nut = client.get("/api/state").get_json()["stats"]["nutrition"]
    assert len(nut["series"]) == 14
    assert nut["series"][-1] == {"date": today, "protein": 40, "calories": 500,
                                 "carbs": 0, "fat": 0, "fiber": 0}
    assert nut["series"][-2]["protein"] == 160
    assert nut["protein_goal"] == 150
    # an unfinished today doesn't break the streak started yesterday
    assert nut["protein_streak"] == 1
    assert nut["hit_days_14"] == 1
    # once today hits the goal it joins the streak
    client.post("/api/meals", json={"name": "Steak", "date": today, "protein": 120})
    nut = client.get("/api/state").get_json()["stats"]["nutrition"]
    assert nut["protein_streak"] == 2
    assert nut["hit_days_14"] == 2


def test_repeat_yesterday(client):
    assert client.post("/api/meals/repeat-yesterday").status_code == 400
    yday = (date.today() - timedelta(days=1)).isoformat()
    client.post("/api/meals", json={"name": "Chili", "date": yday,
                                    "protein": 45, "calories": 600})
    r = client.post("/api/meals/repeat-yesterday")
    assert r.status_code == 200 and r.get_json()["count"] == 1
    today_meals = [m for m in client.get("/api/state").get_json()["meals"]
                   if m["date"] == date.today().isoformat()]
    assert len(today_meals) == 1
    assert today_meals[0]["name"] == "Chili" and today_meals[0]["protein"] == 45
    assert today_meals[0]["notes"] == "Repeated from yesterday"


def test_weight_replaces_same_day_and_syncs_profile(client):
    today = date.today().isoformat()
    client.post("/api/weights", json={"date": today, "weight": 201})
    client.post("/api/weights", json={"date": today, "weight": 200.5})
    state = client.get("/api/state").get_json()
    assert len(state["weights"]) == 1
    assert state["weights"][0]["weight"] == 200.5
    assert state["profile"]["weight"] == 200.5


def test_weight_extras_streak_and_milestones(client):
    assert client.get("/api/state").get_json()["stats"]["weight_extras"] == {"has_data": False}
    d = [(date.today() - timedelta(days=n)).isoformat() for n in range(5)]
    # 200 -> 193.8, weighed daily except a gap 3 days ago
    for day, wt in [(d[4], 200), (d[3], 198.5), (d[1], 195.2), (d[0], 193.8)]:
        client.post("/api/weights", json={"date": day, "weight": wt})
    client.post("/api/profile", json={"goal_weight": 185})
    wx = client.get("/api/state").get_json()["stats"]["weight_extras"]
    assert wx["streak"] == 2  # the gap 3 days ago broke the run
    assert wx["cutting"] is True
    # start 200, goal 185 -> plates at 195, 190, then the goal itself
    assert [m["target"] for m in wx["milestones"]] == [195, 190, 185]
    m195 = wx["milestones"][0]
    assert m195["crossed"] is True and m195["date"] == d[0]  # 193.8 is the first dip under 195
    assert wx["next_milestone"] == {"target": 190, "to_go": 3.8}


def test_weight_weekly_checkins_and_plateau(client):
    monday = date.today() - timedelta(days=date.today().weekday())
    for wk_back, avg in [(3, 200.1), (2, 200.0), (1, 200.2), (0, 200.1)]:
        day = monday - timedelta(weeks=wk_back)
        client.post("/api/weights", json={"date": day.isoformat(), "weight": avg})
    client.post("/api/profile", json={"goal_weight": 185})
    wx = client.get("/api/state").get_json()["stats"]["weight_extras"]
    assert len(wx["weeks"]) == 4
    assert wx["weeks"][0]["delta"] is None
    assert wx["weeks"][1]["delta"] == -0.1
    assert wx["plateau"] is not None and "plateau" in wx["plateau"]
    # near the goal, three flat weeks are maintenance, not a plateau
    client.post("/api/profile", json={"goal_weight": 199})
    wx = client.get("/api/state").get_json()["stats"]["weight_extras"]
    assert wx["plateau"] is None


def test_checklist_toggle(client):
    client.post("/api/schedule", json={"name": "Creatine", "time": "Morning"})
    r = client.post("/api/checklist/toggle", json={"name": "Creatine", "time": "Morning"})
    assert r.get_json()["taken"] is True
    assert client.get("/api/state").get_json()["stats"]["checklist"][0]["taken"] is True
    r = client.post("/api/checklist/toggle", json={"name": "Creatine", "time": "Morning"})
    assert r.get_json()["taken"] is False


def test_schedule_dose_and_servings(client):
    r = client.post("/api/schedule", json={"name": "Creatine", "time": "Morning",
                                           "dose": "5g", "servings": 60})
    assert r.status_code == 200
    item = client.get("/api/state").get_json()["schedule"][0]
    assert item["dose"] == "5g" and item["servings_left"] == 60

    # ticking consumes a serving; un-ticking gives it back
    client.post("/api/checklist/toggle", json={"name": "Creatine", "time": "Morning"})
    assert client.get("/api/state").get_json()["schedule"][0]["servings_left"] == 59
    client.post("/api/checklist/toggle", json={"name": "Creatine", "time": "Morning"})
    assert client.get("/api/state").get_json()["schedule"][0]["servings_left"] == 60

    # refill via PUT
    r = client.put("/api/schedule/0", json={"dose": "10g", "servings": 90})
    assert r.status_code == 200
    item = client.get("/api/state").get_json()["schedule"][0]
    assert item["dose"] == "10g" and item["servings_left"] == 90
    assert client.put("/api/schedule/99", json={"dose": "x"}).status_code == 404


def test_checklist_low_flag(client):
    client.post("/api/schedule", json={"name": "Fish Oil", "time": "Evening", "servings": 7})
    client.post("/api/schedule", json={"name": "Creatine", "time": "Morning", "servings": 60})
    by_name = {c["name"]: c for c in
               client.get("/api/state").get_json()["stats"]["checklist"]}
    assert by_name["Fish Oil"]["low"] is True
    assert by_name["Creatine"]["low"] is False


def test_adherence_series(client):
    assert client.get("/api/state").get_json()["stats"]["adherence_series"] == []
    client.post("/api/schedule", json={"name": "Creatine", "time": "Morning"})
    client.post("/api/checklist/toggle", json={"name": "Creatine", "time": "Morning"})
    series = client.get("/api/state").get_json()["stats"]["adherence_series"]
    assert len(series) == 30
    assert series[-1]["date"] == date.today().isoformat()
    assert series[-1]["pct"] == 100
    assert series[0]["pct"] == 0


def test_briefing_reports_low_supplements(client, monkeypatch):
    client.post("/api/schedule", json={"name": "Fish Oil", "time": "Evening", "servings": 3})
    seen = {}
    monkeypatch.setattr(ai, "daily_briefing",
                        lambda profile, persona, ctx: seen.update(json.loads(ctx)) or "Rise and grind.")
    assert client.post("/api/briefing").status_code == 200
    assert seen["supplements_running_low"] == ["Fish Oil (3 left)"]


def test_ai_parse_and_add(client, monkeypatch):
    fake = [{"name": "Test burrito", "protein": 40, "calories": 700,
             "carbs": 80, "fat": 20, "fiber": 10}]
    monkeypatch.setattr(ai, "parse_meals", lambda desc: fake)
    r = client.post("/api/meals/ai/parse", json={"description": "a burrito"})
    assert r.get_json()["meals"] == fake

    r = client.post("/api/meals/ai/add", json={"meals": fake})
    assert r.status_code == 200
    meal = client.get("/api/state").get_json()["meals"][0]
    assert meal["name"] == "Test burrito" and meal["notes"] == "Estimated by Claude"


def test_ai_unavailable_is_5xx_not_crash(client, monkeypatch):
    def boom(desc):
        raise ai.AIUnavailable("no backend")
    monkeypatch.setattr(ai, "parse_meals", boom)
    r = client.post("/api/meals/ai/parse", json={"description": "food"})
    assert r.status_code == 502
    assert "no backend" in r.get_json()["error"]


def test_deals_endpoint(client, monkeypatch):
    fake = [{"item": "Whey 5lb", "store": "Shop", "price": "$49.99",
             "deal": "20% off", "url": "https://example.com"}]
    monkeypatch.setattr(ai, "find_deals", lambda items, location="": fake)
    r = client.post("/api/deals", json={"items": "whey protein"})
    assert r.get_json()["results"] == fake
    # cached in state for next load
    assert client.get("/api/state").get_json()["deals"]["results"] == fake


def test_shopping_list(client):
    assert client.post("/api/shopping", json={"item": "Whey 5lb"}).status_code == 200
    # batch + dedupe (case-insensitive)
    r = client.post("/api/shopping", json={"items": ["whey 5lb", "Creatine"]})
    assert r.get_json()["added"] == 1
    assert client.get("/api/state").get_json()["shopping_list"] == ["Whey 5lb", "Creatine"]
    assert client.delete("/api/shopping/0").status_code == 200
    assert client.get("/api/state").get_json()["shopping_list"] == ["Creatine"]
    assert client.post("/api/shopping", json={"item": "  "}).status_code == 400


def test_price_watch_lifecycle(client, monkeypatch):
    # create from a found deal
    deal = {"item": "Whey Protein 5lb", "store": "ShopA", "price": "$54.99",
            "deal": "intro", "url": "https://a.example"}
    assert client.post("/api/watches", json=deal).status_code == 200
    assert client.post("/api/watches", json=deal).status_code == 400  # no duplicates
    w = client.get("/api/state").get_json()["watches"][0]
    assert w["history"][0]["price"] == 54.99

    # recheck: cheaper price found elsewhere → point recorded + push fired
    from app import notify
    pushed = {}
    monkeypatch.setattr(notify, "push",
                        lambda st, title, msg, priority='default':
                        pushed.update(title=title, msg=msg) or True)
    monkeypatch.setattr(ai, "find_deals", lambda items, location="": [
        {"item": "Whey Protein 5 lb tub", "store": "ShopB", "price": "$49.99",
         "deal": "sale", "url": "https://b.example"}])
    r = client.post("/api/watches/recheck")
    body = r.get_json()
    assert body["updated"] == 1 and len(body["drops"]) == 1
    assert body["drops"][0]["store"] == "ShopB"
    assert "Price drop" in pushed["title"]

    # one point per day: the same-day creation point is replaced, and the
    # drop was still detected against the pre-replacement baseline
    w = client.get("/api/state").get_json()["watches"][0]
    assert len(w["history"]) == 1 and w["history"][-1]["price"] == 49.99

    # a second same-day recheck neither stacks points nor re-alerts
    r = client.post("/api/watches/recheck")
    assert r.get_json()["drops"] == []
    w = client.get("/api/state").get_json()["watches"][0]
    assert len(w["history"]) == 1

    assert client.delete("/api/watches/0").status_code == 200
    assert client.post("/api/watches/recheck").status_code == 400  # none left


def test_deals_location_persists(client, monkeypatch):
    monkeypatch.setattr(ai, "find_deals", lambda items, location="": [
        {"item": "x", "store": "s", "price": "$1", "deal": "", "url": ""}])
    client.post("/api/deals", json={"items": "whey", "location": "UK · MyProtein"})
    assert client.get("/api/state").get_json()["settings"]["deals_location"] == "UK · MyProtein"


def test_coach_roster_and_selection(client):
    state = client.get("/api/state").get_json()
    assert len(state["coaches"]) == 20
    assert state["coach"] == "cutler"
    ids = {c["id"] for c in state["coaches"]}
    assert {"cutler", "arnold", "hall", "jetli", "goggins",
            "bolt", "wicks", "austin", "simmons", "adriene",
            "fraser", "phelps", "tyson", "pavel", "heria",
            "nippard", "casseyho", "lalanne", "serena", "biles"} == ids
    # every coach carries the full persona contract
    for c in state["coaches"]:
        for field in ("name", "emoji", "goal", "style", "vibe",
                      "workout", "nutrition", "supplements", "voice", "caveats"):
            assert c.get(field), f"{c.get('id')} missing {field}"

    assert client.post("/api/coach/select", json={"id": "goggins"}).status_code == 200
    assert client.get("/api/state").get_json()["coach"] == "goggins"
    assert client.post("/api/coach/select", json={"id": "nope"}).status_code == 404

    # saving the profile must not lose the selected coach
    client.post("/api/profile", json={"name": "G", "daily_protein_g": 160})
    assert client.get("/api/state").get_json()["coach"] == "goggins"


def test_weekly_plan_uses_selected_persona(client, monkeypatch):
    fake = {"week": [{"day": "Monday", "title": "Push", "focus": "Chest",
                      "details": ["Bench 4x10"]}],
            "meals": [{"meal": "Breakfast", "items": "Oats", "protein": 30, "calories": 400}],
            "supplements": ["Creatine 5g"],
            "coach_note": "Ain't nothin' but a peanut."}
    captured = {}

    def fake_plan(profile, persona, context=""):
        captured["persona"] = persona
        return fake
    monkeypatch.setattr(ai, "weekly_plan", fake_plan)

    r = client.post("/api/plan")
    assert r.status_code == 200
    assert r.get_json()["plan"] == fake
    assert "Jay Cutler" in captured["persona"]          # default coach
    assert "never claim" in captured["persona"]          # inspired-by framing
    assert "Safety guardrails" in captured["persona"]    # caveats injected
    # cached for the next state load
    assert client.get("/api/state").get_json()["plan"]["plan"] == fake


def test_coach_summary_uses_selected_persona(client, monkeypatch):
    client.post("/api/meals", json={"name": "Rice", "protein": 10, "calories": 200})
    client.post("/api/coach/select", json={"id": "simmons"})
    captured = {}

    def fake_summary(week_data, persona=None):
        captured["persona"] = persona
        return "**What went well**: everything, darling!"
    monkeypatch.setattr(ai, "coaching_summary", fake_summary)

    r = client.post("/api/coach")
    assert r.status_code == 200
    assert r.get_json()["coach"] == "simmons"
    assert "Richard Simmons" in captured["persona"]


def test_profile_stores_age_sex_notes(client):
    client.post("/api/profile", json={"name": "G", "age": 44, "sex": "male",
                                      "notes": "bad knee", "weight": 200,
                                      "daily_protein_g": 150, "daily_calories": 2000})
    p = client.get("/api/state").get_json()["profile"]
    assert p["age"] == 44 and p["sex"] == "male" and p["notes"] == "bad knee"


def test_supplement_advice_uses_profile_and_persona(client, monkeypatch):
    client.post("/api/profile", json={"name": "G", "age": 44, "sex": "male",
                                      "daily_protein_g": 150, "daily_calories": 2000})
    client.post("/api/coach/select", json={"id": "nippard"})
    client.post("/api/schedule", json={"name": "Creatine", "time": "Morning"})

    fake = {"recommendations": [{"name": "Creatine Monohydrate", "dose": "5g",
                                 "timing": "daily, any time", "priority": "essential",
                                 "why": "strongest evidence base in sports nutrition"}],
            "skip": [{"name": "BCAAs", "why": "redundant with adequate protein"}],
            "coach_note": "The science says.",
            "safety_note": "Check with your doctor."}
    captured = {}

    def fake_advice(profile, persona, context):
        captured["profile"] = profile
        captured["persona"] = persona
        captured["context"] = context
        return fake
    monkeypatch.setattr(ai, "supplement_advice", fake_advice)

    r = client.post("/api/supplements/advice")
    assert r.status_code == 200
    assert r.get_json()["advice"] == fake
    assert captured["profile"]["age"] == 44 and captured["profile"]["sex"] == "male"
    assert "Jeff Nippard" in captured["persona"]
    assert "Creatine" in captured["context"]          # current stack included
    assert "workouts_last_7d" in captured["context"]  # history included
    # cached in state
    assert client.get("/api/state").get_json()["supp_advice"]["advice"] == fake


def test_supplement_kb_shape_and_verdicts(client):
    from app.supplement_kb import KB, VERDICTS, kb_for_prompt
    assert len(KB) == 34
    ids = [s["id"] for s in KB]
    assert len(ids) == len(set(ids)), "duplicate KB ids"
    for s in KB:
        assert s["verdict"] in VERDICTS, f"{s['id']} bad verdict"
        for field in ("name", "category", "evidence_for", "dose", "timing",
                      "pros", "cons", "best_for", "skip_if"):
            assert s.get(field), f"{s['id']} missing {field}"
    # the honest tiers exist and are populated
    verdicts = {s["verdict"] for s in KB}
    assert verdicts == set(VERDICTS)
    garbage = {s["id"] for s in KB if s["verdict"] == "garbage"}
    assert {"bcaa", "glutamine", "fat-burners", "test-boosters",
            "greens-powder", "zma"} == garbage
    # prompt grounding contains the verdict language
    grounding = kb_for_prompt()
    assert "GARBAGE" in grounding and "Creatine" in grounding
    # served to the frontend
    assert len(client.get("/api/state").get_json()["kb"]) == 34


def test_schedule_accepts_custom_names(client):
    r = client.post("/api/schedule", json={"name": "Creatine Monohydrate", "time": "Morning"})
    assert r.status_code == 200
    assert client.get("/api/state").get_json()["schedule"] == [
        {"name": "Creatine Monohydrate", "time": "Morning", "dose": ""}]


def test_meal_suggestions_use_remaining_macros_and_persona(client, monkeypatch):
    client.post("/api/coach/select", json={"id": "wicks"})
    client.post("/api/meals", json={"name": "Eggs on toast", "protein": 30, "calories": 450})

    fake = [{"name": "Chicken stir-fry", "items": "chicken, veg, rice",
             "protein": 45, "calories": 550, "carbs": 55, "fat": 12,
             "fiber": 6, "why": "covers half your remaining protein"}]
    captured = {}

    def fake_suggest(profile, persona, context):
        captured["persona"] = persona
        captured["context"] = json.loads(context)
        return fake
    monkeypatch.setattr(ai, "suggest_meals", fake_suggest)

    r = client.post("/api/meals/suggest")
    assert r.status_code == 200
    assert r.get_json()["suggestions"] == fake
    assert r.get_json()["coach"] == "wicks"
    assert "Joe Wicks" in captured["persona"]
    ctx = captured["context"]
    assert ctx["remaining_today"] == {"protein_g": 120, "calories": 1550}
    assert ctx["eaten_today"][0]["name"] == "Eggs on toast"
    assert "recent_regulars" in ctx and "time_now" in ctx


def test_coach_chat_grounded_and_persistent(client, monkeypatch):
    client.post("/api/coach/select", json={"id": "pavel"})
    client.post("/api/meals", json={"name": "Eggs", "protein": 30, "calories": 400})
    captured = {}

    def fake_chat(persona, history, message, snapshot):
        captured.update(persona=persona, history=list(history),
                        message=message, snapshot=json.loads(snapshot))
        return "Practice, comrade. Five crisp singles, then walk away."
    monkeypatch.setattr(ai, "coach_chat", fake_chat)

    r = client.post("/api/coach/chat", json={"message": "should I train today?"})
    assert r.status_code == 200 and "comrade" in r.get_json()["reply"]
    assert "Pavel Tsatsouline" in captured["persona"]
    assert captured["history"] == []  # first turn
    snap = captured["snapshot"]
    assert snap["today_macros"]["protein"] == 30
    assert "readiness" in snap and "plan_progress" in snap

    # second turn sees the first exchange
    client.post("/api/coach/chat", json={"message": "and food?"})
    assert len(captured["history"]) == 2
    assert captured["history"][0]["role"] == "user"

    chat = client.get("/api/state").get_json()["coach_chat"]
    assert len(chat) == 4 and chat[1]["coach"] == "pavel"

    assert client.delete("/api/coach/chat").status_code == 200
    assert client.get("/api/state").get_json()["coach_chat"] == []
    assert client.post("/api/coach/chat", json={"message": "  "}).status_code == 400


def test_plan_progress(client, monkeypatch):
    assert client.get("/api/state").get_json()["stats"]["plan_progress"] == {"has_plan": False}

    # seed a plan via the mocked generator, then log a workout on Monday
    week = [{"day": "Monday", "title": "Push", "focus": "Chest", "details": ["Bench 4x10"]},
            {"day": "Sunday", "title": "Rest Day", "focus": "Recovery", "details": ["Walk"]}]
    fake = {"week": week, "meals": [], "supplements": [], "coach_note": "Go."}
    monkeypatch.setattr(ai, "weekly_plan", lambda p, persona, context="": fake)
    client.post("/api/plan")

    monday = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    client.post("/api/workouts", json={"date": monday, "name": "Push", "duration": 60,
                                       "exercises": [{"exercise": "Bench", "sets": 4,
                                                      "reps": 10, "weight": 135}]})
    prog = client.get("/api/state").get_json()["stats"]["plan_progress"]
    assert prog["has_plan"] is True
    by_day = {x["day"].lower(): x["status"] for x in prog["days"]}
    assert by_day["monday"] == "done"
    assert by_day["sunday"] in ("rest",)
    assert prog["done"] >= 1 and prog["pct"] is not None


def test_weekly_review_archived(client, monkeypatch):
    client.post("/api/meals", json={"name": "Rice", "protein": 10, "calories": 200})
    monkeypatch.setattr(ai, "coaching_summary",
                        lambda week, persona=None: "**What went well**: showing up.")
    client.post("/api/coach")
    reviews = client.get("/api/state").get_json()["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["date"] == date.today().isoformat()
    assert "showing up" in reviews[0]["summary"]


def test_dashboard_command_center(client, monkeypatch):
    dash = client.get("/api/state").get_json()["stats"]["dashboard"]
    # empty data: 7-day grid exists, streaks zeroed, briefing action offered
    assert len(dash["week_grid"]) == 7
    assert sum(1 for d in dash["week_grid"] if d["is_today"]) == 1
    assert dash["streaks"] == {"meals": 0, "weights": 0, "vitals": 0, "workout_weeks": 0}
    assert any(a["id"] == "briefing" for a in dash["actions"])
    assert len(dash["actions"]) <= 2

    # log things today → grid reflects them, streaks tick
    today = date.today().isoformat()
    client.post("/api/meals", json={"name": "Big meal", "protein": 150, "calories": 900})
    client.post("/api/weights", json={"date": today, "weight": 200})
    client.post("/api/workouts", json={"date": today, "name": "Push", "duration": 60,
                                       "exercises": []})
    dash = client.get("/api/state").get_json()["stats"]["dashboard"]
    today_cell = next(d for d in dash["week_grid"] if d["is_today"])
    assert today_cell["workout"] == "done"
    assert today_cell["protein_pct"] == 100
    assert today_cell["weighed"] is True
    assert dash["streaks"]["meals"] == 1 and dash["streaks"]["weights"] == 1

    # a generated briefing clears the briefing action
    from app import notify
    monkeypatch.setattr(notify, "push", lambda *a, **k: True)
    monkeypatch.setattr(ai, "daily_briefing", lambda p, per, c: "Go lift.")
    client.post("/api/briefing")
    dash = client.get("/api/state").get_json()["stats"]["dashboard"]
    assert not any(a["id"] == "briefing" for a in dash["actions"])


def test_supplement_adherence(client):
    assert client.get("/api/state").get_json()["stats"]["adherence"] == {"has_schedule": False}
    client.post("/api/schedule", json={"name": "Creatine", "time": "Morning"})
    client.post("/api/checklist/toggle", json={"name": "Creatine", "time": "Morning"})
    adh = client.get("/api/state").get_json()["stats"]["adherence"]
    assert adh["has_schedule"] is True
    assert adh["slots"] == 7 and adh["taken"] == 1
    assert adh["pct"] == 14  # 1 of 7 daily slots this week


def test_vitals_ingest_merge_and_summary(client):
    state = client.get("/api/state").get_json()
    token = state["settings"]["ingest_token"]
    assert token  # auto-generated on first load
    assert state["stats"]["vitals"] == {"has_data": False}

    # webhook rejects bad tokens
    assert client.post("/api/ingest?token=wrong", json={"steps": 100}).status_code == 401

    today = date.today().isoformat()
    r = client.post(f"/api/ingest?token={token}", json={
        "date": today, "stepCount": 9000, "restingHeartRate": 58, "sleep_minutes": 450})
    assert r.status_code == 200 and r.get_json()["merged"] == 1

    # same-day merge: BP arrives later, steps survive
    client.post("/api/vitals", json={"date": today, "bp_sys": 128, "bp_dia": 82})
    vs = client.get("/api/state").get_json()["stats"]["vitals"]
    assert vs["has_data"] is True
    assert vs["latest"]["steps"]["value"] == 9000
    assert vs["latest"]["sleep_h"]["value"] == 7.5   # minutes converted
    assert vs["bp"] == {"sys": 128, "dia": 82, "date": today, "level": "elevated"}
    assert len(client.get("/api/state").get_json()["vitals"]) == 1

    # batch form
    r = client.post(f"/api/ingest?token={token}", json={"days": [
        {"date": "2026-07-29", "steps": 7000}, {"date": "2026-07-30", "steps": 11000}]})
    assert r.get_json()["merged"] == 2


def test_settings_and_notify(client, monkeypatch):
    client.post("/api/settings", json={"ntfy_topic": "gna-test", "daily_steps": 10000})
    s = client.get("/api/state").get_json()["settings"]
    assert s["ntfy_topic"] == "gna-test" and s["daily_steps"] == 10000

    from app import notify
    sent = {}
    monkeypatch.setattr(notify, "push", lambda st, title, msg, priority='default':
                        sent.update(topic=st["ntfy_topic"], title=title) or True)
    assert client.post("/api/notify/test").status_code == 200
    assert sent["topic"] == "gna-test"


def test_briefing_generates_pushes_and_caches(client, monkeypatch):
    client.post("/api/coach/select", json={"id": "goggins"})
    from app import notify
    pushed = {}
    monkeypatch.setattr(notify, "push", lambda st, title, msg, priority='default':
                        pushed.update(title=title) or True)
    captured = {}

    def fake_brief(profile, persona, context):
        captured["persona"] = persona
        captured["context"] = json.loads(context)
        return "Run. Eat. Stay hard."
    monkeypatch.setattr(ai, "daily_briefing", fake_brief)

    r = client.post("/api/briefing")
    assert r.status_code == 200
    assert r.get_json()["text"] == "Run. Eat. Stay hard."
    assert "David Goggins" in captured["persona"]
    assert "goals" in captured["context"] and "weekday" in captured["context"]
    assert "David Goggins" in pushed["title"]

    state = client.get("/api/state").get_json()
    assert state["briefing"]["date"] == date.today().isoformat()
    assert state["briefing"]["coach"] == "goggins"


def test_readiness_engine(client):
    token_state = client.get("/api/state").get_json()
    assert token_state["stats"]["readiness"] == {"has_data": False}
    token = token_state["settings"]["ingest_token"]

    # 5 baseline days, then a rough night
    days = [{"date": (date.today() - timedelta(days=i)).isoformat(),
             "sleep_h": 7.5, "hrv_ms": 50, "resting_hr": 60} for i in range(1, 6)]
    days.append({"date": date.today().isoformat(),
                 "sleep_h": 6.0, "hrv_ms": 40, "resting_hr": 66})
    client.post(f"/api/ingest?token={token}", json={"days": days})

    rd = client.get("/api/state").get_json()["stats"]["readiness"]
    assert rd["has_data"] is True
    assert rd["components"]["sleep"]["score"] == 80      # 6.0 / 7.5
    assert rd["components"]["hrv"]["score"] == 80        # 40 / 50
    assert rd["components"]["resting_hr"]["score"] == 91  # 60 / 66
    assert rd["score"] == 83 and rd["level"] == "primed"


def test_readiness_series_and_vitals_weeks(client):
    token = client.get("/api/state").get_json()["settings"]["ingest_token"]
    days = [{"date": (date.today() - timedelta(days=i)).isoformat(),
             "sleep_h": 7.5, "hrv_ms": 50, "resting_hr": 60, "steps": 9000}
            for i in range(1, 6)]
    days.append({"date": date.today().isoformat(),
                 "sleep_h": 6.0, "hrv_ms": 40, "resting_hr": 66, "steps": 4000})
    client.post(f"/api/ingest?token={token}", json={"days": days})
    st = client.get("/api/state").get_json()["stats"]

    series = st["readiness_series"]
    assert len(series) == 6
    assert series[-1]["date"] == date.today().isoformat()
    # today's entry scores against the flat 5-day baseline: .8*40 + .8*35 + (60/66)*25
    assert series[-1]["score"] == 83
    # a flat baseline day scores 100 on hrv/rhr and 100 on sleep (7.5 vs 7.5 target)
    assert series[1]["score"] == 100

    weeks = st["vitals_weeks"]
    assert 1 <= len(weeks) <= 2
    total_n = sum(w["n"] for w in weeks)
    assert total_n == 6
    assert weeks[0]["week_start"] <= date.today().isoformat()
    if len(weeks) == 2:
        assert weeks[1]["resting_hr_delta"] is not None


def test_step_stats(client):
    token = client.get("/api/state").get_json()["settings"]["ingest_token"]
    d = [(date.today() - timedelta(days=n)).isoformat() for n in range(4)]
    # goal defaults to 8000: hit, hit, miss, hit (oldest->newest: d3 hit, d2 miss, d1 hit, d0 hit)
    client.post(f"/api/ingest?token={token}", json={"days": [
        {"date": d[3], "steps": 9000}, {"date": d[2], "steps": 5000},
        {"date": d[1], "steps": 8000}, {"date": d[0], "steps": 12000}]})
    ss = client.get("/api/state").get_json()["stats"]["step_stats"]
    assert ss == {"has_goal": True, "goal": 8000, "streak": 2, "hits_14": 3}


def test_achievements_wall(client):
    seed(week_of_data())
    badges = {b["id"]: b for b in client.get("/api/state").get_json()["stats"]["achievements"]}
    assert badges["first_blood"]["earned"] is True
    assert badges["iron_week"]["earned"] is True          # 6 sessions this week
    assert badges["quad_stomp"]["earned"] is False        # ~3k lbs day vs 10k
    assert badges["peanut"]["earned"] is False and badges["peanut"]["progress"] == 6
    assert badges["wired_in"]["earned"] is False


def test_photo_endpoint(client, monkeypatch):
    fake = [{"name": "Grilled chicken plate", "protein": 45, "calories": 520,
             "carbs": 40, "fat": 15, "fiber": 5}]
    seen = {}
    monkeypatch.setattr(ai, "parse_meal_photo", lambda path: seen.update(path=path) or fake)
    tiny_png = ("data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
                "2mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=")
    r = client.post("/api/meals/photo", json={"image": tiny_png})
    assert r.status_code == 200 and r.get_json()["meals"] == fake
    assert seen["path"].endswith(".png")
    assert client.post("/api/meals/photo", json={"image": "nope"}).status_code == 400


def test_voice_routing(client, monkeypatch):
    monkeypatch.setattr(ai, "route_voice",
                        lambda t: {"action": "weight", "pounds": 199.5})
    r = client.post("/api/voice", json={"text": "weigh in at one ninety nine and a half"})
    assert r.status_code == 200 and "199.5" in r.get_json()["message"]
    assert client.get("/api/state").get_json()["profile"]["weight"] == 199.5

    monkeypatch.setattr(ai, "route_voice",
                        lambda t: {"action": "supplement", "name": "Creatine", "time": "Morning"})
    r = client.post("/api/voice", json={"text": "took my creatine"})
    assert r.get_json()["action"] == "supplement"

    monkeypatch.setattr(ai, "route_voice",
                        lambda t: {"action": "meal", "description": "chicken and rice"})
    monkeypatch.setattr(ai, "parse_meals",
                        lambda d: [{"name": "Chicken and rice", "protein": 50,
                                    "calories": 600, "carbs": 60, "fat": 10, "fiber": 3}])
    r = client.post("/api/voice", json={"text": "log chicken and rice"})
    assert "50g protein" in r.get_json()["message"]
    meal = client.get("/api/state").get_json()["meals"][-1]
    assert meal["notes"] == "Logged by voice"

    monkeypatch.setattr(ai, "route_voice",
                        lambda t: {"action": "unknown", "reason": "not a log command"})
    assert client.post("/api/voice", json={"text": "what is love"}).status_code == 400


def test_remedies_kb_loads_and_merges(client):
    from app.remedies_kb import CATEGORIES, kb_stats, load_kb, search_kb
    kb = load_kb()
    assert len(kb) >= 250, f"expected a full archive, got {len(kb)}"
    ids = [r['id'] for r in kb]
    names = [r['name'].lower() for r in kb]
    assert len(names) == len(set(names)), "cross-tradition duplicates must merge"
    for r in kb[:50] + kb[-50:]:
        assert 1 <= r['evidence'] <= 5
        assert r['traditions'] and r['summary'] and r['safety']
        assert all(c in CATEGORIES for c in r['categories'])
    # honey spans multiple traditions in the source — the merge must show it
    honey = next((r for r in kb if r['name'].lower() == 'honey'), None)
    assert honey and len(honey['traditions']) >= 2
    assert kb[0]['evidence'] >= kb[-1]['evidence']  # strongest first
    assert search_kb('sleep')  # relevance search returns something
    stats_ = kb_stats()
    assert stats_['count'] == len(kb) and stats_['traditions'] >= 8


def test_remedies_gate_and_unlock(client):
    # locked by default: no KB leaves the server
    assert client.get("/api/remedies").status_code == 403
    assert client.post("/api/remedies/ask", json={"question": "sleep"}).status_code == 403
    state = client.get("/api/state").get_json()
    assert state["remedies_unlocked"] is False
    assert "remedies" not in state  # only stats are teased
    assert state["remedies_stats"]["count"] >= 250

    assert client.post("/api/remedies/unlock", json={"key": "wrong"}).status_code == 403
    assert client.post("/api/remedies/unlock", json={"key": "golden"}).status_code == 200
    assert client.get("/api/state").get_json()["remedies_unlocked"] is True
    r = client.get("/api/remedies")
    assert r.status_code == 200 and len(r.get_json()["remedies"]) >= 250


def test_remedies_ask_grounded(client, monkeypatch):
    client.post("/api/remedies/unlock", json={"key": "GOLDEN"})
    captured = {}

    def fake_answer(profile, question, matches):
        captured["question"] = question
        captured["matches"] = matches
        return "Valerian is your best-graded option. Talk to a doctor first."
    monkeypatch.setattr(ai, "remedy_answer", fake_answer)

    r = client.post("/api/remedies/ask", json={"question": "help me sleep"})
    assert r.status_code == 200
    body = r.get_json()
    assert "sources" in body and len(body["sources"]) >= 1
    assert captured["matches"], "answer must be grounded in KB matches"
    assert all("safety" in m for m in captured["matches"])

    r = client.post("/api/remedies/ask", json={"question": "zzzqqqxxx"})
    assert r.status_code == 400  # no matches → honest refusal, no AI call


def test_vitals_intelligence(client):
    token = client.get("/api/state").get_json()["settings"]["ingest_token"]
    # 7 baseline days: steady, then 3 recent days trending bad
    days = []
    for i in range(9, 2, -1):
        days.append({"date": (date.today() - timedelta(days=i)).isoformat(),
                     "steps": 9000, "resting_hr": 58, "hrv_ms": 52, "sleep_h": 7.5})
    for i in range(2, -1, -1):
        days.append({"date": (date.today() - timedelta(days=i)).isoformat(),
                     "steps": 4000, "resting_hr": 64, "hrv_ms": 40, "sleep_h": 5.5})
    client.post(f"/api/ingest?token={token}", json={"days": days})

    vs = client.get("/api/state").get_json()["stats"]["vitals"]
    # deltas vs 7d avg, direction-aware
    assert vs["deltas"]["resting_hr"]["diff"] > 0 and vs["deltas"]["resting_hr"]["good"] is False
    assert vs["deltas"]["sleep_h"]["diff"] < 0 and vs["deltas"]["sleep_h"]["good"] is False
    # sleep debt: recent 7 logged nights = 4×7.5 + 3×5.5 → debt 3×2.0 = 6.0h
    assert vs["sleep_debt"]["hours"] == 6.0 and vs["sleep_debt"]["target"] == 7.5
    # signals: rising RHR (64 vs 58 baseline), suppressed HRV (40 vs 52), sleep debt ≥5h
    texts = " | ".join(s["text"] for s in vs["signals"])
    assert "Resting heart rate" in texts
    assert "HRV is suppressed" in texts
    assert "sleep debt" in texts


def test_vitals_edit_delete_and_export(client):
    today = date.today().isoformat()
    client.post("/api/vitals", json={"date": today, "steps": 8000,
                                     "resting_hr": 60, "sleep_h": 7})
    # edit: change steps, blank resting_hr (removes the reading), keep sleep
    r = client.put("/api/entry/vitals/0", json={"date": today, "steps": 8500,
                                                "resting_hr": "", "sleep_h": 7})
    assert r.status_code == 200
    v = client.get("/api/state").get_json()["vitals"][0]
    assert v["steps"] == 8500 and "resting_hr" not in v and v["sleep_h"] == 7.0

    res = client.get("/api/export/vitals.csv")
    assert res.status_code == 200 and b"8500" in res.data

    assert client.delete("/api/entry/vitals/0").status_code == 200
    assert client.get("/api/state").get_json()["vitals"] == []


def test_sleep_target_setting(client):
    client.post("/api/settings", json={"sleep_target": 8.5})
    assert client.get("/api/state").get_json()["settings"]["sleep_target"] == 8.5


def test_pwa_surfaces(client):
    assert client.get("/sw.js").status_code == 200
    assert b"manifest.webmanifest" in client.get("/").data
    assert client.get("/static/manifest.webmanifest").status_code == 200
    assert client.get("/static/icon.svg").status_code == 200


def test_corrupt_file_recovery(client, tmp_path):
    (tmp_path / "nutrition_data.json").write_text("{not json")
    state = client.get("/api/state").get_json()
    assert "backed it up" in (state["recovery_note"] or "")
    assert (tmp_path / "nutrition_data.json.corrupt").exists()


def test_legacy_v1_data_still_loads(client):
    seed({
        "profile": {"name": "", "weight": 0, "goal_weight": 0,
                    "daily_protein_g": 150, "daily_calories": 2000},
        "meals": [{"date": date.today().isoformat(), "time": "12:00",
                   "name": "Legacy meal", "protein": 40, "calories": 500, "notes": ""}],
        "workouts": [], "supplements": [],
    })
    state = client.get("/api/state").get_json()
    totals = state["stats"]["today"]["totals"]
    assert totals["protein"] == 40 and totals["carbs"] == 0


def test_csv_export(client):
    client.post("/api/meals", json={"name": "Rice", "protein": 5, "calories": 200})
    res = client.get("/api/export/meals.csv")
    assert res.status_code == 200
    assert b"Rice" in res.data
    assert client.get("/api/export/nope.csv").status_code == 404
