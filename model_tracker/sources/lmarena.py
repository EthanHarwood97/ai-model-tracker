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


def _parse(text, seen):
    text = text.replace(r"\"", '"')
    rows = []
    for match in re.finditer(r'"entries":\s*\[', text):
        arr_text = _bracket_span(text, match.end() - 1)
        if arr_text is None:
            continue
        try:
            entries = json.loads(arr_text)
        except Exception:
            continue
        ctx = text[max(0, match.start() - 500): match.start()]
        arena_match = re.search(r'"arenaSlug":"([^"]+)"', ctx)
        board_match = re.search(r'"leaderboardSlug":"([^"]+)"', ctx)
        arena = arena_match.group(1) if arena_match else "unknown"
        board = board_match.group(1) if board_match else "unknown"
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            model_key = entry.get("modelKey") or entry.get("modelDisplayName")
            key = (arena, board, model_key)
            if key in seen:
                continue
            seen.add(key)
            rating = entry.get("rating")
            if rating is None:
                continue
            rows.append({
                "kind": f"arena_{arena}_{board}",
                "name": entry.get("modelDisplayName") or model_key,
                "slug": None,
                "score": round(rating, 2),
                "extra": {
                    "model_key": entry.get("modelKey"),
                    "arena": arena,
                    "leaderboard": board,
                    "organization": entry.get("modelOrganization"),
                    "votes": entry.get("votes"),
                    "rank": entry.get("rank"),
                    "ci": [entry.get("ratingLower"), entry.get("ratingUpper")],
                },
            })
    return rows


def fetch(f):
    rows = []
    seen = set()
    urls = (
        "https://arena.ai/leaderboard",
        # The frontend board is a separate route and is the most relevant
        # visual signal for the UI-coder recommendation.
        "https://arena.ai/leaderboard/code/webdev/frontend",
    )
    for url in urls:
        try:
            response = f.get(url, ttl=43200)
            rows.extend(_parse(response.text, seen))
        except Exception:
            if url.endswith("/leaderboard"):
                raise
    return rows
