import json
import re


def _bracket_span(text, start):
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]
        i += 1
    return None


def fetch(f):
    r = f.get("https://lmarena.ai/leaderboard")
    text = r.text.replace(r"\"", '"')
    rows = []
    seen = set()
    for m in re.finditer(r'"entries":\s*\[', text):
        arr_text = _bracket_span(text, m.end() - 1)
        if arr_text is None:
            continue
        try:
            entries = json.loads(arr_text)
        except Exception:
            continue
        ctx = text[max(0, m.start() - 500): m.start()]
        am = re.search(r'"arenaSlug":"([^"]+)"', ctx)
        lm = re.search(r'"leaderboardSlug":"([^"]+)"', ctx)
        arena = am.group(1) if am else "unknown"
        board = lm.group(1) if lm else "unknown"
        for e in entries:
            if not isinstance(e, dict):
                continue
            key = (arena, board, e.get("modelKey") or e.get("modelDisplayName"))
            if key in seen:
                continue
            seen.add(key)
            rating = e.get("rating")
            if rating is None:
                continue
            rows.append({
                "kind": f"arena_{arena}_{board}",
                "name": e.get("modelDisplayName") or e.get("modelKey"),
                "slug": None,
                "score": round(rating, 2),
                "extra": {
                    "model_key": e.get("modelKey"),
                    "arena": arena,
                    "leaderboard": board,
                    "organization": e.get("modelOrganization"),
                    "votes": e.get("votes"),
                    "rank": e.get("rank"),
                    "ci": [e.get("ratingLower"), e.get("ratingUpper")],
                },
            })
    return rows
