import unittest

from services.live_caption import should_emit


class LiveCaptionTests(unittest.TestCase):
    def test_emits_only_when_there_is_new_audio_and_new_text(self):
        self.assertFalse(should_emit(2.0, "", "old"))          # nothing recognised
        self.assertFalse(should_emit(0.2, "xin chào", "old"))  # not enough new audio
        self.assertFalse(should_emit(2.0, "xin chào", "xin chào"))  # unchanged
        self.assertTrue(should_emit(2.0, "xin chào", "xin"))
        self.assertTrue(should_emit(2.0, "  xin chào  ", ""))

    def test_whitespace_only_transcript_is_not_emitted(self):
        self.assertFalse(should_emit(5.0, "   ", ""))


if __name__ == "__main__":
    unittest.main()
