import statistics

from .normalize import canon, plain_key, slug_for_row

SOURCE_CATEGORIES = {
    "aa_coding": "coding_agent",
    "aa_models": "intelligence",
    "lmarena": "human_pref",
    "livebench": "code_correctness",
    "swebench": "code_correctness",
    "aider": "code_correctness",
    "evalplus": "code_correctness",
    "hf_openllm": "intelligence",
    "tbench": "agentic",
    "deepswe": "agentic",
    "scale_seal": "agentic",
    "gorilla": "tool_use",
    "openrouter": "market",
    "aa_changelog": "signal",
}

KIND_OVERRIDES = {
    "livebench_reasoning": "intelligence",
}


def _kind_category(source, kind):
    if kind in KIND_OVERRIDES:
        return KIND_OVERRIDES[kind]
    return SOURCE_CATEGORIES.get(source, "misc")


def normalize_within(rows, mode="minmax"):
    vals = [(i, r) for i, r in enumerate(rows) if r.get("score") is not None]
    if len(vals) < 2:
        for i, r in vals:
            r["score_norm"] = 50.0
        return
    if mode == "percentile":
        order = sorted(vals, key=lambda t: t[1]["score"])
        n = len(order)
        for rank, (_, r) in enumerate(order):
            r["score_norm"] = round(rank / (n - 1) * 100, 2)
        return
    scores = [r["score"] for _, r in vals]
    mn, mx = min(scores), max(scores)
    for _, r in vals:
        r["score_norm"] = round(100 * (r["score"] - mn) / (mx - mn), 2) if mx > mn else 50.0


def build_components(source_rows_by_source, cfg):
    norm_mode = cfg.get("normalization", {}).get("mode", "minmax")
    comps = {}
    for source, rows in source_rows_by_source.items():
        bucket = {}
        for r in rows:
            bucket.setdefault(r.get("kind", "generic"), []).append(r)
        for kind, group in bucket.items():
            normalize_within(group, mode=norm_mode)
            for r in group:
                if r.get("score_norm") is None:
                    continue
                key = plain_key(slug_for_row(r))
                if not key:
                    continue
                node = comps.setdefault(key, {})
                cat = _kind_category(source, kind)
                entry = {
                    "source": source,
                    "kind": kind,
                    "name": r["name"],
                    "norm": r["score_norm"],
                    "raw": r["score"],
                }
                node.setdefault(cat, []).append(entry)
    return comps


def _band(meta, w_eff, coding_band, cat_vals):
    dispersion = statistics.pstdev(cat_vals) if len(cat_vals) > 1 else 0.0
    band = max(0.02, 0.5 * dispersion)
    if coding_band:
        band = max(band, coding_band * w_eff)
    return band


def compute_entities(coding_rows, model_rows, est_rows, pairs_attach, comps, cfg):
    weights = cfg["weights"]
    present_cats = {k: v for k, v in weights.items() if v > 0}
    entities = []

    for c in coding_rows:
        attach = pairs_attach.get(c["slug"], {})
        extra = c.get("extra") or {}
        plain = canon(extra.get("model")) or plain_key(c["slug"])
        ent = {
            "slug": c["slug"],
            "plain": plain,
            "name": c["name"],
            "harness": extra.get("harness"),
            "effort": extra.get("effort"),
            "measured": True,
            "coding_index": c["score"],
            "cost_task": extra.get("cost_usd"),
            "wall_time_s": extra.get("wall_time_s"),
            "intelligence": attach.get("intelligence"),
            "price_mtok": attach.get("price_mtok"),
            "model_name": attach.get("model_name"),
            "context_window": attach.get("context_window"),
            "output_speed": attach.get("output_speed"),
            "mmmu_pro": attach.get("mmmu_pro"),
            "accepts_image": attach.get("accepts_image"),
            "est_band": None,
            "est_detail": None,
            "detail": {},
        }
        entities.append(ent)

    for e in est_rows:
        m = e["model_row"]
        ent = {
            "slug": e["slug"],
            "plain": canon(m["name"]) or e["slug"],
            "name": m["name"],
            "harness": None,
            "effort": None,
            "measured": False,
            "coding_index": e["score"],
            "cost_task": None,
            "wall_time_s": None,
            "intelligence": m["score"],
            "price_mtok": m["extra"].get("price_1m_blended"),
            "model_name": m["name"],
            "context_window": m["extra"].get("context_window"),
            "output_speed": m["extra"].get("output_speed"),
            "mmmu_pro": m["extra"].get("mmmu_pro"),
            "accepts_image": m["extra"].get("accepts_image"),
            "est_band": e["band"],
            "est_detail": e["detail"],
            "detail": e["detail"],
        }
        entities.append(ent)

    for ent in entities:
        node = comps.get(ent["plain"], {})
        cat_vals = {}
        detail = {}
        n_sources = 0
        src_set = set()
        if ent["coding_index"] is not None:
            cat_vals["coding_agent"] = ent["coding_index"]
            detail["coding_agent"] = {
                "value": ent["coding_index"],
                "estimated": not ent["measured"],
                "sources": [],
            }
        if ent["intelligence"] is not None:
            cat_vals["intelligence"] = ent["intelligence"]
            detail["intelligence"] = {
                "value": ent["intelligence"],
                "sources": [],
            }
        for cat, w in present_cats.items():
            if cat in ("coding_agent", "intelligence"):
                continue
            members = node.get(cat, [])
            if not members:
                continue
            vals = [m["norm"] for m in members]
            cat_vals[cat] = round(statistics.mean(vals), 2)
            detail[cat] = {"value": cat_vals[cat], "sources": [
                {"source": m["source"], "kind": m["kind"], "norm": m["norm"], "raw": m["raw"], "name": m["name"]}
                for m in sorted(members, key=lambda x: -x["norm"])
            ]}
            n_sources += len(members)
            src_set.update(m["source"] for m in members)
        w_sum = sum(weights[c] for c in cat_vals)
        meta = sum(weights[c] * cat_vals[c] for c in cat_vals) / w_sum if w_sum else None
        coding_band = None
        w_eff = 0.0
        if ent["measured"] is False and ent["est_band"]:
            coding_band = ent["est_band"]
            w_eff = weights["coding_agent"] / w_sum if w_sum else 1.0
        band = _band(meta, w_eff, coding_band, list(cat_vals.values())) if meta is not None else None
        ent["meta"] = round(meta, 2) if meta is not None else None
        ent["meta_min"] = round(meta - band, 2) if meta is not None and band is not None else None
        ent["meta_max"] = round(meta + band, 2) if meta is not None and band is not None else None
        ent["band"] = round(band, 3) if band is not None else None
        ent["n_sources"] = n_sources
        ent["source_names"] = sorted(src_set)
        ent["components"] = detail
        ent["categories"] = list(cat_vals.keys())
        vision_parts = []
        if ent["mmmu_pro"] is not None:
            vision_parts.append(ent["mmmu_pro"])
        vision_elos = [s["norm"] for s in node.get("human_pref", []) if str(s["kind"]).startswith("arena_vision")]
        if vision_elos:
            vision_parts.append(statistics.mean(vision_elos))
        ent["vision_mmmu"] = ent["mmmu_pro"]
        ent["vision_arena"] = round(statistics.mean(vision_elos), 1) if vision_elos else None
        ent["vision"] = round(statistics.mean(vision_parts), 1) if vision_parts else None

    return entities


def build_market(coding_rows, model_rows, est_rows, pairs_attach):
    price_by_plain = {}
    for m in model_rows:
        slug = m.get("slug")
        if not slug:
            continue
        p = m["extra"].get("price_1m_blended")
        if p is None:
            continue
        price_by_plain[slug] = p
    out = {}
    for c in coding_rows:
        key = plain_key(c["slug"])
        out[key] = price_by_plain.get(key)
    for e in est_rows:
        m = e["model_row"]
        if m.get("slug"):
            out.setdefault(m["slug"], m["extra"].get("price_1m_blended"))
    return out
