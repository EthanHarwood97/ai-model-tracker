import json
import re


def _unescape_jsonish(text):
    return text.replace(r"\"", '"').replace(r"\'", "'")


def _json_str(raw):
    try:
        return json.loads('"' + raw + '"')
    except Exception:
        return raw.replace("\\/", "/")


def _grab_num(window, key):
    m = re.search(r'"' + re.escape(key) + r'":\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', window)
    if not m:
        return None
    return float(m.group(1))


def _grab_bool(window, key):
    m = re.search(r'"' + re.escape(key) + r'":\s*(true|false)', window)
    if not m:
        return None
    return m.group(1) == "true"


def _grab_str(window, key):
    m = re.search(r'"' + re.escape(key) + r'":"((?:[^"\\]|\\.)*)"', window)
    if not m:
        return None
    return _json_str(m.group(1))


EFFORTS = ("max", "xhigh", "high", "medium", "low", "none")

_HARNESS_RE = re.compile(
    r"^(?P<harness>[A-Za-z0-9 .&+'-]+?) - (?P<rest>.+)$"
)
_EFFORT_RE = re.compile(
    r"\((?P<effort>max|xhigh|high|medium|low|none)\)\s*$", re.IGNORECASE
)
_FALLBACK_RE = re.compile(r"\(with fallback\)\s*$", re.IGNORECASE)


def parse_coding_label(label):
    info = {"label": label, "harness": None, "model": label, "effort": None, "with_fallback": False}
    m = _FALLBACK_RE.search(label)
    if m:
        info["with_fallback"] = True
        label = label[: m.start()].strip()
    m = _EFFORT_RE.search(label)
    if m:
        info["effort"] = m.group("effort").lower()
        label = label[: m.start()].strip()
    m = _HARNESS_RE.match(label)
    if m:
        info["harness"] = m.group("harness")
        info["model"] = m.group("rest").strip()
    return info


def scrape_coding(html):
    text = _unescape_jsonish(html)
    rows = []
    seen = set()
    for m in re.finditer(r'"displayLabel":"((?:[^"\\]|\\.)*)"', text):
        raw_label = _json_str(m.group(1))
        window = text[m.end(): m.end() + 6000]
        score = _grab_num(window, "indexScore")
        if score is None:
            continue
        if raw_label in seen:
            continue
        seen.add(raw_label)
        info = parse_coding_label(raw_label)
        cost = _grab_num(window, "costUsd")
        wall = _grab_num(window, "agentWallTimeSec")
        rows.append({
            "kind": "coding_index",
            "name": raw_label,
            "slug": _coding_slug(info),
            "score": round(score * 100, 4),
            "extra": {
                "harness": info["harness"],
                "model": info["model"],
                "effort": info["effort"],
                "with_fallback": info["with_fallback"],
                "index_raw": round(score, 4),
                "cost_usd": round(cost, 4) if cost is not None else None,
                "wall_time_s": round(wall, 1) if wall is not None else None,
            },
        })
    return rows


def _coding_slug(info):
    parts = [info["harness"] or "", info["model"] or ""]
    if info["effort"]:
        parts.append(info["effort"])
    if info["with_fallback"]:
        parts.append("with-fallback")
    slug = "-".join(p for p in parts if p).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or None


def _grab_round(window, key, digits):
    value = _grab_num(window, key)
    return round(value, digits) if value is not None else None


def scrape_models(html):
    text = _unescape_jsonish(html)
    rows = []
    seen = {}
    for m in re.finditer(r'"name":"((?:[^"\\]|\\.)*)"', text):
        name = _json_str(m.group(1))
        window = text[m.end(): m.end() + 3200]
        slug = _grab_str(window, "slug")
        iq = _grab_num(window, "intelligenceIndex")
        if slug is None or iq is None:
            continue
        key = (name, slug)
        if key in seen:
            continue
        seen[key] = True
        mmmu = _grab_num(window, "mmmuPro")
        rows.append({
            "kind": "intelligence",
            "name": name,
            "slug": slug,
            "score": round(iq, 4),
            "extra": {
                "intelligence_estimated": _grab_bool(window, "intelligenceIndexIsEstimated"),
                "coding_index": _grab_round(window, "codingIndex", 4),
                "price_1m_blended": _grab_round(window, "price1mBlended0To3To1", 4),
                "price_1m_input": _grab_round(window, "price1mInputTokens", 4),
                "price_1m_output": _grab_round(window, "price1mOutputTokens", 4),
                "release_date": _grab_str(window, "releaseDate"),
                "is_reasoning": _grab_bool(window, "isReasoning"),
                "deprecated": _grab_bool(window, "deprecated"),
                "context_window": _grab_num(window, "contextWindowTokens"),
                "output_speed": _grab_round(window, "medianOutputTokensPerSecond", 1),
                "time_to_first_answer": _grab_round(window, "medianTimeToFirstAnswerTokenSeconds", 2),
                "mmmu_pro": round(mmmu * 100, 2) if mmmu is not None else None,
                "accepts_image": _grab_bool(window, "inputModalityImage"),
            },
        })
    return rows


def scrape_changelog(html):
    entries = []
    seen = set()
    for m in re.finditer(r'<a[^>]*href="/articles/([^"]+)"[^>]*>([\s\S]*?)</a>', html):
        slug = m.group(1)
        block = m.group(2)
        if slug in seen:
            continue
        seen.add(slug)
        tm = re.search(r"<h3[^>]*>([\s\S]*?)</h3>", block)
        if not tm:
            continue
        title = re.sub(r"<[^>]+>", "", tm.group(1)).strip()
        if not title:
            continue
        dm = re.search(r"(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})", block)
        entries.append({"title": title, "date": dm.group(1) if dm else None, "slug": slug})
    return entries[:60]
