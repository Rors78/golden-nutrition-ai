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
        {"name": "Creatine Monohydrate", "time": "Morning"}]


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
