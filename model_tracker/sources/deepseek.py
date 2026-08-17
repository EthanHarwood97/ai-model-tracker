import re
from html import unescape

PAGE = "https://api-docs.deepseek.com/quick_start/pricing"

MODEL_VERSIONS = {
    "deepseek/deepseek-v4-flash-0731": ("flash", "DeepSeek-V4-Flash-0731"),
    "deepseek/deepseek-v4-pro-0813": ("pro", "DeepSeek-V4-Pro-0813"),
}

_OFFPEAK = "off_peak"
_PEAK = "peak"


def _usd(cell):
    m = re.search(r"\$?(\d+(?:\.\d+)?)", cell)
    return round(float(m.group(1)), 4) if m else None


def _parse_table(html):
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"\s+", " ", text).strip()
    data = {}
    labels = {
        "cache_hit": r"1M\s+INPUT\s+TOKENS\s+\(\s*CACHE\s+HIT\s*\)",
        "cache_miss": r"1M\s+INPUT\s+TOKENS\s+\(\s*CACHE\s+MISS\s*\)",
        "output": r"1M\s+OUTPUT\s+TOKENS",
    }
    tiered_prices = r"OFF[\s-]+PEAK\s+\$([\d.]+)\s+\$([\d.]+)\s+PEAK\s+\$([\d.]+)\s+\$([\d.]+)"
    for metric, label in labels.items():
        match = re.search(rf"{label}\s+{tiered_prices}", text, re.I)
        if not match:
            continue
        data[metric] = {
            _OFFPEAK: (_usd(match.group(1)), _usd(match.group(2))),
            _PEAK: (_usd(match.group(3)), _usd(match.group(4))),
        }
    if set(data) != set(labels):
        raise ValueError("pricing table not found")
    return data


def fetch(f):
    r = f.get(PAGE, ttl=43200)
    data = _parse_table(r.text)
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
