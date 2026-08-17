import statistics
from collections import defaultdict

from .estimator import _coding_points
from .normalize import canon, plain_key, slug_for_row


# These lanes describe what a source actually measures. They are deliberately
# separate from the legacy meta categories so a benchmark cannot masquerade as
# an AA Coding Agent measurement.
SOURCE_CATEGORIES = {
    "aa_coding": "coding_agent",
    "aa_models": "intelligence",
    "lmarena": "human_pref",
    "livebench": "supporting",
    "swebench": "coding_support",
    "aider": "coding_support",
    "evalplus": "coding_support",
    "hf_openllm": "intelligence_support",
    "tbench": "agentic",
    "deepswe": "agentic",
    "scale_seal": "agentic",
    "gorilla": "tool_use",
    "openrouter": "market",
    "deepseek": "market",
    "aa_changelog": "signal",
}


LANE_TO_LEGACY_CATEGORY = {
    "coding_support": "code_correctness",
    "human_pref": "human_pref",
    "agentic": "agentic",
    "tool_use": "agentic",
    "reasoning": "intelligence",
    "intelligence_support": "intelligence",
}


def benchmark_spec(source, kind):
    """Return the evidence lane for one source row."""
    kind = str(kind or "generic")
    if source in ("openrouter", "deepseek") or source == "aa_changelog":
        return {"lane": None, "benchmark_id": f"{source}:{kind}"}
    if source == "aa_coding":
        return {"lane": "coding_agent", "benchmark_id": "aa_coding_agent"}
    if source == "aa_models":
        return {"lane": "intelligence", "benchmark_id": "aa_intelligence"}
    if source == "livebench":
        if kind == "livebench_global":
            return {"lane": None, "benchmark_id": "livebench_global"}
        if kind == "livebench_coding":
            return {"lane": "coding_support", "benchmark_id": "livebench_coding"}
        if kind == "livebench_agentic":
            return {"lane": "agentic", "benchmark_id": "livebench_agentic"}
        if kind == "livebench_reasoning":
            return {"lane": "reasoning", "benchmark_id": "livebench_reasoning"}
    if source == "lmarena":
        lower = kind.lower()
        if "frontend" in lower or "webdev" in lower:
            return {"lane": "visual_frontend", "benchmark_id": kind}
        if "vision" in lower:
            return {"lane": "vision", "benchmark_id": kind}
        return {"lane": "human_pref", "benchmark_id": kind}
    if source in ("swebench", "aider", "evalplus"):
        return {"lane": "coding_support", "benchmark_id": f"{source}:{kind}"}
    if source == "hf_openllm":
        return {"lane": "intelligence_support", "benchmark_id": f"{source}:{kind}"}
    if source == "tbench":
        return {"lane": "agentic", "benchmark_id": "terminal_bench"}
    if source == "deepswe":
        return {"lane": "agentic", "benchmark_id": "deepswe"}
    if source == "gorilla":
        return {"lane": "tool_use", "benchmark_id": "bfcl"}
    lane = SOURCE_CATEGORIES.get(source)
    return {"lane": lane if lane not in (None, "market", "signal", "supporting") else None,
            "benchmark_id": f"{source}:{kind}"}


def normalize_within(rows, mode="minmax", floor=0.0, ceiling=100.0):
    """Add a relative score without inventing evidence for singleton cohorts."""
    vals = [(i, r) for i, r in enumerate(rows) if r.get("score") is not None]
    for _, row in vals:
        row["score_norm"] = None
        row["normalization_status"] = "insufficient_cohort"
    if len(vals) < 2:
        return

    if mode == "percentile":
        ordered = sorted(vals, key=lambda item: item[1]["score"])
        rank_by_index = {}
        pos = 0
        while pos < len(ordered):
            end = pos + 1
            while end < len(ordered) and ordered[end][1]["score"] == ordered[pos][1]["score"]:
                end += 1
            average_rank = (pos + end - 1) / 2
            for index, _ in ordered[pos:end]:
                rank_by_index[index] = average_rank
            pos = end
        denominator = max(1, len(ordered) - 1)
        for index, row in vals:
            row["score_norm"] = round(
                floor + (rank_by_index[index] / denominator) * (ceiling - floor), 2
            )
            row["normalization_status"] = "relative_percentile"
        return

    scores = [r["score"] for _, r in vals]
    mn, mx = min(scores), max(scores)
    if mx == mn:
        midpoint = round((floor + ceiling) / 2, 2)
        for _, row in vals:
            row["score_norm"] = midpoint
            row["normalization_status"] = "no_variation"
        return
    for _, row in vals:
        row["score_norm"] = round(
            floor + (row["score"] - mn) / (mx - mn) * (ceiling - floor), 2
        )
        row["normalization_status"] = "relative_minmax"


def build_components(source_rows_by_source, cfg):
    norm_cfg = cfg.get("normalization", {})
    norm_mode = norm_cfg.get("mode", "minmax")
    floor = float(norm_cfg.get("minmax_floor", 0))
    ceiling = float(norm_cfg.get("minmax_ceiling", 100))
    comps = {}
    for source, rows in source_rows_by_source.items():
        bucket = defaultdict(list)
        for row in rows:
            bucket[row.get("kind", "generic")].append(row)
        for kind, group in bucket.items():
            spec = benchmark_spec(source, kind)
            if spec["lane"] is None:
                continue
            normalize_within(group, mode=norm_mode, floor=floor, ceiling=ceiling)
            for row in group:
                key = plain_key(slug_for_row(row))
                if not key:
                    continue
                extra = row.get("extra") or {}
                if not isinstance(extra, dict):
                    extra = {}
                entry = {
                    "source": source,
                    "kind": kind,
                    "lane": spec["lane"],
                    "benchmark_id": spec["benchmark_id"],
                    "name": row.get("name"),
                    "norm": row.get("score_norm"),
                    "raw": row.get("score"),
                    "normalization_status": row.get("normalization_status"),
                    "retrieved_at": extra.get("retrieved_at"),
                }
                node = comps.setdefault(key, {})
                node.setdefault(spec["lane"], []).append(entry)
    return comps


def _band(meta, w_eff, coding_band, cat_vals):
    dispersion = statistics.pstdev(cat_vals) if len(cat_vals) > 1 else 0.0
    band = max(1.0, 0.5 * dispersion)
    if coding_band:
        band = max(band, coding_band * w_eff)
    return band


def _aggregate_lane(entries):
    groups = defaultdict(list)
    for entry in entries:
        if isinstance(entry.get("norm"), (int, float)):
            groups[entry["benchmark_id"]].append(entry)
    values = {
        benchmark_id: round(statistics.mean(item["norm"] for item in members), 2)
        for benchmark_id, members in groups.items()
    }
    if not values:
        return None, [], []
    value = round(statistics.mean(values.values()), 2)
    return value, values, [entry for members in groups.values() for entry in members]


def _entity_base_detail(ent):
    detail = ent.get("detail")
    return detail if isinstance(detail, dict) else {}


def compute_entities(coding_rows, model_rows, est_rows, pairs_attach, comps, cfg):
    weights = {key: float(value) for key, value in cfg.get("weights", {}).items() if value > 0}
    entities = []

    for coding in coding_rows:
        attach = pairs_attach.get(coding["slug"], {})
        extra = coding.get("extra") or {}
        detail = {
            "source": "aa_coding",
            "benchmark_id": "aa_coding_agent",
            "measurement_type": "aa_coding_agent",
            "harness": extra.get("harness"),
            "effort": extra.get("effort"),
            "fallback": extra.get("with_fallback", False),
        }
        entities.append({
            "slug": coding["slug"],
            "plain": plain_key(canon(extra.get("model"))) or plain_key(coding["slug"]),
            "name": coding["name"],
            "harness": extra.get("harness"),
            "effort": extra.get("effort"),
            "measured": True,
            "measurement_type": "aa_coding_agent",
            "score_source": "aa_coding_agent",
            "coding_index": coding["score"],
            "aa_model_coding_index": None,
            "cost_task": extra.get("cost_usd"),
            "cost_basis": "benchmark_task" if extra.get("cost_usd") is not None else None,
            "wall_time_s": extra.get("wall_time_s"),
            "intelligence": attach.get("intelligence"),
            "intelligence_estimated": attach.get("intelligence_estimated"),
            "deprecated": attach.get("deprecated", False),
            "price_mtok": attach.get("price_mtok"),
            "price_input": attach.get("price_input"),
            "price_output": attach.get("price_output"),
            "price_source": None,
            "model_name": attach.get("model_name"),
            "provider_route_id": None,
            "context_window": attach.get("context_window"),
            "output_speed": attach.get("output_speed"),
            "time_to_first_answer": attach.get("time_to_first_answer"),
            "mmmu_pro": attach.get("mmmu_pro"),
            "accepts_image": attach.get("accepts_image"),
            "supports_tools": attach.get("supports_tools"),
            "est_band": None,
            "est_detail": None,
            "detail": detail,
        })

    for estimate in est_rows:
        model = estimate["model_row"]
        extra = model.get("extra") or {}
        detail = dict(estimate.get("detail") or {})
        measurement_type = estimate.get("measurement_type", detail.get("measurement_type", "unavailable"))
        entities.append({
            "slug": estimate["slug"],
            "plain": plain_key(canon(model["name"])) or estimate["slug"],
            "name": model["name"],
            "harness": None,
            "effort": None,
            "measured": False,
            "measurement_type": measurement_type,
            "score_source": estimate.get("score_source", detail.get("source")),
            "coding_index": estimate.get("score"),
            "aa_model_coding_index": _coding_points(extra.get("coding_index")),
            "cost_task": None,
            "cost_basis": None,
            "wall_time_s": None,
            "intelligence": model.get("score"),
            "intelligence_estimated": extra.get("intelligence_estimated"),
            "deprecated": extra.get("deprecated", False),
            "price_mtok": extra.get("price_1m_blended"),
            "price_input": extra.get("price_1m_input"),
            "price_output": extra.get("price_1m_output"),
            "price_source": "aa_models" if extra.get("price_1m_blended") is not None else None,
            "model_name": model["name"],
            "provider_route_id": None,
            "context_window": extra.get("context_window"),
            "output_speed": extra.get("output_speed"),
            "time_to_first_answer": extra.get("time_to_first_answer"),
            "mmmu_pro": extra.get("mmmu_pro"),
            "accepts_image": extra.get("accepts_image"),
            "supports_tools": extra.get("supports_tools"),
            "est_band": estimate.get("band"),
            "est_detail": detail,
            "detail": detail,
        })

    total_weight = sum(weights.values()) or 1.0
    for entity in entities:
        node = comps.get(entity["plain"], {})
        detail = _entity_base_detail(entity)
        cat_vals = {}
        if entity.get("measurement_type") == "aa_coding_agent" and entity.get("coding_index") is not None:
            cat_vals["coding_agent"] = entity["coding_index"]
            detail["coding_agent"] = {
                "value": entity["coding_index"],
                "estimated": False,
                "sources": [{"source": "aa_coding", "benchmark_id": "aa_coding_agent"}],
            }
        if entity.get("intelligence") is not None:
            cat_vals["intelligence"] = entity["intelligence"]
            detail["intelligence"] = {
                "value": entity["intelligence"],
                "estimated": bool(entity.get("intelligence_estimated")),
                "sources": [{"source": "aa_models", "benchmark_id": "aa_intelligence"}],
            }

        lane_values = {}
        evidence_groups = set()
        source_names = set()
        for lane, members in node.items():
            value, groups, used_entries = _aggregate_lane(members)
            if value is None:
                continue
            lane_values[lane] = value
            if isinstance(groups, dict):
                evidence_groups.update(groups.keys())
            source_names.update(entry["source"] for entry in used_entries)
            detail[lane] = {
                "value": value,
                "benchmark_values": groups,
                "sources": [
                    {
                        "source": entry["source"],
                        "kind": entry["kind"],
                        "benchmark_id": entry["benchmark_id"],
                        "norm": entry["norm"],
                        "raw": entry["raw"],
                        "name": entry["name"],
                        "normalization_status": entry["normalization_status"],
                        "retrieved_at": entry.get("retrieved_at"),
                    }
                    for entry in sorted(used_entries, key=lambda item: -(item.get("norm") or -1))
                ],
            }

        # External evidence can support the legacy summary, but it cannot become
        # the coding-agent category or turn a prediction into a measurement.
        by_legacy_category = defaultdict(list)
        for lane, value in lane_values.items():
            category = LANE_TO_LEGACY_CATEGORY.get(lane)
            if category:
                by_legacy_category[category].append(value)
        for category, values in by_legacy_category.items():
            if category == "intelligence" and "intelligence" in cat_vals:
                continue
            if category in weights:
                cat_vals[category] = round(statistics.mean(values), 2)

        weight_present = sum(weights.get(category, 0) for category in cat_vals)
        meta = (
            sum(weights.get(category, 0) * value for category, value in cat_vals.items()) / total_weight
            if cat_vals else None
        )
        coverage = weight_present / total_weight if total_weight else 0.0
        coding_band = entity.get("est_band") if entity.get("measurement_type") == "predicted_coding_agent" else None
        coding_weight = weights.get("coding_agent", 0.0)
        band = _band(meta, coding_weight / total_weight, coding_band, list(cat_vals.values())) if meta is not None else None
        entity["meta"] = round(meta, 2) if meta is not None else None
        entity["meta_min"] = round(max(0.0, meta - band), 2) if meta is not None and band is not None else None
        entity["meta_max"] = round(min(100.0, meta + band), 2) if meta is not None and band is not None else None
        entity["band"] = round(band, 2) if band is not None else None
        entity["coverage"] = round(coverage, 3)
        entity["n_sources"] = len(evidence_groups) + (1 if entity.get("intelligence") is not None else 0)
        entity["source_names"] = sorted(source_names | ({"aa_models"} if entity.get("intelligence") is not None else set()))
        entity["components"] = detail
        entity["categories"] = list(cat_vals.keys())
        entity["evidence_groups"] = sorted(evidence_groups)
        detail["source_names"] = entity["source_names"]
        detail["evidence_groups"] = entity["evidence_groups"]
        detail["coverage"] = entity["coverage"]

        vision_parts = []
        if entity.get("mmmu_pro") is not None:
            vision_parts.append(entity["mmmu_pro"])
        vision_parts.extend(
            entry["norm"]
            for entry in node.get("vision", [])
            if isinstance(entry.get("norm"), (int, float))
        )
        vision_frontend = [
            entry["norm"]
            for entry in node.get("visual_frontend", [])
            if isinstance(entry.get("norm"), (int, float))
        ]
        entity["vision_mmmu"] = entity.get("mmmu_pro")
        entity["vision_arena"] = round(statistics.mean(vision_parts[1:]), 1) if len(vision_parts) > 1 else None
        entity["vision_frontend"] = round(statistics.mean(vision_frontend), 1) if vision_frontend else None
        entity["vision"] = round(statistics.mean(vision_parts), 1) if vision_parts else None

    return entities


def build_market(coding_rows, model_rows, est_rows, pairs_attach):
    price_by_plain = {}
    for model in model_rows:
        slug = model.get("slug")
        if not slug:
            continue
        price = model["extra"].get("price_1m_blended")
        if price is not None:
            price_by_plain[slug] = price
    out = {}
    for coding in coding_rows:
        out[plain_key(coding["slug"])] = price_by_plain.get(coding["slug"])
    for estimate in est_rows:
        model = estimate["model_row"]
        if model.get("slug"):
            out.setdefault(model["slug"], model["extra"].get("price_1m_blended"))
    return out
