#!/usr/bin/env bash
# Golden Nutrition AI statusline: branch · today's protein/calories · AI backend
cd "$(dirname "$0")/.." 2>/dev/null

branch=$(git branch --show-current 2>/dev/null || echo "?")

read -r protein cals < <(python3 - <<'PY' 2>/dev/null || echo "0 0"
import json, datetime
try:
    d = json.load(open("nutrition_data.json"))
    t = datetime.date.today().isoformat()
    meals = [m for m in d.get("meals", []) if m.get("date") == t]
    print(sum(m.get("protein", 0) for m in meals), sum(m.get("calories", 0) for m in meals))
except Exception:
    print(0, 0)
PY
)

ai="api"
command -v claude >/dev/null 2>&1 && ai="sub"

printf '🏋️ GNA · %s · %sg P / %s cal today · ai:%s' "$branch" "$protein" "$cals" "$ai"
