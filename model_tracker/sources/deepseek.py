import re
from html import unescape

PAGE = "https://api-docs.deepseek.com/quick_start/pricing"

MODEL_VERSIONS = {
    "deepseek/deepseek-v4-flash-0731": ("flash", "DeepSeek-V4-Flash-0731"),
    "deepseek/deepseek-v4-pro-0813": ("pro", "DeepSeek-V4-Pro-0813"),
}

_OFFPEAK = "off_peak"
_PEAK = "peak"

_LABELS = {
    "cache_hit": r"1M\s+INPUT\s+TOKENS\s*\(\s*CACHE\s+HIT\s*\)",
    "cache_miss": r"1M\s+INPUT\s+TOKENS\s*\(\s*CACHE\s+MISS\s*\)",
    "output": r"1M\s+OUTPUT\s+TOKENS",
}

_PRICES = r"\$?\d+(?:\.\d+)?"


def _usd(cell):
    m = re.search(r"(\d+(?:\.\d+)?)", cell)
    return round(float(m.group(1)), 4) if m else None


def _tiered(text, label):
    patterns = [
        rf"{label}\s+OFF[\s-]+PEAK\s+({_PRICES})\s+({_PRICES})\s+PEAK\s+({_PRICES})\s+({_PRICES})",
        rf"{label}\s+OFF[\s-]+PEAK\s+({_PRICES})\s+({_PRICES})\s+({_PRICES})\s+({_PRICES})",
        rf"{label}\s+({_PRICES})\s+({_PRICES})\s+PEAK\s+({_PRICES})\s+({_PRICES})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return {
                _OFFPEAK: (_usd(m.group(1)), _usd(m.group(2))),
                _PEAK: (_usd(m.group(3)), _usd(m.group(4))),
            }
    m = re.search(rf"{label}\s+((?:{_PRICES}\s*)+)", text, re.I)
    if m:
        vals = re.findall(_PRICES, m.group(1))
        if len(vals) >= 4:
            return {
                _OFFPEAK: (_usd(vals[0]), _usd(vals[1])),
                _PEAK: (_usd(vals[2]), _usd(vals[3])),
            }
    return None


def _parse_table(html):
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()
    data = {}
    for metric, label in _LABELS.items():
        tiers = _tiered(text, label)
        if tiers:
            data[metric] = tiers
    if set(data) != set(_LABELS):
        raise ValueError("pricing table not found")
    return data


def fetch(f):
    data = None
    last_err = None
    snippet = ""
    attempts = [(43200, False, PAGE), (0, True, PAGE)]
    for n in range(1, 4):
        attempts.append((0, True, f"{PAGE}?v={n}"))
    for ttl, force, url in attempts:
        try:
            r = f.get(url, ttl=ttl, force=force)
            snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))[:160]
            data = _parse_table(r.text)
            break
        except Exception as e:
            last_err = e
    if not data:
        detail = "zh-CN variant served" if "缓存" in snippet or "百万tokens" in snippet else repr(snippet)
        raise ValueError(f"pricing table not found ({last_err}) [{detail}]")
    rows = []
    for or_id, (flavor, version) in MODEL_VERSIONS.items():
        idx = 0 if flavor == "flash" else 1
        extra = {
            "or_id": or_id,
            "version": version,
            "peak_hours_utc": "01:00-04:00, 06:00-10:00",
        }
        for metric, tiers in data.items():
            for tier in (_OFFPEAK, _PEAK):
                pair = tiers.get(tier)
                if not pair:
                    continue
                val = pair[idx]
                if val is not None:
                    extra[f"{metric}_{tier}"] = val
        off_in = extra.get("cache_miss_off_peak")
        off_out = extra.get("output_off_peak")
        blended = None
        if isinstance(off_in, (int, float)) and isinstance(off_out, (int, float)):
            blended = round((float(off_in) * 3 + float(off_out)) / 4, 4)
        rows.append({
            "kind": "market",
            "name": or_id,
            "slug": None,
            "score": blended,
            "extra": extra,
        })
    return rows
