import json
import unittest

from services.answer_review import deterministic_issues, drop_self_contradictory, parse_review


class AnswerReviewTests(unittest.TestCase):
    def test_self_contradictory_unsupported_claim_is_dropped(self):
        issues = [
            {"code": "unsupported_claim",
             "detail": "The candidate states X. The evidence supports this: README.md says 'Automatic backup'."},
            {"code": "unsupported_claim", "detail": "The endpoint /api/change_id is not in the excerpts."},
            {"code": "missing_part", "detail": "The evidence supports this part is missing."},
        ]
        kept = drop_self_contradictory(issues)
        self.assertEqual([item["code"] for item in kept], ["unsupported_claim", "missing_part"])

    def test_absence_statement_is_not_an_unsupported_claim(self):
        issues = [
            {"code": "unsupported_claim",
             "detail": "The candidate asserts 'Tài liệu không nêu cách kiểm chứng độc lập'. The excerpts contain no statement about it."},
            {"code": "unsupported_claim",
             "detail": "The candidate claims precision 0.95 on a public benchmark, which the excerpts do not support."},
        ]
        kept = drop_self_contradictory(issues)
        self.assertEqual(len(kept), 1)
        self.assertIn("0.95", kept[0]["detail"])

    def test_valid_empty_review(self):
        self.assertEqual(parse_review('{"issues": []}'), [])
        self.assertEqual(parse_review('```json\n{"issues": []}\n```'), [])

    def test_issue_must_be_actionable_and_known(self):
        for issue in [{"code": "approved", "detail": "ok"},
                      {"code": "unsupported_claim", "detail": " "}]:
            with self.assertRaises(ValueError):
                parse_review(json.dumps({"issues": [issue]}))

    def test_malformed_review_is_not_acceptance(self):
        for raw in ['{}', '[]', '{"issues": "none"}', '{"issues": [], "approved": true}', 'not JSON']:
            with self.assertRaises(ValueError):
                parse_review(raw)

    def test_wrong_script_detected_across_all_fields(self):
        answer = {"key_point": "Cần đo.", "keywords": [], "framework_steps": ["不提供實驗數據"]}
        self.assertEqual(deterministic_issues("Hiệu quả học thế nào?", answer)[0]["code"], "wrong_language")
        self.assertEqual(deterministic_issues("實驗數據 là gì?", answer), [])

    def test_technical_terms_not_wrong_script(self):
        self.assertEqual(deterministic_issues("Độ trễ?", {"key_point": "Cần đo p95 và p99.", "keywords": ["API"]}), [])

    def test_absence_of_evidence_cannot_be_negative_technology_claim(self):
        answer = {"key_point": "Chưa có bằng chứng dùng Redis.", "framework_steps": ["Hệ thống không dùng Redis."]}
        issues = deterministic_issues("Dùng Redis chứ?", answer, ["Không có thông tin công nghệ lưu trữ."])
        self.assertEqual(issues[0]["code"], "unsupported_claim")
        self.assertEqual(deterministic_issues("Dùng Redis chứ?", answer, ["Hệ thống không dùng Redis."]), [])

    def test_unseen_endpoint_path_is_not_invented(self):
        answer = {"key_point": "Gửi POST /api/change_id để sửa."}
        self.assertEqual(deterministic_issues("Kiểm thử sửa ID?", answer)[0]["code"], "unsupported_claim")

    def test_rejecting_a_negative_conclusion_is_not_itself_a_negative_claim(self):
        for point in ["Chưa có bằng chứng, không được kết luận là không dùng Redis.",
                      "Chưa thể xác nhận hệ thống không dùng Redis.",
                      "Không đủ cơ sở để nói sản phẩm không dùng Redis.",
                      "Khẳng định “không dùng Redis” chưa được chứng minh.",
                      "Khẳng định “hệ thống không dùng Redis” là chưa có cơ sở."]:
            self.assertEqual(deterministic_issues("Dùng Redis?", {"key_point": point}), [])

    def test_proposal_in_steps_does_not_excuse_unsupported_policy_in_key_point(self):
        answer = {"key_point": "Học sinh có quyền giải trình.", "framework_steps": ["Đề xuất cơ chế giải trình."]}
        self.assertEqual(deterministic_issues("Có giải trình không?", answer)[0]["code"], "unsupported_claim")
        self.assertEqual(deterministic_issues("Có giải trình không?", {"key_point": "Đề xuất: học sinh có quyền giải trình."}), [])
        self.assertEqual(deterministic_issues("Có giải trình không?", answer, ["Học sinh có quyền giải trình."]), [])
