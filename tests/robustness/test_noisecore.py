import unittest
from agi_runtime.robustness.noisecore_adapter import encode_noisecore, decode_noisecore


class TestNoisecore(unittest.TestCase):
    def test_encode_decode_roundtrip_nonempty(self):
        text = "hello how are you"
        enc = encode_noisecore(text, level=2)
        dec = decode_noisecore(enc)
        self.assertTrue(enc)
        self.assertTrue(dec)


if __name__ == '__main__':
    unittest.main()
