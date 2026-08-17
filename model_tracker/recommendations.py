from collections import OrderedDict


ROLE_PROFILES = OrderedDict(
    (
        (
            "research",
            {
                "label": "Research / lightweight agent",
                "description": "Cheap, fast models that can still operate OpenCode tools and long context.",
                "weights": {"quality": 0.45, "cost": 0.30, "speed": 0.25},
                "quality": {"reasoning": 0.30, "tool_use": 0.30, "agentic": 0.20, "intelligence": 0.20},
                "requires_tools": True,
            },
        ),
        (
            "general_coder",
            {
                "label": "General coder",
                "description": "The best coding capability per OpenCode turn, not merely the highest raw benchmark.",
                "weights": {"quality": 0.65, "cost": 0.25, "speed": 0.10},
                "quality": {"coding": 0.65, "coding_support": 0.25, "agentic": 0.10},
            },
        ),
        (
            "ui_coder",
            {
                "label": "UI coder",
                "description": "Models with visual/frontend evidence as well as reliable coding ability.",
                "weights": {"quality": 0.70, "cost": 0.15, "speed": 0.15},
                "quality": {"visual": 0.45, "coding": 0.40, "coding_support": 0.15},
                "requires_visual": True,
            },
        ),
        (
            "complex_code",
            {
                "label": "Complex code",
                "description": "Highest measured coding and agentic quality, with price ignored.",
                "weights": {"quality": 1.0, "cost": 0.0, "speed": 0.0},
                "quality": {"coding": 0.70, "agentic": 0.20, "coding_support": 0.10},
                "measured_only": True,
                "requires_agent_measurement": True,
            },
        ),
    )
)


def _number(value):
    return value if isinstance(value, (int, float)) else None


def _component_value(entity, lane):
    components = entity.get("components") or {}
    block = components.get(lane) or {}
    value = block.get("value") if isinstance(block, dict) else None
    return _number(value)


def _quality_signals(entity):
    measurement_type = entity.get("measurement_type")
    actual_coding = entity.get("coding_index") if measurement_type == "aa_coding_agent" else None
    support_coding = _component_value(entity, "coding_support")
    if measurement_type == "livebench":
        support_coding = support_coding or _number(entity.get("coding_index"))
    model_coding = _number(entity.get("aa_model_coding_index"))
    predicted_coding = (
        _number(entity.get("coding_index"))
        if measurement_type == "predicted_coding_agent"
        else None
    )
    return {
        "coding": actual_coding,
        "coding_support": support_coding,
        "aa_model_coding": model_coding,
        "predicted_coding": predicted_coding,
        "agentic": _component_value(entity, "agentic"),
        "tool_use": _component_value(entity, "tool_use"),
        "reasoning": _component_value(entity, "reasoning"),
        "intelligence": _number(entity.get("intelligence")),
        "visual": max(
            [value for value in (
                _number(entity.get("vision_frontend")),
                _number(entity.get("vision")),
                _component_value(entity, "visual_frontend"),
                _component_value(entity, "vision"),
            ) if value is not None],
            default=None,
        ),
        "visual_frontend": max(
            [value for value in (
                _number(entity.get("vision_frontend")),
                _component_value(entity, "visual_frontend"),
            ) if value is not None],
            default=None,
        ),
        "speed": _number(entity.get("speed")),
    }


def _projected_cost(entity, workload):
    detail = entity.get("detail") or {}
    input_tokens = float(workload.get("input_tokens", 120000))
    output_tokens = float(workload.get("output_tokens", 8000))
    prompt_price = detail.get("price_input", entity.get("price_input"))
    completion_price = detail.get("price_output", entity.get("price_output"))
    if _number(prompt_price) is not None and _number(completion_price) is not None:
        return round(
            (input_tokens * float(prompt_price) + output_tokens * float(completion_price)) / 1_000_000,
            4,
        ), "projected_opencode_turn"
    blended = _number(entity.get("price_mtok"))
    if blended is not None:
        return round((input_tokens + output_tokens) * float(blended) / 1_000_000, 4), "blended_token_price"
    return None, None


def _weighted_mean(signals, weights):
    present = [(signals.get(key), weight) for key, weight in weights.items() if signals.get(key) is not None]
    if not present:
        return None, 0.0
    weight_sum = sum(weight for _, weight in present)
    return round(sum(value * weight for value, weight in present) / weight_sum, 2), round(weight_sum, 3)


def _confidence(entity, signals, quality_coverage):
    measurement_type = entity.get("measurement_type")
    base = {
        "aa_coding_agent": 0.95,
        "livebench": 0.70,
        "aa_model_index": 0.60,
        "predicted_coding_agent": 0.35,
        "unavailable": 0.10,
    }.get(measurement_type, 0.55)
    evidence_count = len(entity.get("evidence_groups") or [])
    corroboration = min(0.15, evidence_count * 0.04)
    confidence = min(1.0, base * (0.70 + quality_coverage * 0.30) + corroboration)
    if entity.get("deprecated"):
        confidence *= 0.25
    return round(confidence, 2)


def _confidence_label(value):
    if value >= 0.80:
        return "high"
    if value >= 0.55:
        return "medium"
    return "low"


def _capability_status(entity):
    if entity.get("supports_tools") is True or entity.get("supports_tools") == 1:
        return "verified"
    if entity.get("supports_tools") is False or entity.get("supports_tools") == 0:
        return "unsupported"
    if _component_value(entity, "tool_use") is not None or _component_value(entity, "agentic") is not None:
        return "benchmark_evidence"
    return "unknown"


def _candidate(entity, role, profile, workload):
    signals = _quality_signals(entity)
    quality, quality_coverage = _weighted_mean(signals, profile["quality"])
    if quality is None:
        return None
    if profile.get("requires_tools"):
        capability = _capability_status(entity)
        if capability == "unsupported":
            return None
    if profile.get("requires_visual") and signals["visual"] is None:
        return None
    if profile.get("requires_agent_measurement") and entity.get("measurement_type") != "aa_coding_agent":
        return None
    if profile.get("measured_only"):
        if entity.get("measurement_type") not in {"aa_coding_agent", "livebench"} and signals["coding_support"] is None:
            return None

    projected_cost, cost_basis = _projected_cost(entity, workload)
    budget = workload.get("budget_usd", {}).get(role)
    if budget is None or projected_cost is None:
        cost_factor = 1.0
    else:
        cost_factor = min(1.0, float(budget) / max(projected_cost, 0.0001))
    speed = signals.get("speed") or 50.0
    weights = profile["weights"]
    role_score = (
        quality * weights["quality"]
        + cost_factor * 100 * weights["cost"]
        + speed * weights["speed"]
    )
    confidence = _confidence(entity, signals, quality_coverage)
    warnings = []
    capability = _capability_status(entity)
    if profile.get("requires_tools") and capability == "unknown":
        warnings.append("tool support is not explicitly verified")
    if profile.get("requires_tools") and capability == "benchmark_evidence":
        warnings.append("tool capability is inferred from benchmark evidence")
    if profile.get("requires_visual") and signals.get("visual_frontend") is None:
        warnings.append("no dedicated frontend-board score is available; visual score is a proxy")
    if projected_cost is None:
        warnings.append("no provider price is available for the OpenCode workload")
    if budget is not None and projected_cost is not None and projected_cost > budget:
        warnings.append("above the configured workload budget")
    if entity.get("measurement_type") == "predicted_coding_agent":
        warnings.append("coding score is a regression estimate")
    if entity.get("measurement_type") == "aa_model_index":
        warnings.append("coding signal is from the model index, not an agent run")
    if entity.get("deprecated"):
        warnings.append("provider marks this model deprecated")

    return {
        "slug": entity.get("slug"),
        "name": entity.get("name"),
        "role_score": round(role_score, 2),
        "quality_score": quality,
        "quality_coverage": quality_coverage,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "measurement_type": entity.get("measurement_type"),
        "score_source": entity.get("score_source"),
        "coding_index": entity.get("coding_index"),
        "intelligence": entity.get("intelligence"),
        "visual_score": signals.get("visual"),
        "speed": entity.get("speed"),
        "projected_cost_usd": projected_cost,
        "cost_basis": cost_basis,
        "benchmark_task_cost_usd": entity.get("cost_task"),
        "token_price_mtok": entity.get("price_mtok"),
        "provider_route_id": entity.get("provider_route_id"),
        "supports_tools": capability,
        "accepts_image": entity.get("accepts_image"),
        "coverage": entity.get("coverage", 0),
        "source_names": entity.get("source_names", []),
        "warnings": warnings,
    }


def _sort_key(candidate):
    cost = candidate.get("projected_cost_usd")
    return (-candidate["role_score"], -candidate["quality_score"], cost if cost is not None else float("inf"))


def build_recommendations(entities, cfg):
    workload = dict(cfg.get("workloads", {}).get("opencode_turn", {}))
    workload.setdefault("budget_usd", {})
    results = {}
    for role, profile in ROLE_PROFILES.items():
        candidates = []
        for entity in entities:
            if entity.get("deprecated"):
                continue
            result = _candidate(entity, role, profile, workload)
            if result is not None:
                candidates.append(result)

        budget = workload.get("budget_usd", {}).get(role)
        known_cost = [candidate for candidate in candidates if candidate.get("projected_cost_usd") is not None]
        under_budget = [
            candidate for candidate in known_cost
            if budget is None or candidate["projected_cost_usd"] <= budget
        ]
        budget_relaxed = False
        price_unverified = False
        if budget is None:
            under_budget = candidates
        elif under_budget:
            candidates = under_budget
        elif known_cost:
            candidates = known_cost
            budget_relaxed = True
        elif candidates:
            # A cheap recommendation without a price is not safe to publish.
            price_unverified = True
            candidates = []
        candidates.sort(key=_sort_key)
        recommended = candidates[0] if candidates else None
        if recommended is not None and budget_relaxed:
            recommended["warnings"].append("no candidate met the configured workload budget")
        results[role] = {
            "role": role,
            "label": profile["label"],
            "description": profile["description"],
            "budget_usd": budget,
            "status": "price_unverified" if price_unverified else "ok" if recommended else "insufficient_evidence",
            "recommended": recommended,
            "candidates": candidates[:8],
        }
    return results
