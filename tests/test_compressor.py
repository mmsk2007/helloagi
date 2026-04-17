"""Tests for the context compression module."""

import unittest

from agi_runtime.memory.compressor import ContextCompressor


class TestContextCompressor(unittest.TestCase):
    def setUp(self):
        self.comp = ContextCompressor()

    def test_short_history_no_compression(self):
        history = [{"role": "user", "content": "hello"}]
        assert self.comp.needs_compression(history) is False

    def test_long_history_needs_compression(self):
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i} " * 100}
            for i in range(40)
        ]
        assert self.comp.needs_compression(history) is True

    def test_empty_history(self):
        assert self.comp.needs_compression([]) is False

    def test_message_count_threshold(self):
        # 30+ messages should trigger
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(35)
        ]
        assert self.comp.needs_compression(history) is True


if __name__ == "__main__":
    unittest.main()
