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
    return {
        "name": name,
        "slug": slug,
        "measurement_type": measurement_type,
        "score_source": measurement_type,
        "coding_index": quality,
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


if __name__ == "__main__":
    unittest.main()
