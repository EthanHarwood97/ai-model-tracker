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


def _identity_tokens(value):
    return {
        token for token in re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split()
        if len(token) > 1
    }


def _coding_points(value):
    """Return a coding score on the 0-100 scale without guessing its meaning."""
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= score <= 1:
        score *= 100
    return score if 0 <= score <= 100 else None


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
        stem_key = plain_key(canon(stem))
        exact = [m for m in models if plain_key(canon(m["name"])) == stem_key]
        if exact:
            cands = exact
        else:
            stem_tokens = _identity_tokens(stem)
            candidates = [
                m for m in models
                if stem_tokens and stem_tokens.issubset(_identity_tokens(m["name"]))
            ]
            if not candidates:
                continue
            overlap = [len(stem_tokens & _identity_tokens(m["name"])) for m in candidates]
            best_overlap = max(overlap)
            cands = [m for m, score in zip(candidates, overlap) if score == best_overlap]
        if not cands:
            continue
        if with_fallback:
            fb = [m for m in cands if "fallback" in m["name"].lower()]
            if not fb:
                continue
            cands = fb
        else:
            cands = [m for m in cands if "fallback" not in m["name"].lower()]
            if not cands:
                continue
        if effort and effort in EFFORT_PATTERNS:
            pat = EFFORT_PATTERNS[effort]
            ef = [m for m in cands if pat.search(m["name"])]
            if not ef:
                continue
            cands = ef
        non_est = [m for m in cands if not m["extra"].get("intelligence_estimated")]
        if non_est:
            cands = non_est
        if not cands:
            continue
        cands.sort(key=lambda m: -m["score"])
        if len(cands) > 1 and cands[0]["score"] == cands[1]["score"]:
            # Do not silently attach an arbitrary provider/version when the source is ambiguous.
            continue
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
    iq_val = m.get("score")
    iq = float(iq_val) if iq_val is not None else None
    coding = m["extra"].get("coding_index")
    coding_points = _coding_points(coding)
    est1 = est_cfg["int_slope"] * iq + est_cfg["int_intercept"] if iq is not None else None
    est2 = None
    if coding_points is not None:
        # The configured cross-check is trained on coding-index points, not a 0-1 fraction.
        est2 = est_cfg["code_slope"] * coding_points + est_cfg["code_intercept"]
    cap = float(est_cfg.get("cap", 0.75))
    if est_cfg.get("cap_points") is not None:
        cap = float(est_cfg["cap_points"]) / 100
    extrapolated = train_max_iq is not None and iq is not None and iq > train_max_iq
    cap_f = float(cap)
    band_points = float(est_cfg.get("band_points", est_cfg.get("band", 0.06) * 100))
    extrapolated_band_points = float(
        est_cfg.get("extrapolated_band_points", est_cfg.get("extrapolated_band", 0.10) * 100)
    )

    if coding_points is not None:
        # AA's model leaderboard coding index is observed evidence, but it is not an
        # AA Coding Agent measurement and must not enter the measured coding view.
        score_points = coding_points
        source = "aa_model_coding_index"
        measurement_type = "aa_model_index"
        estimated = False
        adjustment = 0.0
        adjustment_reason = None
        capped = False
        band = None
    elif est1 is not None:
        adjustment, adjustment_reason = _fam_adj(m["name"], cfg)
        raw_score = est1 + float(adjustment)
        capped = raw_score > cap_f
        score = min(cap_f, max(0.0, raw_score))
        score_points = score * 100
        source = "intelligence_regression"
        measurement_type = "predicted_coding_agent"
        estimated = True
        band = max(band_points, extrapolated_band_points) if extrapolated else band_points
    else:
        score_points = None
        source = "no_data"
        measurement_type = "unavailable"
        estimated = True
        adjustment = 0.0
        adjustment_reason = None
        capped = False
        band = None

    detail = {
        "est_from_intelligence": round(est1, 4) if est1 is not None else None,
        "est_from_coding_index": round(est2, 4) if est2 is not None else None,
        "adjustment": float(adjustment),
        "adjustment_reason": adjustment_reason,
        "quirky_family": _quirky(m["name"]),
        "intelligence_index": iq,
        "coding_index": coding_points,
        "measurement_type": measurement_type,
        "extrapolated": extrapolated,
        "capped": capped,
        "source": source,
        "band_points": band,
    }
    if est1 is not None and est2 is not None:
        detail["agrees"] = abs(est1 - est2) <= est_cfg["agree_threshold"]
    else:
        detail["agrees"] = None
    detail["band"] = band
    return {
        "slug": m["slug"] or canon(m["name"]),
        "name": m["name"],
        "score": round(score_points, 2) if score_points is not None else None,
        "score_raw": round(score_points / 100, 4) if score_points is not None else None,
        "estimated": estimated,
        "band": band,
        "measurement_type": measurement_type,
        "score_source": source,
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
            "deprecated": m["extra"].get("deprecated", False),
            "price_mtok": m["extra"].get("price_1m_blended"),
            "price_input": m["extra"].get("price_1m_input"),
            "price_output": m["extra"].get("price_1m_output"),
            "release_date": m["extra"].get("release_date"),
            "context_window": m["extra"].get("context_window"),
            "output_speed": m["extra"].get("output_speed"),
            "time_to_first_answer": m["extra"].get("time_to_first_answer"),
            "mmmu_pro": m["extra"].get("mmmu_pro"),
            "accepts_image": m["extra"].get("accepts_image"),
            "supports_tools": m["extra"].get("supports_tools"),
        }
    return out
