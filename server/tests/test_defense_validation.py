import unittest
from copy import deepcopy
from services.defense_validation import CATEGORIES, validate_plan


class DefenseValidationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = [{"id": "e1", "excerpt": "Project fact"}]
        self.plan = {"questions": [{"category": category, "question": f"Question {index}?",
            "purpose": "Understand tradeoffs", "follow_up": "What proof exists?",
            "answer_outline": ["Known fact"], "evidence_ids": ["e1"]}
            for index, category in enumerate(CATEGORIES)]}

    def test_valid_plan_has_server_ids_and_cited_status(self):
        questions = validate_plan(self.plan, self.evidence, 6)
        self.assertEqual(questions[0]["id"], "q1")
        self.assertEqual(questions[0]["evidence_status"], "cited")

    def test_missing_evidence_is_marked_missing(self):
        self.plan["questions"][0]["evidence_ids"] = []
        item = validate_plan(self.plan, self.evidence, 6)[0]
        self.assertEqual(item["evidence_status"], "missing")
        self.assertNotIn("Known fact", item["answer_outline"])

    def test_forged_reference_rejected(self):
        self.plan["questions"][0]["evidence_ids"] = ["invented"]
        with self.assertRaises(ValueError): validate_plan(self.plan, self.evidence, 6)

    def test_required_category_cannot_be_omitted(self):
        self.plan["questions"][0]["category"] = "technical"
        with self.assertRaises(ValueError): validate_plan(self.plan, self.evidence, 6)

    def test_count_and_duplicate_questions_rejected(self):
        with self.assertRaises(ValueError): validate_plan(self.plan, self.evidence, 3)
        self.plan["questions"][1]["question"] = self.plan["questions"][0]["question"]
        with self.assertRaises(ValueError): validate_plan(self.plan, self.evidence, 6)

    def test_malformed_outline_rejected(self):
        self.plan["questions"][0]["answer_outline"] = "not a list"
        with self.assertRaises(ValueError): validate_plan(self.plan, self.evidence, 6)
