import json
import tempfile
import unittest
from pathlib import Path

from services.vocab_bias import compose_prompt, extract_terms, load_vocab, store_vocab


class VocabBiasTests(unittest.TestCase):
    def test_extracts_technical_tokens_by_frequency(self):
        texts = [
            "ShieldCall dùng FAISS và faster-whisper để tìm kiếm.",
            "Cấu hình FAISS nằm trong settings.py, Celery dùng Redis.",
            "the quick brown fox jumps",
        ]
        terms = extract_terms(texts, limit=10)
        self.assertIn("FAISS", terms)
        self.assertIn("Redis", terms)
        self.assertIn("settings.py", terms)
        self.assertNotIn("the", terms)      # stopword
        self.assertNotIn("quick", terms)    # not technical-looking

    def test_strong_terms_rank_above_markup_noise(self):
        texts = ["background-color: red; box-shadow: none;"] * 20 + ["Dùng FAISS để tìm kiếm."]
        terms = extract_terms(texts, limit=5)
        self.assertEqual(terms[0], "FAISS")
        self.assertIn("background-color", terms)  # still present, just lower

    def test_compose_prompt_appends_and_caps(self):
        self.assertEqual(compose_prompt("base", []), "base")
        self.assertEqual(compose_prompt("base,", ["FAISS", "Redis"]), "base, FAISS, Redis")
        self.assertEqual(compose_prompt("", ["A", "B"]), "A, B")
        self.assertLessEqual(len(compose_prompt("x" * 100, ["y" * 100], max_chars=50)), 50)

    def test_store_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "vocab.json")
            self.assertEqual(load_vocab(path), [])
            store_vocab(path, ["FAISS", "Docker"])
            self.assertEqual(load_vocab(path), ["FAISS", "Docker"])
            self.assertEqual(json.loads(Path(path).read_text(encoding="utf-8"))["terms"], ["FAISS", "Docker"])


if __name__ == "__main__":
    unittest.main()
