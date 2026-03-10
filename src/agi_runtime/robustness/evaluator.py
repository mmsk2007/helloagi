from dataclasses import dataclass
from difflib import SequenceMatcher
from agi_runtime.robustness.noisecore_adapter import encode_noisecore, decode_noisecore


@dataclass
class RobustnessReport:
    consistency: float
    recovered_text: str
    noisy_text: str


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def evaluate_consistency(text: str) -> RobustnessReport:
    noisy = encode_noisecore(text, level=2)
    recovered = decode_noisecore(noisy)
    a = _normalize(text)
    b = _normalize(recovered)
    score = SequenceMatcher(None, a, b).ratio() if a else 0.0
    return RobustnessReport(consistency=score, recovered_text=recovered, noisy_text=noisy)
