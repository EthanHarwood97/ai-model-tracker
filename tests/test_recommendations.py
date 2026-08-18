import unittest

from model_tracker.recommendations import build_recommendations


CFG = {
    "workloads": {
        "opencode_turn": {
            "input_tokens": 120000,
            "output_tokens": 8000,
            "budget_usd": {
                "research": 0.10,
                "general_coder": 0.25,
                "ui_coder": 0.35,
                "complex_code": None,
            },
        }
    }
}


def model(name, slug, measurement_type, quality, prompt, completion, **kwargs):
    components = kwargs.pop("components", {})
    model_index = kwargs.pop("model_index", quality if measurement_type == "aa_model_index" else None)
    return {
        "name": name,
        "slug": slug,
        "measurement_type": measurement_type,
        "score_source": measurement_type,
        "coding_index": quality,
        "aa_model_coding_index": model_index,
        "intelligence": kwargs.pop("intelligence", 70),
        "price_mtok": (prompt * 3 + completion) / 4,
        "price_input": prompt,
        "price_output": completion,
        "speed": kwargs.pop("speed", 70),
        "supports_tools": kwargs.pop("supports_tools", True),
        "accepts_image": kwargs.pop("accepts_image", False),
        "deprecated": False,
        "coverage": 1.0,
        "source_names": ["test"],
        "evidence_groups": ["test"],
        "components": components,
        "detail": {"price_input": prompt, "price_output": completion},
        **kwargs,
    }


class RecommendationTests(unittest.TestCase):
    def test_general_coder_prefers_quality_that_fits_budget(self):
        cheap = model("Cheap coder", "cheap", "aa_coding_agent", 78, 0.20, 0.20)
        expensive = model("Expensive coder", "expensive", "aa_coding_agent", 96, 5, 10)
        recommendations = build_recommendations([cheap, expensive], CFG)
        self.assertEqual(recommendations["general_coder"]["recommended"]["name"], "Cheap coder")

    def test_complex_code_ignores_price(self):
        cheap = model("Cheap coder", "cheap", "aa_coding_agent", 78, 0.20, 0.20)
        expensive = model("Expensive coder", "expensive", "aa_coding_agent", 96, 5, 10)
        recommendations = build_recommendations([cheap, expensive], CFG)
        self.assertEqual(recommendations["complex_code"]["recommended"]["name"], "Expensive coder")

    def test_ui_role_requires_visual_evidence(self):
        coding_only = model("Coding only", "coding", "aa_coding_agent", 98, 0.10, 0.10)
        visual = model(
            "Visual coder",
            "visual",
            "aa_coding_agent",
            82,
            0.20,
            0.20,
            accepts_image=True,
            components={"visual_frontend": {"value": 92}},
        )
        recommendations = build_recommendations([coding_only, visual], CFG)
        self.assertEqual(recommendations["ui_coder"]["recommended"]["name"], "Visual coder")

    def test_research_role_requires_tool_capability(self):
        no_tools = model("No tools", "no-tools", "aa_coding_agent", 99, 0.01, 0.01, supports_tools=False)
        tool_model = model(
            "Tool model",
            "tools",
            "aa_coding_agent",
            75,
            0.10,
            0.10,
            supports_tools=True,
            components={"tool_use": {"value": 80}, "reasoning": {"value": 75}},
        )
        recommendations = build_recommendations([no_tools, tool_model], CFG)
        self.assertEqual(recommendations["research"]["recommended"]["name"], "Tool model")

    def test_low_prediction_is_excluded_from_coding_roles(self):
        weak = model(
            "Weak predicted",
            "weak",
            "predicted_coding_agent",
            13,
            0.05,
            0.05,
            components={"coding_support": {"value": 99}},
        )
        solid = model("Solid measured", "solid", "aa_coding_agent", 66, 0.10, 0.10)
        recommendations = build_recommendations([weak, solid], CFG)
        names = [candidate["name"] for candidate in recommendations["general_coder"]["candidates"]]
        self.assertNotIn("Weak predicted", names)
        self.assertEqual(recommendations["general_coder"]["recommended"]["name"], "Solid measured")

    def test_model_index_coding_is_discounted(self):
        indexy = model(
            "Index only",
            "indexy",
            "aa_model_index",
            80,
            0.01,
            0.01,
            model_index=80,
            components={"coding_support": {"value": 80}, "visual_frontend": {"value": 80}},
        )
        recommendations = build_recommendations([indexy], CFG)
        candidate = recommendations["ui_coder"]["candidates"][0]
        expected_quality = (0.40 * 72 + 0.15 * 80 + 0.45 * 80) / 1.0
        self.assertAlmostEqual(candidate["quality_score"], expected_quality, places=2)
        self.assertLess(candidate["quality_score"], 80)
        self.assertIn("model index", "".join(candidate["warnings"]).lower())

    def test_general_coder_requires_measured_coding_agent(self):
        indexy = model(
            "Index only",
            "indexy",
            "aa_model_index",
            80,
            0.01,
            0.01,
            model_index=80,
            components={"coding_support": {"value": 99}},
        )
        measured = model("Measured", "measured", "aa_coding_agent", 66, 0.10, 0.10)
        recommendations = build_recommendations([indexy, measured], CFG)
        names = [candidate["name"] for candidate in recommendations["general_coder"]["candidates"]]
        self.assertNotIn("Index only", names)
        self.assertEqual(recommendations["general_coder"]["recommended"]["name"], "Measured")

    def test_general_coder_excludes_below_coding_floor(self):
        weak = model("Weak measured", "weak", "aa_coding_agent", 42, 0.01, 0.01)
        solid = model("Solid measured", "solid", "aa_coding_agent", 66, 0.10, 0.10)
        recommendations = build_recommendations([weak, solid], CFG)
        names = [candidate["name"] for candidate in recommendations["general_coder"]["candidates"]]
        self.assertNotIn("Weak measured", names)
        self.assertEqual(recommendations["general_coder"]["recommended"]["name"], "Solid measured")

    def test_general_coder_rewards_cheaper_measured_model(self):
        good_cheap = model("Good cheap", "good-cheap", "aa_coding_agent", 64, 0.005, 0.02)
        slightly_better = model("Slightly better", "better", "aa_coding_agent", 66, 0.18, 0.20)
        recommendations = build_recommendations([good_cheap, slightly_better], CFG)
        self.assertEqual(recommendations["general_coder"]["recommended"]["name"], "Good cheap")

    def test_research_rewards_cheaper_faster_model(self):
        cheap_fast = model(
            "Cheap fast",
            "cheap-fast",
            "aa_coding_agent",
            68,
            0.002,
            0.01,
            speed=80,
            components={"reasoning": {"value": 68}, "tool_use": {"value": 70}, "agentic": {"value": 65}},
        )
        pricey_slower = model(
            "Pricey slower",
            "pricey",
            "aa_coding_agent",
            73,
            0.08,
            0.10,
            speed=45,
            components={"reasoning": {"value": 72}, "tool_use": {"value": 75}, "agentic": {"value": 70}},
        )
        recommendations = build_recommendations([cheap_fast, pricey_slower], CFG)
        self.assertEqual(recommendations["research"]["recommended"]["name"], "Cheap fast")

    def test_ui_requires_dedicated_frontend_evidence(self):
        proxy_only = model(
            "Proxy only",
            "proxy-only",
            "aa_coding_agent",
            90,
            0.05,
            0.05,
            components={"vision": {"value": 95}},
        )
        frontend = model(
            "Frontend",
            "frontend",
            "aa_coding_agent",
            60,
            0.10,
            0.10,
            components={"visual_frontend": {"value": 88}},
        )
        recommendations = build_recommendations([proxy_only, frontend], CFG)
        names = [candidate["name"] for candidate in recommendations["ui_coder"]["candidates"]]
        self.assertNotIn("Proxy only", names)
        self.assertEqual(recommendations["ui_coder"]["recommended"]["name"], "Frontend")

    def test_ui_excludes_weak_frontend_scores(self):
        weak = model(
            "Weak visual",
            "weak-visual",
            "aa_coding_agent",
            95,
            0.01,
            0.01,
            components={"visual_frontend": {"value": 62}},
        )
        strong = model(
            "Strong visual",
            "strong-visual",
            "aa_coding_agent",
            60,
            0.10,
            0.10,
            components={"visual_frontend": {"value": 88}},
        )
        recommendations = build_recommendations([weak, strong], CFG)
        names = [candidate["name"] for candidate in recommendations["ui_coder"]["candidates"]]
        self.assertNotIn("Weak visual", names)
        self.assertEqual(recommendations["ui_coder"]["recommended"]["name"], "Strong visual")

    def test_ui_prefers_frontend_board_over_vision_proxy(self):
        proxy_high = model(
            "High proxy",
            "proxy",
            "aa_coding_agent",
            60,
            0.10,
            0.10,
            components={"visual_frontend": {"value": 70}, "vision": {"value": 95}},
        )
        frontend_high = model(
            "High frontend",
            "frontend",
            "aa_coding_agent",
            60,
            0.10,
            0.10,
            components={"visual_frontend": {"value": 88}, "vision": {"value": 80}},
        )
        recommendations = build_recommendations([proxy_high, frontend_high], CFG)
        self.assertEqual(recommendations["ui_coder"]["recommended"]["name"], "High frontend")


if __name__ == "__main__":
    unittest.main()
