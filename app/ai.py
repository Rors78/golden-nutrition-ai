"""Claude backends for the AI features.

Two backends, tried in order:
  1. Claude Code CLI (`claude -p`) — bills the user's Claude subscription
     (Pro/Max), no API credits needed. Preferred when installed.
  2. Anthropic API SDK — needs ANTHROPIC_API_KEY with a credit balance.
"""
import json
import os
import shutil
import subprocess
import tempfile

import anthropic

from .data import clean_num
from .supplement_kb import kb_for_prompt

CLAUDE_MODEL = "claude-opus-5"

NUTRITIONIST_PROMPT = (
    "You are a nutrition expert. The user describes food they ate in plain "
    "language. Break it into individual meals/items and estimate protein (g), "
    "calories, carbs (g), fat (g), and fiber (g) for each, assuming realistic "
    "typical portion sizes unless quantities are given. Round to sensible "
    "whole numbers."
)

COACH_PROMPT = (
    "You are Golden Nutrition AI, an expert fitness and nutrition coach for a "
    "dedicated lifter following a push/pull/legs program. Be direct, specific, "
    "and use the actual numbers from the data. Keep it under 400 words."
)

MEAL_SCHEMA = {
    "type": "object",
    "properties": {
        "meals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "protein": {"type": "integer"},
                    "calories": {"type": "integer"},
                    "carbs": {"type": "integer"},
                    "fat": {"type": "integer"},
                    "fiber": {"type": "integer"}
                },
                "required": ["name", "protein", "calories", "carbs", "fat", "fiber"],
                "additionalProperties": False
            }
        }
    },
    "required": ["meals"],
    "additionalProperties": False
}


class AIUnavailable(RuntimeError):
    """No working Claude backend on this machine."""


def cli_available():
    return shutil.which("claude") is not None


def backend_name():
    if cli_available():
        return "Claude Code (subscription)"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "Anthropic API"
    return None


def _run_cli(prompt, timeout=300):
    """One-shot headless Claude Code prompt on the user's subscription."""
    env = dict(os.environ)
    # Bill the subscription login, never a possibly-unfunded API key
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True, text=True, timeout=timeout, env=env,
        cwd=tempfile.gettempdir(),  # neutral cwd: no project context leaks in
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Claude Code CLI failed: {detail[:500] or 'unknown error'}")
    return result.stdout.strip()


def _extract_json(text):
    """Pull the first JSON object out of a model response (tolerates fences/prose)."""
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in the AI response")
    return json.loads(text[start:end + 1])


def _sdk_create(**kwargs):
    client = anthropic.Anthropic()
    try:
        return client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **kwargs,
        )
    except TypeError:
        return client.messages.create(**kwargs)


def parse_meals(description):
    """Plain-language meal description → list of normalized macro dicts."""
    if cli_available():
        prompt = (
            f"{NUTRITIONIST_PROMPT}\n\n"
            f"The user's description:\n{description}\n\n"
            "Respond with ONLY a JSON object — no markdown fences, no commentary — "
            "in exactly this shape:\n"
            '{"meals": [{"name": "...", "protein": 0, "calories": 0, '
            '"carbs": 0, "fat": 0, "fiber": 0}]}'
        )
        meals = _extract_json(_run_cli(prompt, timeout=240))["meals"]
    elif backend_name():
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=NUTRITIONIST_PROMPT,
            messages=[{"role": "user", "content": description}],
            output_config={"format": {"type": "json_schema", "schema": MEAL_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this description.")
        meals = json.loads(next(b.text for b in response.content if b.type == "text"))["meals"]
    else:
        raise AIUnavailable(
            "No Claude backend found. Install Claude Code and log in (uses your "
            "Claude subscription), or set ANTHROPIC_API_KEY."
        )

    cleaned = []
    for m in meals:
        if not str(m.get('name', '')).strip():
            continue
        cleaned.append({
            'name': str(m['name']).strip(),
            'protein': clean_num(m.get('protein')),
            'calories': clean_num(m.get('calories')),
            'carbs': clean_num(m.get('carbs')),
            'fat': clean_num(m.get('fat')),
            'fiber': clean_num(m.get('fiber')),
        })
    if not cleaned:
        raise RuntimeError("Claude couldn't identify any meals in that description.")
    return cleaned


DEALS_PROMPT = (
    "You are a savvy shopping assistant for a lifter buying fitness food and "
    "supplements. Search the web for CURRENT deals, discounts, and best prices "
    "on the requested items. Prefer well-known retailers. Include the price you "
    "found and where. If a location or preferred store is given, prioritize it."
)


def find_deals(items, location=""):
    """Web-search current deals on food/supplements. Returns a list of deal dicts."""
    ask = (
        f"{DEALS_PROMPT}\n\n"
        f"Items to find deals on: {items}\n"
        + (f"Shopper location / preferred stores: {location}\n" if location.strip() else "")
        + "\nSearch the web, then respond with ONLY a JSON object — no markdown "
        "fences, no commentary — in exactly this shape:\n"
        '{"deals": [{"item": "...", "store": "...", "price": "...", '
        '"deal": "one-line description of the offer", "url": "..."}]}\n'
        "Give up to 8 deals, best value first. If you can't verify a price, skip it."
    )
    if cli_available():
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        result = subprocess.run(
            ["claude", "-p", ask, "--output-format", "text",
             "--allowedTools", "WebSearch,WebFetch"],
            capture_output=True, text=True, timeout=420, env=env,
            cwd=tempfile.gettempdir(),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Claude Code CLI failed: {detail[:500] or 'unknown error'}")
        deals = _extract_json(result.stdout.strip()).get("deals", [])
    elif backend_name():
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=DEALS_PROMPT,
            messages=[{"role": "user", "content": ask}],
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this request.")
        text = " ".join(b.text for b in response.content if b.type == "text")
        deals = _extract_json(text).get("deals", [])
    else:
        raise AIUnavailable(
            "No Claude backend found. Install Claude Code and log in (uses your "
            "Claude subscription), or set ANTHROPIC_API_KEY."
        )

    cleaned = []
    for d in deals:
        if not str(d.get('item', '')).strip():
            continue
        cleaned.append({
            'item': str(d.get('item', '')).strip(),
            'store': str(d.get('store', '')).strip(),
            'price': str(d.get('price', '')).strip(),
            'deal': str(d.get('deal', '')).strip(),
            'url': str(d.get('url', '')).strip(),
        })
    if not cleaned:
        raise RuntimeError("No verifiable deals came back — try naming the items more specifically.")
    return cleaned


SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "items": {"type": "string"},
                    "protein": {"type": "integer"},
                    "calories": {"type": "integer"},
                    "carbs": {"type": "integer"},
                    "fat": {"type": "integer"},
                    "fiber": {"type": "integer"},
                    "why": {"type": "string"}
                },
                "required": ["name", "items", "protein", "calories",
                             "carbs", "fat", "fiber", "why"],
                "additionalProperties": False
            }
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False
}


def suggest_meals(profile, persona, context):
    """Suggest the next meals to eat, fitted to what's left of today's macros."""
    ask = (
        "What should I eat next?\n\n"
        f"My profile: {json.dumps(profile)}\n"
        f"Today so far and what's left of my goals: {context}\n\n"
        "Suggest exactly 3 realistic options for my NEXT meal or snack — quick to "
        "prepare, matching YOUR nutrition philosophy, sized so the rest of today's "
        "remaining protein and calories work out. Vary them against what I've "
        "already eaten today and my recent regulars. For each: a short name, the "
        "actual items/portions, estimated protein/calories/carbs/fat/fiber, and one "
        "line on why it fits right now (tie it to my remaining numbers)."
    )
    shape = (
        "Respond with ONLY a JSON object — no markdown fences, no commentary — in exactly "
        'this shape:\n{"suggestions": [{"name": "...", "items": "...", "protein": 0, '
        '"calories": 0, "carbs": 0, "fat": 0, "fiber": 0, "why": "..."}]}'
    )
    if cli_available():
        raw = _extract_json(_run_cli(f"{persona}\n\n{ask}\n{shape}", timeout=240))
    elif backend_name():
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=persona,
            messages=[{"role": "user", "content": ask}],
            output_config={"format": {"type": "json_schema", "schema": SUGGEST_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this request.")
        raw = json.loads(next(b.text for b in response.content if b.type == "text"))
    else:
        raise AIUnavailable(
            "No Claude backend found. Install Claude Code and log in (uses your "
            "Claude subscription), or set ANTHROPIC_API_KEY."
        )

    cleaned = []
    for s in raw.get("suggestions", []):
        if not str(s.get('name', '')).strip():
            continue
        cleaned.append({
            'name': str(s['name']).strip(),
            'items': str(s.get('items', '')).strip(),
            'protein': clean_num(s.get('protein')),
            'calories': clean_num(s.get('calories')),
            'carbs': clean_num(s.get('carbs')),
            'fat': clean_num(s.get('fat')),
            'fiber': clean_num(s.get('fiber')),
            'why': str(s.get('why', '')).strip(),
        })
    if not cleaned:
        raise RuntimeError("No suggestions came back — try again.")
    return cleaned


SUPP_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "dose": {"type": "string"},
                    "timing": {"type": "string"},
                    "priority": {"type": "string", "enum": ["essential", "beneficial", "optional"]},
                    "why": {"type": "string"}
                },
                "required": ["name", "dose", "timing", "priority", "why"],
                "additionalProperties": False
            }
        },
        "skip": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "why": {"type": "string"}
                },
                "required": ["name", "why"],
                "additionalProperties": False
            }
        },
        "coach_note": {"type": "string"},
        "safety_note": {"type": "string"}
    },
    "required": ["recommendations", "skip", "coach_note", "safety_note"],
    "additionalProperties": False
}


def supplement_advice(profile, persona, context):
    """Personalized supplement stack: profile factors + logged history + coach stance."""
    ask = (
        "Recommend my optimal supplement stack.\n\n"
        f"My profile: {json.dumps(profile)}\n"
        f"My current stack, adherence, and recent training/diet data: {context}\n\n"
        "GROUND every recommendation in this evidence table (verdicts: PROVEN = the real "
        "ones; SOLID = worth it for the right training; SITUATIONAL = only if the user "
        "specifically needs it; WEAK = thin evidence; GARBAGE = marketing in a tub). "
        "Do not recommend anything the table grades WEAK or GARBAGE unless you explain "
        "the narrow exception, and if the user's CURRENT stack contains WEAK or GARBAGE "
        "items, say so plainly in your voice — people deserve to know what is a true "
        "supplement and what is garbage:\n"
        f"{kb_for_prompt()}\n\n"
        "Weigh ALL the factors: age (e.g., vitamin D and creatine matter more with age; "
        "40+ may benefit from joint support), sex (e.g., iron considerations for women, "
        "typically not for men), body weight and goal direction (cutting vs gaining), "
        "training volume and type from my actual logs, diet gaps visible in my macro "
        "history (low fiber, protein shortfall), my health notes, and YOUR supplement "
        "philosophy — if your stance is minimalist, recommend few things and say why "
        "that's a feature. If age or sex are missing from my profile, say so in the "
        "coach_note and generalize sensibly.\n\n"
        "Return:\n"
        "- recommendations: each with name, specific dose, timing, priority "
        "(essential = clearly worth it for me; beneficial = solid support; optional = "
        "nice-to-have), and why — tied to MY numbers and factors, not generic blurbs\n"
        "- skip: supplements I might expect that YOU would skip, with the honest reason\n"
        "- coach_note: one or two lines in your voice\n"
        "- safety_note: interactions and medical-check reminders relevant to my profile\n"
    )
    shape = (
        "Respond with ONLY a JSON object — no markdown fences, no commentary — in exactly "
        'this shape:\n{"recommendations": [{"name": "...", "dose": "...", "timing": "...", '
        '"priority": "essential|beneficial|optional", "why": "..."}], '
        '"skip": [{"name": "...", "why": "..."}], "coach_note": "...", "safety_note": "..."}'
    )
    if cli_available():
        advice = _extract_json(_run_cli(f"{persona}\n\n{ask}\n{shape}", timeout=300))
    elif backend_name():
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=persona,
            messages=[{"role": "user", "content": ask}],
            output_config={"format": {"type": "json_schema", "schema": SUPP_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this request.")
        advice = json.loads(next(b.text for b in response.content if b.type == "text"))
    else:
        raise AIUnavailable(
            "No Claude backend found. Install Claude Code and log in (uses your "
            "Claude subscription), or set ANTHROPIC_API_KEY."
        )

    if not advice.get("recommendations"):
        raise RuntimeError("No recommendations came back — try again.")
    valid = {"essential", "beneficial", "optional"}
    for r in advice["recommendations"]:
        if r.get("priority") not in valid:
            r["priority"] = "optional"
    advice.setdefault("skip", [])
    return advice


def daily_briefing(profile, persona, context):
    """A short morning briefing in the coach's voice: plan, focus, one nudge."""
    ask = (
        "Good morning, coach. Give me my daily briefing.\n\n"
        f"My profile: {json.dumps(profile)}\n"
        f"Today's picture: {context}\n\n"
        "In your voice, in UNDER 120 words of plain text (no markdown headers): "
        "1) today's training in one line (from the plan if there is one, or your call), "
        "2) the nutrition focus with actual numbers, "
        "3) one specific nudge based on my recent data (vitals, adherence, weigh-ins). "
        "End with one short line of your signature energy."
    )
    if cli_available():
        return _run_cli(f"{persona}\n\n{ask}", timeout=240)
    if backend_name():
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=8000,
            system=persona,
            messages=[{"role": "user", "content": ask}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this request.")
        return next(b.text for b in response.content if b.type == "text")
    raise AIUnavailable(
        "No Claude backend found. Install Claude Code and log in (uses your "
        "Claude subscription), or set ANTHROPIC_API_KEY."
    )


def parse_meal_photo(image_path):
    """Estimate macros from a photo of the plate. CLI path uses Claude Code's
    vision via the Read tool; SDK path sends the image as a content block."""
    if cli_available():
        prompt = (
            f"Read the meal photo at {image_path} and act as a nutrition expert: "
            "identify the foods and estimate realistic portions from the visual. "
            f"{NUTRITIONIST_PROMPT}\n\n"
            "Respond with ONLY a JSON object — no markdown fences, no commentary — "
            "in exactly this shape:\n"
            '{"meals": [{"name": "...", "protein": 0, "calories": 0, '
            '"carbs": 0, "fat": 0, "fiber": 0}]}'
        )
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text",
             "--allowedTools", "Read"],
            capture_output=True, text=True, timeout=300, env=env,
            cwd=os.path.dirname(image_path) or tempfile.gettempdir(),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Claude Code CLI failed: {detail[:500] or 'unknown error'}")
        meals = _extract_json(result.stdout.strip())["meals"]
    elif backend_name():
        import base64
        with open(image_path, 'rb') as f:
            b64 = base64.standard_b64encode(f.read()).decode()
        media = 'image/png' if image_path.lower().endswith('.png') else 'image/jpeg'
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=NUTRITIONIST_PROMPT,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": media, "data": b64}},
                {"type": "text", "text": "Identify the foods in this photo and estimate the macros."},
            ]}],
            output_config={"format": {"type": "json_schema", "schema": MEAL_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this photo.")
        meals = json.loads(next(b.text for b in response.content if b.type == "text"))["meals"]
    else:
        raise AIUnavailable(
            "No Claude backend found. Install Claude Code and log in (uses your "
            "Claude subscription), or set ANTHROPIC_API_KEY."
        )

    cleaned = []
    for m in meals:
        if not str(m.get('name', '')).strip():
            continue
        cleaned.append({
            'name': str(m['name']).strip(),
            'protein': clean_num(m.get('protein')),
            'calories': clean_num(m.get('calories')),
            'carbs': clean_num(m.get('carbs')),
            'fat': clean_num(m.get('fat')),
            'fiber': clean_num(m.get('fiber')),
        })
    if not cleaned:
        raise RuntimeError("Couldn't identify any food in that photo — try a clearer shot.")
    return cleaned


APOTHECARY_PROMPT = (
    "You are the Apothecary — a careful, warm librarian of traditional remedies "
    "backed by modern evidence. You answer ONLY from the remedy entries provided; "
    "if the entries don't cover the question, say so plainly rather than "
    "improvising. Hard rules: natural remedies are COMPLEMENTARY to medical care, "
    "never a replacement — for serious conditions (cancer, heart disease, "
    "diabetes, infections, mental-health crises) say clearly that medical care "
    "comes first and these are supportive at best. Never claim cures. Surface "
    "every relevant drug interaction and safety warning from the entries, "
    "especially any that touch the user's stated health notes or medications. "
    "Mention the evidence grade honestly (5 = strongest). End every answer with "
    "one line advising a conversation with a doctor or pharmacist before starting "
    "anything new."
)


def remedy_answer(profile, question, matches):
    """Answer a remedies question grounded strictly in the matched KB entries."""
    ask = (
        f"My profile (age/sex/health notes matter for interactions): {json.dumps(profile)}\n\n"
        f"My question: {question}\n\n"
        f"The only remedy entries you may draw on:\n{json.dumps(matches, indent=1)}\n\n"
        "Answer in under 250 words of plain text (no markdown headers). Recommend at "
        "most 3 options, best evidence first, each with how to use it and its key "
        "caution. Flag anything that conflicts with my profile notes."
    )
    if cli_available():
        return _run_cli(f"{APOTHECARY_PROMPT}\n\n{ask}", timeout=240)
    if backend_name():
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=8000,
            system=APOTHECARY_PROMPT,
            messages=[{"role": "user", "content": ask}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this request.")
        return next(b.text for b in response.content if b.type == "text")
    raise AIUnavailable(
        "No Claude backend found. Install Claude Code and log in (uses your "
        "Claude subscription), or set ANTHROPIC_API_KEY."
    )


VOICE_PROMPT = (
    "You route voice commands for a fitness tracking app. Given a transcript, "
    "decide the single action and extract its fields. Actions:\n"
    "- meal: the user says food they ate → description = the food text\n"
    "- weight: a body weigh-in → pounds (number)\n"
    "- supplement: they took a supplement → name, time (Morning/Afternoon/Evening/"
    "Pre-Workout/Post-Workout — infer from context, default Morning)\n"
    "- unknown: anything else → reason (one short line)\n"
)


def route_voice(transcript):
    """Voice transcript → {action, ...fields}. Small, fast, structured."""
    shape = (
        "Respond with ONLY a JSON object — no fences, no commentary:\n"
        '{"action": "meal|weight|supplement|unknown", "description": "...", '
        '"pounds": 0, "name": "...", "time": "...", "reason": "..."}\n'
        "Include only the fields relevant to the action."
    )
    ask = f"{VOICE_PROMPT}\nTranscript: \"{transcript}\"\n\n{shape}"
    if cli_available():
        return _extract_json(_run_cli(ask, timeout=120))
    if backend_name():
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            system=VOICE_PROMPT,
            messages=[{"role": "user", "content": f'Transcript: "{transcript}"\n\n{shape}'}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this request.")
        return _extract_json(next(b.text for b in response.content if b.type == "text"))
    raise AIUnavailable(
        "No Claude backend found. Install Claude Code and log in (uses your "
        "Claude subscription), or set ANTHROPIC_API_KEY."
    )


def coaching_summary(week_data, persona=None):
    """Weekly coaching write-up (markdown) from the last 7 days of data.

    `persona` is a system-prompt fragment (see coaches.persona_prompt) that
    puts the review in the selected coach's voice and philosophy.
    """
    system = persona or COACH_PROMPT
    user_content = (
        "Here is my last 7 days of tracking data as JSON:\n\n"
        f"{json.dumps(week_data, indent=2)}\n\n"
        "Give me a weekly coaching summary in markdown, in your coaching voice, with "
        "three sections: **What went well**, **What to fix**, and **The one change "
        "for next week** (the single highest-impact adjustment). Keep it under 400 "
        "words and use the actual numbers from the data."
    )
    if cli_available():
        return _run_cli(f"{system}\n\n{user_content}", timeout=300)
    if backend_name():
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this request.")
        return next(b.text for b in response.content if b.type == "text")
    raise AIUnavailable(
        "No Claude backend found. Install Claude Code and log in (uses your "
        "Claude subscription), or set ANTHROPIC_API_KEY."
    )


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "week": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day": {"type": "string"},
                    "title": {"type": "string"},
                    "focus": {"type": "string"},
                    "details": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["day", "title", "focus", "details"],
                "additionalProperties": False
            }
        },
        "meals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "meal": {"type": "string"},
                    "items": {"type": "string"},
                    "protein": {"type": "integer"},
                    "calories": {"type": "integer"}
                },
                "required": ["meal", "items", "protein", "calories"],
                "additionalProperties": False
            }
        },
        "supplements": {"type": "array", "items": {"type": "string"}},
        "coach_note": {"type": "string"}
    },
    "required": ["week", "meals", "supplements", "coach_note"],
    "additionalProperties": False
}


def weekly_plan(profile, persona, context=""):
    """Generate a 7-day plan (workouts, a sample meal day, supplements) in the
    selected coach's style. Returns the parsed plan dict."""
    ask = (
        f"Build my training week.\n\n"
        f"My profile: {json.dumps(profile)}\n"
        + (f"Recent context: {context}\n" if context else "")
        + "\nCreate:\n"
        "1. A 7-day week (include rest/active-recovery days where your philosophy calls "
        "for them): for each day give a short title, the focus, and 3-6 concrete detail "
        "lines (exercises with sets×reps, or activity with duration/intensity).\n"
        "2. One sample day of meals (4-6 meals) matching your nutrition philosophy AND "
        "my daily protein/calorie goals — each with items, protein grams, calories.\n"
        "3. Your supplement recommendations (respect your stance — fewer is fine).\n"
        "4. A one-or-two-sentence coach_note in your voice.\n"
    )
    shape = (
        "Respond with ONLY a JSON object — no markdown fences, no commentary — in exactly "
        'this shape:\n{"week": [{"day": "Monday", "title": "...", "focus": "...", '
        '"details": ["..."]}], "meals": [{"meal": "Breakfast", "items": "...", '
        '"protein": 0, "calories": 0}], "supplements": ["..."], "coach_note": "..."}'
    )
    if cli_available():
        plan = _extract_json(_run_cli(f"{persona}\n\n{ask}\n{shape}", timeout=420))
    elif backend_name():
        response = _sdk_create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=persona,
            messages=[{"role": "user", "content": ask}],
            output_config={"format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to process this request.")
        plan = json.loads(next(b.text for b in response.content if b.type == "text"))
    else:
        raise AIUnavailable(
            "No Claude backend found. Install Claude Code and log in (uses your "
            "Claude subscription), or set ANTHROPIC_API_KEY."
        )

    if not plan.get("week"):
        raise RuntimeError("The plan came back empty — try again.")
    return plan
