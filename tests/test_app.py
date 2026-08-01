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

    prog = state["stats"]["progression"]["Incline Dumbbell Press"]
    assert max(p["top"] for p in prog) == 75

    ins = state["stats"]["insights"]
    assert ins["avg_daily_protein"] == 45
    assert ins["verdict"]["level"] == "warn"  # 45g/day vs 150g goal

    assert state["stats"]["checklist"] == [{"name": "Creatine", "time": "Morning", "taken": False}]


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


def test_weight_replaces_same_day_and_syncs_profile(client):
    today = date.today().isoformat()
    client.post("/api/weights", json={"date": today, "weight": 201})
    client.post("/api/weights", json={"date": today, "weight": 200.5})
    state = client.get("/api/state").get_json()
    assert len(state["weights"]) == 1
    assert state["weights"][0]["weight"] == 200.5
    assert state["profile"]["weight"] == 200.5


def test_checklist_toggle(client):
    client.post("/api/schedule", json={"name": "Creatine", "time": "Morning"})
    r = client.post("/api/checklist/toggle", json={"name": "Creatine", "time": "Morning"})
    assert r.get_json()["taken"] is True
    assert client.get("/api/state").get_json()["stats"]["checklist"][0]["taken"] is True
    r = client.post("/api/checklist/toggle", json={"name": "Creatine", "time": "Morning"})
    assert r.get_json()["taken"] is False


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
        {"name": "Creatine Monohydrate", "time": "Morning"}]


def test_supplement_adherence(client):
    assert client.get("/api/state").get_json()["stats"]["adherence"] == {"has_schedule": False}
    client.post("/api/schedule", json={"name": "Creatine", "time": "Morning"})
    client.post("/api/checklist/toggle", json={"name": "Creatine", "time": "Morning"})
    adh = client.get("/api/state").get_json()["stats"]["adherence"]
    assert adh["has_schedule"] is True
    assert adh["slots"] == 7 and adh["taken"] == 1
    assert adh["pct"] == 14  # 1 of 7 daily slots this week


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
