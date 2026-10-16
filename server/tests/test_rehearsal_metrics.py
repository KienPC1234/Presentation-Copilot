import unittest
from services.rehearsal_metrics import word_error_rate


class SpeechMetricTests(unittest.TestCase):
    def test_case_and_punctuation_normalized(self):
        self.assertEqual(word_error_rate("What is quality?", "what IS quality"), 0)

    def test_deleted_word_counts(self):
        self.assertAlmostEqual(word_error_rate("what is quality", "what quality"), 1 / 3)

    def test_insertions_can_exceed_one(self):
        self.assertEqual(word_error_rate("quality", "what is app quality"), 3)

    def test_missing_reference_is_not_a_score(self):
        with self.assertRaises(ValueError): word_error_rate("", "some words")
