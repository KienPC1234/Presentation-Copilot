import json
import unittest

from export_evaluation_summary import summarize


class ExportTests(unittest.TestCase):
    def expert(self):
        return {"answers": [
            {"role": "ok", "seconds": 1, "question": "PRIVATE QUESTION", "answer": {"key_point": "PRIVATE SOURCE", "review_status": "model_reviewed"}},
            {"role": "blocked", "seconds": 2, "answer": {"error": "PRIVATE ERROR", "key_point": "PRIVATE CANDIDATE"}},
            {"role": "exception", "seconds": 3, "error": "PRIVATE EXCEPTION", "review_trace": "PRIVATE TRACE"}],
            "valid_answers": 1, "blocked_or_failed_answers": 2, "execution_gate_passed": False}

    def test_nested_and_top_level_errors_are_counted_without_private_content(self):
        result = summarize(self.expert())
        self.assertEqual([row["is_error"] for row in result["answers"]], [False, True, True])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(result["blocked_or_failed_answers"], 2)

    def test_rejects_counter_disagreement(self):
        report = self.expert()
        report["valid_answers"] = 3
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            summarize(report)

    def test_missing_answer_is_not_success(self):
        report = self.expert()
        del report["answers"][0]["answer"]
        with self.assertRaises(ValueError):
            summarize(report)

    def test_conversation_error_and_context_check_both_control_gate(self):
        report = {"results": [{"case": "followup", "answer": {"error": "private"}}],
                  "checks": [{"check": "other unchanged", "passed": True}], "execution_passed": False}
        self.assertTrue(summarize(report)["results"][0]["is_error"])
        report["results"][0]["answer"] = {"key_point": "private"}
        report["checks"][0]["passed"] = False
        self.assertFalse(summarize(report)["execution_passed"])
