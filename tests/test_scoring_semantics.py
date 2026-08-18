import unittest

from model_tracker.composite import build_components, compute_entities, normalize_within
from model_tracker.estimator import estimate_for_model


CFG = {
    "weights": {
        "coding_agent": 0.35,
        "intelligence": 0.25,
        "code_correctness": 0.20,
        "human_pref": 0.10,
        "agentic": 0.10,
    },
    "normalization": {"mode": "minmax", "minmax_floor": 0, "minmax_ceiling": 100},
    "est": {
        "band": 0.06,
        "extrapolated_band": 0.10,
        "band_points": 6,
        "extrapolated_band_points": 10,
        "cap": 0.75,
        "agree_threshold": 0.03,
        "int_slope": 0.01417,
        "int_intercept": -0.2089,
        "code_slope": 0.01206,
        "code_intercept": -0.3022,
    },
    "known_underperform": ["DeepSeek"],
    "known_overperform": [],
}


class ScoringSemanticsTests(unittest.TestCase):
    def test_singleton_normalization_is_missing_not_average(self):
        rows = [{"score": 75}]
        normalize_within(rows)
        self.assertIsNone(rows[0]["score_norm"])
        self.assertEqual(rows[0]["normalization_status"], "insufficient_cohort")

    def test_livebench_lanes_do_not_double_count_global_score(self):
        rows = [
            {"source": "livebench", "kind": "livebench_global", "name": "Alpha", "score": 80, "extra": {}},
            {"source": "livebench", "kind": "livebench_global", "name": "Beta", "score": 70, "extra": {}},
            {"source": "livebench", "kind": "livebench_coding", "name": "Alpha", "score": 60, "extra": {}},
            {"source": "livebench", "kind": "livebench_coding", "name": "Beta", "score": 50, "extra": {}},
            {"source": "livebench", "kind": "livebench_agentic", "name": "Alpha", "score": 40, "extra": {}},
            {"source": "livebench", "kind": "livebench_agentic", "name": "Beta", "score": 30, "extra": {}},
        ]
        components = build_components({"livebench": rows}, CFG)
        self.assertNotIn("livebench_global", components.get("alpha", {}))
        self.assertIn("coding_support", components["alpha"])
        self.assertIn("agentic", components["alpha"])

    def test_model_index_is_not_agent_measurement(self):
        result = estimate_for_model(
            {"slug": "m", "name": "Model M", "score": 50, "extra": {"coding_index": 50}},
            CFG,
        )
        self.assertEqual(result["measurement_type"], "aa_model_index")
        self.assertFalse(result["estimated"])
        self.assertEqual(result["score"], 50)
        self.assertIsNone(result["band"])

    def test_index_coding_is_rejected_when_impossibly_inflated(self):
        result = estimate_for_model(
            {"slug": "solar-mini", "name": "Solar Mini", "score": 5.97, "extra": {"coding_index": 78.35}},
            CFG,
        )
        self.assertEqual(result["measurement_type"], "predicted_coding_agent")
        self.assertTrue(result["estimated"])
        self.assertEqual(result["score"], 0)
        self.assertFalse(result["detail"]["agrees"])

    def test_coder_specialist_survives_the_inflation_gate(self):
        result = estimate_for_model(
            {"slug": "kat", "name": "KAT Coder Pro V2", "score": 33.73, "extra": {"coding_index": 59.46}},
            CFG,
        )
        self.assertEqual(result["measurement_type"], "aa_model_index")
        self.assertFalse(result["estimated"])

    def test_prediction_band_uses_score_points_and_caps_before_flagging(self):
        result = estimate_for_model(
            {"slug": "m", "name": "Model M", "score": 90, "extra": {}},
            CFG,
            train_max_iq=80,
        )
        self.assertEqual(result["measurement_type"], "predicted_coding_agent")
        self.assertTrue(result["detail"]["capped"])
        self.assertEqual(result["band"], 10)
        self.assertEqual(result["score"], 75)

    def test_external_benchmarks_never_promote_estimate_to_measured(self):
        entities = compute_entities(
            [],
            [],
            [{
                "slug": "modelm",
                "name": "Model M",
                "score": 55,
                "estimated": True,
                "band": 6,
                "measurement_type": "predicted_coding_agent",
                "score_source": "intelligence_regression",
                "detail": {"source": "intelligence_regression", "band_points": 6},
                "model_row": {
                    "name": "Model M",
                    "slug": "modelm",
                    "score": 55,
                    "extra": {},
                },
            }],
            {},
            {"model-m": {"coding_support": [{
                "source": "swebench",
                "kind": "swebench_verified",
                "lane": "coding_support",
                "benchmark_id": "swebench:swebench_verified",
                "name": "Model M",
                "norm": 95,
                "raw": 95,
                "normalization_status": "relative_minmax",
            }]}},
            CFG,
        )
        self.assertEqual(len(entities), 1)
        self.assertFalse(entities[0]["measured"])
        self.assertEqual(entities[0]["measurement_type"], "predicted_coding_agent")
        self.assertNotIn("coding_agent", entities[0]["components"])
        self.assertIn("coding_support", entities[0]["components"])


if __name__ == "__main__":
    unittest.main()
