import unittest

from services.audio_buffer import append_chunk, snapshot


class AudioBufferTests(unittest.TestCase):
    def test_sliding_window_keeps_the_newest_bytes(self):
        buffer = bytearray(b"aaaa")
        self.assertFalse(append_chunk(buffer, b"bb", 6))
        self.assertEqual(bytes(buffer), b"aaaabb")
        self.assertTrue(append_chunk(buffer, b"cc", 6))
        self.assertEqual(bytes(buffer), b"aabbcc")

    def test_oversized_chunk_truncates_from_the_front(self):
        buffer = bytearray(b"old")
        self.assertTrue(append_chunk(buffer, b"0123456789", 4))
        self.assertEqual(bytes(buffer), b"6789")

    def test_zero_limit_clears(self):
        buffer = bytearray(b"data")
        self.assertTrue(append_chunk(buffer, b"", 0))
        self.assertEqual(bytes(buffer), b"")

    def test_snapshot_takes_the_requested_tail_and_clears(self):
        buffer = bytearray(bytes(range(100)))
        # 16000 Hz * 2 bytes * 1 s would be 32000 bytes; use a tiny rate to test the math.
        window = snapshot(buffer, seconds=2, sample_rate=10)  # 40 bytes
        self.assertEqual(len(window), 40)
        self.assertEqual(bytes(window), bytes(range(60, 100)))
        self.assertEqual(len(buffer), 0)

    def test_snapshot_without_seconds_keeps_everything(self):
        buffer = bytearray(b"current question")
        window = snapshot(buffer, seconds=None, sample_rate=16000)
        self.assertEqual(bytes(window), b"current question")
        self.assertEqual(len(buffer), 0)

    def test_snapshot_window_larger_than_buffer(self):
        buffer = bytearray(b"short")
        window = snapshot(buffer, seconds=90, sample_rate=16000)
        self.assertEqual(bytes(window), b"short")


if __name__ == "__main__":
    unittest.main()
