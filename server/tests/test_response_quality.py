import unittest
from services.response_quality import missing_requested_example


class ResponseQualityTests(unittest.TestCase):
    def test_definition_does_not_satisfy_example_request(self):
        self.assertTrue(missing_requested_example("Cho một ví dụ", {"key_point": "Đã nhận nhưng chưa xử lý."}))

    def test_vietnamese_but_is_not_like(self):
        self.assertTrue(missing_requested_example("Lấy ví dụ", {"key_point": "Đã nhận nhưng chưa xử lý."}))
        self.assertFalse(missing_requested_example("Lấy ví dụ", {"key_point": "Giống như người đang xếp hàng."}))

    def test_no_example_required_when_user_opts_out(self):
        self.assertFalse(missing_requested_example("Không cần ví dụ", {"key_point": "Định nghĩa."}))
        self.assertFalse(missing_requested_example("Explain without an example", {"key_point": "Definition."}))

    def test_example_in_supporting_point_counts(self):
        self.assertFalse(missing_requested_example("Give an example", {"key_point": "Definition.", "framework_steps": ["For example, people waiting their turn."]}))
