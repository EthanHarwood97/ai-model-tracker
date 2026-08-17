import unittest

from model_tracker.validation import validate_rows


class ValidationTests(unittest.TestCase):
    def test_empty_source_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_rows("livebench", [])

    def test_required_kind_is_checked(self):
        with self.assertRaises(ValueError):
            validate_rows("aa_coding", [{"kind": "wrong", "name": "Model", "score": 50}])

    def test_invalid_score_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_rows("aa_coding", [{"kind": "coding_index", "name": "Model", "score": 150}])

    def test_lmarena_elo_can_exceed_percentage_scale(self):
        result = validate_rows("lmarena", [{"kind": "arena_text_overall", "name": "Model", "score": 1500}])
        self.assertEqual(result["rows"], 1)


if __name__ == "__main__":
    unittest.main()
