import unittest

from model_tracker.normalize import canon, plain_key, slug_for_row


class IdentityTests(unittest.TestCase):
    def test_qwen_size_suffix_is_preserved(self):
        self.assertEqual(canon("Qwen3.8 27B"), "qwen3.8-27b")
        self.assertEqual(canon("Qwen3.6 27B (Reasoning)"), "qwen3.6-27b")
        self.assertEqual(canon("Qwen3.8 2.4T A95B"), "qwen3.8-2.4t-a95b")
        self.assertEqual(canon("Qwen3.5 397B A17B (Reasoning)"), "qwen3.5-397b-a17b")

    def test_qwen_hyphen_size_is_not_a_minor_version(self):
        self.assertEqual(canon("Qwen3-8B (FC)"), "qwen3-8b")
        self.assertEqual(canon("Qwen3-8B (Prompt)"), "qwen3-8b")
        self.assertEqual(canon("Qwen3 8B (Reasoning)"), "qwen3-8b")

    def test_qwen_max_is_model_name_not_effort(self):
        self.assertEqual(canon("Qwen3.8 Max"), "qwen3.8-max")
        self.assertEqual(plain_key("qwen3.8-max"), "qwen3.8-max")
        self.assertEqual(plain_key("qwen3.8-27b"), "qwen3.8-27b")

    def test_qwen_variants_never_collapse_onto_each_other(self):
        keys = {
            plain_key(canon("Qwen3.8 27B")),
            plain_key(canon("Qwen3.8 Max")),
            plain_key(slug_for_row({"name": "Qwen3-8B (FC)", "extra": {}})),
            plain_key(canon("Qwen3.8 2.4T A95B")),
        }
        self.assertEqual(len(keys), 4)
        self.assertEqual(plain_key(canon("Qwen3.8 Max")), plain_key(slug_for_row({"name": "qwen3.8-max", "extra": {}})))

    def test_distill_and_r1_derivatives_keep_full_identity(self):
        self.assertEqual(canon("DeepSeek R1 Distill Qwen 14B"), "deepseek-r1-distill-qwen-14b")
        self.assertEqual(canon("DeepSeek R1 0528 Qwen3 8B"), "deepseek-r1-0528-qwen3-8b")

    def test_effort_strip_still_works_for_non_qwen(self):
        self.assertEqual(plain_key("gpt5.6-luna-high"), "gpt5.6-luna")
        self.assertEqual(plain_key("opus5-max"), "opus5")
        self.assertEqual(plain_key("claude-4-5-haiku-high"), "claude-4-5-haiku")

    def test_solar_variants_keep_their_identity(self):
        self.assertEqual(canon("Solar Mini"), "solar-mini")
        self.assertEqual(canon("Solar Pro 4"), "solarpro4")
        self.assertEqual(canon("Solar Pro 2 (Preview)"), "solarpro2-preview")
        self.assertEqual(canon("Solar Open2 250B"), "solar-open2")
        self.assertEqual(canon("upstage/solar-pro-preview-instruct"), "solarpro-preview")
        keys = {
            plain_key(canon("Solar Mini")),
            plain_key(canon("Solar Pro 4")),
            plain_key(canon("Solar Pro 2 (Preview)")),
            plain_key(canon("Solar Open2 250B")),
        }
        self.assertEqual(len(keys), 4)


if __name__ == "__main__":
    unittest.main()
