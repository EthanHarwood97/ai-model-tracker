import re

from .normalize import canon, plain_key

EFFORT_PATTERNS = {
    "max": re.compile(r"\(max\)|max effort", re.IGNORECASE),
    "xhigh": re.compile(r"\(xhigh\)|xhigh", re.IGNORECASE),
    "high": re.compile(r"\(high\)|high effort", re.IGNORECASE),
    "medium": re.compile(r"\(medium\)|medium effort", re.IGNORECASE),
    "low": re.compile(r"\(low\)|low effort", re.IGNORECASE),
    "none": re.compile(r"\(none\)", re.IGNORECASE),
}


def _model_key(m):
    return m["slug"] or canon(m["name"]) or m["name"].lower()


def _matches_stem(name, stem):
    return re.search(re.escape(stem), name, re.IGNORECASE) is not None


def match_coding_to_models(coding_rows, model_rows):
    by_slug = {}
    for m in model_rows:
        k = _model_key(m)
        prev = by_slug.get(k)
        if prev is None:
            by_slug[k] = m
            continue
        prev_est = prev["extra"].get("intelligence_estimated", False)
        m_est = m["extra"].get("intelligence_estimated", False)
        if m_est and not prev_est:
            continue
        if m["score"] > prev["score"]:
            by_slug[k] = m
    models = list(by_slug.values())

    pairs = []
    matched_slugs = set()
    for c in coding_rows:
        extra = c.get("extra") or {}
        stem = (extra.get("model") or c["name"]).strip()
        with_fallback = extra.get("with_fallback", False)
        effort = extra.get("effort")
        cands = [m for m in models if _matches_stem(m["name"], stem)]
        if not cands:
            continue
        if with_fallback:
            fb = [m for m in cands if "fallback" in m["name"].lower()]
            if fb:
                cands = fb
        else:
            cands = [m for m in cands if "fallback" not in m["name"].lower()]
        if effort and effort in EFFORT_PATTERNS:
            pat = EFFORT_PATTERNS[effort]
            ef = [m for m in cands if pat.search(m["name"])]
            if ef:
                cands = ef
            else:
                continue
        non_est = [m for m in cands if not m["extra"].get("intelligence_estimated")]
        if non_est:
            cands = non_est
        if not cands:
            continue
        cands.sort(key=lambda m: -m["score"])
        best = cands[0]
        matched_slugs.add(_model_key(best))
        pairs.append({"coding": c, "model": best})
    return pairs, matched_slugs


def regress(pairs):
    xs = [p["model"]["score"] for p in pairs]
    ys = [p["coding"]["score"] / 100.0 for p in pairs]
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    r = sxy / (sxx * syy) ** 0.5
    slope = sxy / sxx
    intercept = my - slope * mx
    return {"n": n, "r": r, "slope": slope, "intercept": intercept}


def _fam_adj(name, cfg):
    under = cfg.get("known_underperform", [])
    over = cfg.get("known_overperform", [])
    nl = name.lower()
    for f in under:
        if f.lower() in nl:
            return -0.10, "underperform-family"
    for f in over:
        if f.lower() in nl:
            return 0.06, "overperform-family"
    return 0.0, None


def _quirky(name):
    nl = name.lower()
    for f in ("deepseek", "glm", "kimi"):
        if f in nl:
            return True
    return False


def estimate_for_model(m, cfg, train_max_iq=None):
    est_cfg = cfg["est"]
    iq = m["score"]
    coding = m["extra"].get("coding_index")
    est1 = est_cfg["int_slope"] * iq + est_cfg["int_intercept"]
    est2 = None
    if coding is not None:
        est2 = est_cfg["code_slope"] * coding + est_cfg["code_intercept"]
    adj, adj_reason = _fam_adj(m["name"], cfg)
    cap = float(est_cfg.get("cap", 0.75))
    extrapolated = train_max_iq is not None and iq > train_max_iq
    est = min(cap, max(0.0, est1 + adj))
    detail = {
        "est_from_intelligence": round(est1, 4),
        "est_from_coding_index": round(est2, 4) if est2 is not None else None,
        "adjustment": adj,
        "adjustment_reason": adj_reason,
        "quirky_family": _quirky(m["name"]),
        "intelligence_index": iq,
        "coding_index": coding,
        "extrapolated": extrapolated,
        "capped": (est1 + adj) > cap,
    }
    if est2 is not None:
        detail["agrees"] = abs(est1 - est2) <= est_cfg["agree_threshold"]
    else:
        detail["agrees"] = None
    band = float(est_cfg["band"])
    if extrapolated:
        band = max(band, float(est_cfg.get("extrapolated_band", 0.10)))
    detail["band"] = band
    return {
        "slug": m["slug"] or canon(m["name"]),
        "name": m["name"],
        "score": round(est * 100, 2),
        "score_raw": est,
        "estimated": True,
        "band": band,
        "model_row": m,
        "detail": detail,
    }


def estimate_all(model_rows, matched_slugs, cfg, pairs=None):
    train_max_iq = None
    matched_canons = set()
    if pairs:
        iqs = [p["model"]["score"] for p in pairs]
        if iqs:
            train_max_iq = max(iqs)
        for p in pairs:
            c = canon(p["model"]["name"])
            if c:
                matched_canons.add(c)
    by_key = {}
    for m in model_rows:
        k = _model_key(m)
        prev = by_key.get(k)
        if prev is None or (
            not m["extra"].get("intelligence_estimated")
            and prev["extra"].get("intelligence_estimated")
        ) or (m["score"] > prev["score"]):
            by_key[k] = m
    out = []
    for k, m in by_key.items():
        if k in matched_slugs:
            continue
        if canon(m["name"]) in matched_canons:
            continue
        out.append(estimate_for_model(m, cfg, train_max_iq=train_max_iq))
    out.sort(key=lambda e: -e["score"])
    return out


def attach_model_to_coding(pairs):
    out = {}
    for p in pairs:
        c = p["coding"]
        m = p["model"]
        out[c["slug"]] = {
            "model_slug": m["slug"],
            "model_name": m["name"],
            "intelligence": m["score"],
            "intelligence_estimated": m["extra"].get("intelligence_estimated", False),
            "price_mtok": m["extra"].get("price_1m_blended"),
            "release_date": m["extra"].get("release_date"),
            "context_window": m["extra"].get("context_window"),
            "output_speed": m["extra"].get("output_speed"),
            "mmmu_pro": m["extra"].get("mmmu_pro"),
            "accepts_image": m["extra"].get("accepts_image"),
        }
    return out
