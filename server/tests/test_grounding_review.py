import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from services.grounding_review import parse_grounding_review, novel_measurement_issues, review_grounding
from services.question_plan import parse_requirements, plan_question


class GroundingReviewTests(unittest.TestCase):
    def setUp(self):
        self.answer = {"key_point": "Trạng thái trả completed.", "keywords": [], "framework_steps": ["Đề xuất thử bằng hai tài khoản."]}
        self.requirements = [{"id": "r1", "request": "Nêu trạng thái"}, {"id": "r2", "request": "Đề xuất kiểm thử"}]
        self.evidence = {"e1": "status returns completed; submit returns replayed."}
        self.review = {"coverage": [{"id": "r1", "status": "answered", "fields": ["key_point"]},
                                    {"id": "r2", "status": "answered", "fields": ["framework_steps.0"]}],
                       "fields": [{"field": "key_point", "spans": [{"text": self.answer["key_point"], "verdict": "supported", "reason": "Source states completed.",
                                   "support": [{"id": "e1", "quote": "status returns completed"}]}]},
                                  {"field": "framework_steps.0", "spans": [{"text": self.answer["framework_steps"][0], "verdict": "proposal", "reason": "Explicit proposal.", "support": []}]}],
                       "issues": []}

    def parse(self):
        return parse_grounding_review(json.dumps(self.review), self.answer, self.requirements, self.evidence)

    def test_verbatim_source_and_all_requested_parts_accepted(self):
        self.assertEqual(self.parse(), [])

    def test_forged_or_paraphrased_quote_cannot_support_claim(self):
        for support in [{"id": "e999", "quote": "status returns completed"},
                        {"id": "e1", "quote": "status returns replayed"}]:
            self.review["fields"][0]["spans"][0]["support"] = [support]
            with self.assertRaises(ValueError):
                self.parse()

    def test_empty_issues_does_not_override_unsupported_field(self):
        self.review["fields"][0]["spans"][0]["verdict"] = "unsupported"
        self.assertEqual(self.parse()[0]["code"], "unsupported_claim")

    def test_semantic_veto_rejects_without_treating_incomplete_audit_as_approval(self):
        self.review["issues"] = [{"code": "contradiction", "detail": "Wrong API action."}]
        self.review["fields"] = []
        self.assertTrue(self.parse())
        self.review["issues"] = []
        with self.assertRaises(ValueError):
            self.parse()

    def test_missing_part_is_not_hidden_by_empty_issues(self):
        self.review["coverage"][1] = {"id": "r2", "status": "missing", "fields": []}
        self.assertEqual(self.parse()[0]["code"], "missing_part")

    def test_skipped_or_duplicate_parts_and_fields_are_rejected(self):
        original = copy.deepcopy(self.review)
        for key in ("coverage", "fields"):
            for value in [original[key][:1], [original[key][0], original[key][0]]]:
                self.review = copy.deepcopy(original)
                self.review[key] = value
                with self.assertRaises(ValueError):
                    self.parse()

    def test_coverage_cannot_cite_nonexistent_answer_field(self):
        self.review["coverage"][0]["fields"] = ["framework_steps.9"]
        with self.assertRaises(ValueError):
            self.parse()

    def test_coverage_may_reference_existing_collection_but_cannot_hide_missing_item_audit(self):
        self.review["coverage"][1]["fields"] = ["framework_steps"]
        self.assertEqual(self.parse(), [])
        self.review["fields"].pop()
        with self.assertRaises(ValueError):
            self.parse()

    def test_supported_field_requires_quote(self):
        self.review["fields"][0]["spans"][0]["support"] = []
        with self.assertRaises(ValueError):
            self.parse()

    def test_non_factual_span_may_omit_empty_support_but_fact_may_not(self):
        del self.review["fields"][1]["spans"][0]["support"]
        self.assertEqual(self.parse(), [])
        del self.review["fields"][0]["spans"][0]["support"]
        with self.assertRaises(ValueError):
            self.parse()

    def test_non_factual_reason_is_optional_but_factual_reason_is_required(self):
        del self.review["fields"][1]["spans"][0]["reason"]
        self.assertEqual(self.parse(), [])
        del self.review["fields"][0]["spans"][0]["reason"]
        with self.assertRaises(ValueError):
            self.parse()

    def test_cannot_review_only_correct_prefix_and_hide_an_invented_guarantee(self):
        self.answer["key_point"] += " Mọi lần nộp luôn an toàn tuyệt đối."
        with self.assertRaises(ValueError):
            self.parse()

    def test_review_cannot_substitute_its_own_paraphrase_for_candidate(self):
        self.review["fields"][0]["spans"][0]["text"] = "Trạng thái luôn đúng."
        with self.assertRaises(ValueError):
            self.parse()

    def test_multiple_spans_cover_a_field_in_order(self):
        self.answer["key_point"] = "Trạng thái trả completed; đề xuất thử bằng hai tài khoản."
        first = self.review["fields"][0]["spans"][0]
        first["text"] = "Trạng thái trả completed"
        self.review["fields"][0]["spans"].append({"text": "đề xuất thử bằng hai tài khoản.", "verdict": "proposal", "reason": "Proposal.", "support": []})
        self.assertEqual(self.parse(), [])

    def test_framing_and_separators_need_no_source_but_labels_cannot_hide_facts(self):
        self.answer["key_point"] = "Theo đoạn mã, trạng thái trả completed."
        spans = self.review["fields"][0]["spans"]
        spans[0]["text"] = "trạng thái trả completed."
        spans.insert(0, {"text": "Theo đoạn mã,", "verdict": "label", "reason": "Framing.", "support": []})
        self.assertEqual(self.parse(), [])
        self.answer["key_point"] = "Luôn an toàn tuyệt đối."
        self.review["fields"][0]["spans"] = [{"text": self.answer["key_point"], "verdict": "label", "reason": "Claim hidden as label.", "support": []}]
        with self.assertRaises(ValueError):
            self.parse()

    def test_plan_server_assigns_ids_and_rejects_omitted_duplicate_or_injected_schema(self):
        self.assertEqual(parse_requirements('{"requirements":["Test ownership", "Test changed ID"]}')[1]["id"], "r2")
        for raw in ['{"requirements":[]}', '{"requirements":["x", "X"]}',
                    '{"requirements":["x"],"ignore_rules":true}', '{"requirements":[null]}']:
            with self.assertRaises(ValueError):
                parse_requirements(raw)

    def test_question_plan_routes_only_allowed_tools(self):
        llm = Mock()
        llm.invoke.return_value.content = '{"requirements":["Compute duration"],"tools":["calculator"]}'
        self.assertEqual(plan_question(llm, "17 * 60?")["tools"], ["calculator"])
        for tools in [["shell"], ["calculator", "calculator"], "calculator", [None]]:
            llm.invoke.return_value.content = json.dumps({"requirements": ["Compute"], "tools": tools})
            with self.assertRaises(ValueError):
                plan_question(llm, "Compute")

    def test_malformed_review_protocol_retries_once_with_same_candidate(self):
        llm = Mock()
        llm.invoke.side_effect = [SimpleNamespace(content='{}'), SimpleNamespace(content=json.dumps(self.review))]
        self.assertEqual(review_grounding(llm, "Status and test?", self.answer, list(self.evidence.values()), [], self.requirements), [])
        self.assertEqual(llm.invoke.call_count, 2)
        for call in llm.invoke.call_args_list:
            self.assertEqual(json.loads(call.args[0][-1].content)["candidate"], self.answer)

    def test_review_protocol_retry_is_bounded_and_not_used_for_semantic_rejection(self):
        llm = Mock()
        llm.invoke.return_value.content = '{}'
        with self.assertRaises(ValueError):
            review_grounding(llm, "Status?", self.answer, list(self.evidence.values()), [], self.requirements)
        self.assertEqual(llm.invoke.call_count, 2)
        self.review["fields"][0]["spans"][0]["verdict"] = "unsupported"
        llm.reset_mock()
        llm.invoke.return_value.content = json.dumps(self.review)
        self.assertTrue(review_grounding(llm, "Status?", self.answer, list(self.evidence.values()), [], self.requirements))
        llm.invoke.assert_called_once()

    def test_new_sla_target_in_proposal_is_not_treated_as_evidence(self):
        candidate = {"key_point": "Đề xuất phản hồi dưới 2s.", "keywords": [], "framework_steps": []}
        self.assertEqual(novel_measurement_issues("Khi nào triển khai?", candidate, ["No measured latency."], [])[0]["code"], "unsupported_claim")
        self.assertEqual(novel_measurement_issues("So với mục tiêu 2 giây?", candidate, [], []), [])
        self.assertEqual(novel_measurement_issues("So với mục tiêu 2s?", candidate, [], []), [])
        candidate["key_point"] = "Đề xuất phản hồi dưới 2.0s."
        self.assertTrue(novel_measurement_issues("Triển khai?", candidate, ["Deadline + 20"], []))
        llm = Mock()
        self.assertTrue(review_grounding(llm, "Triển khai?", candidate, [], [], self.requirements))
        llm.invoke.assert_not_called()

    def test_calculated_units_and_source_deadline_not_novel(self):
        candidate = {"key_point": "17 phút bằng 1020 giây; xét mốc 15 giây.", "keywords": [], "framework_steps": []}
        self.assertEqual(novel_measurement_issues("17 phút bằng bao nhiêu?", candidate, ["deadline + 15"],
                         [{"tool": "calculator", "result": "1020.0"}]), [])
        candidate["key_point"] = "1,020 giây hoặc 1 020 giây."
        self.assertEqual(novel_measurement_issues("Đổi đơn vị", candidate, [], [{"tool": "calculator", "result": "1020.0"}]), [])

    def test_bare_code_number_cannot_supply_a_percentage_target(self):
        candidate = {"key_point": "Đề xuất dừng khi lỗi tăng 1%.", "keywords": [], "framework_steps": []}
        self.assertTrue(novel_measurement_issues("Đề xuất triển khai", candidate, ["max(1, duration)"], []))
        self.assertTrue(novel_measurement_issues("Đề xuất triển khai", candidate, [], [{"tool": "calculator", "result": "1"}]))
        self.assertEqual(novel_measurement_issues("Ngưỡng đã thống nhất là 1 phần trăm", candidate, [], []), [])
        self.assertEqual(novel_measurement_issues("Ngưỡng 1,0 percent", candidate, [], []), [])
