import re

PAGE = "https://api-docs.deepseek.com/quick_start/pricing"

MODEL_VERSIONS = {
    "deepseek/deepseek-v4-flash-0731": ("flash", "DeepSeek-V4-Flash-0731"),
    "deepseek/deepseek-v4-pro-0813": ("pro", "DeepSeek-V4-Pro-0813"),
}

_OFFPEAK = "off_peak"
_PEAK = "peak"


def _usd(cell):
    m = re.search(r"\$(\d+(?:\.\d+)?)", cell)
    return round(float(m.group(1)), 4) if m else None


def _parse_table(html):
    table = next(
        (
            table
            for table in re.findall(r"<table\b[^>]*>.*?</table>", html, re.I | re.S)
            if re.search(r"1M\s+INPUT\s+TOKENS", table, re.I)
            and re.search(r"OFF-PEAK", table, re.I)
        ),
        None,
    )
    if table is None:
        raise ValueError("pricing table not found")
    data = {}
    current = None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.I | re.S):
        cells = [
            re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.I | re.S)
        ]
        if not cells:
            continue
        label_idx = next(
            (
                n
                for n, c in enumerate(cells)
                if re.search(r"TOKENS", c, re.I) and any("$" in x for x in cells)
            ),
            None,
        )
        if label_idx is not None:
            current = cells[label_idx]
            cells = cells[label_idx + 1:]
        if not current or not cells or cells[0].upper() not in ("OFF-PEAK", "PEAK"):
            continue
        tier = _OFFPEAK if cells[0].upper() == "OFF-PEAK" else _PEAK
        m = re.search(r"\((.*?)\)", current)
        metric = (m.group(1) if m else "output").lower().replace(" ", "_").replace("-", "_")
        data.setdefault(metric, {})[tier] = (_usd(cells[1]), _usd(cells[2]))
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
