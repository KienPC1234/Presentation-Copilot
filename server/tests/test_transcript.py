import unittest

from services.transcript import collapse_repetitions


class TranscriptCleanupTests(unittest.TestCase):
    def test_repeated_sentence_is_collapsed(self):
        text = ("Anh chị nói hệ thống chạy local first để bảo vệ dữ liệu người dùng. "
                "Nhưng bộ đánh giá nội bộ chỉ có 88 mẫu tự gán nhãn. "
                "Anh chị nói hệ thống chạy local first để bảo vệ dữ liệu người dùng.")
        cleaned = collapse_repetitions(text)
        self.assertEqual(cleaned.count("chạy local first"), 1)
        self.assertIn("88 mẫu", cleaned)

    def test_distinct_sentences_are_kept(self):
        text = "Vì sao chọn FAISS? Đã đo độ trễ chưa? Kế hoạch đo là gì?"
        self.assertEqual(collapse_repetitions(text), text)

    def test_case_and_punctuation_insensitive_match(self):
        text = "Do you use FAISS? do you use faiss!"
        self.assertEqual(collapse_repetitions(text), "Do you use FAISS?")

    def test_empty_input(self):
        self.assertEqual(collapse_repetitions(""), "")


if __name__ == "__main__":
    unittest.main()
