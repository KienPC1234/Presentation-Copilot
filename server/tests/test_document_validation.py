import unittest

from services.document_validation import (
    validate_cheatsheet,
    validate_outline,
    validate_rebuttals,
)


class DocumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.allowed = {"e1", "e2"}
        self.question_ids = {"q1"}

    def test_valid_rebuttal_is_normalized(self):
        items = validate_rebuttals([{
            "question_id": "q1", "objection": "Cost is too high",
            "answer_points": ["Cite measured cost"], "evidence_ids": ["e1", "e1"],
            "fallback": "Say the number is not measured yet",
        }], self.allowed, self.question_ids)
        self.assertEqual(items[0]["evidence_ids"], ["e1"])

    def test_unknown_question_or_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_rebuttals([{"question_id": "q9", "objection": "x",
                                 "answer_points": [], "evidence_ids": [], "fallback": "y"}],
                               self.allowed, self.question_ids)
        with self.assertRaises(ValueError):
            validate_rebuttals([{"question_id": "q1", "objection": "x",
                                 "answer_points": [], "evidence_ids": ["forged"], "fallback": "y"}],
                               self.allowed, self.question_ids)

    def test_outline_requires_at_least_one_section(self):
        with self.assertRaises(ValueError):
            validate_outline([], self.allowed)
        sections = validate_outline([{"title": "Demo", "points": ["Show login"],
                                      "evidence_ids": ["e2"]}], self.allowed)
        self.assertEqual(sections[0]["title"], "Demo")

    def test_cheatsheet_bounds_lists(self):
        sheet = validate_cheatsheet({
            "key_numbers": ["3 tests passed"],
            "key_terms": ["latency"],
            "one_liners": [{"question": "Q?", "answer": "A", "evidence_ids": ["e1"]}],
        }, self.allowed)
        self.assertEqual(sheet["key_terms"], ["latency"])
        with self.assertRaises(ValueError):
            validate_cheatsheet({"one_liners": [{"question": "Q?", "answer": "A",
                                                 "evidence_ids": ["nope"]}]}, self.allowed)


if __name__ == "__main__":
    unittest.main()
