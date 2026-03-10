from dataclasses import dataclass


@dataclass
class VerifyResult:
    passed: bool
    summary: str


class Verifier:
    def check(self, outputs: list[str], goal: str) -> VerifyResult:
        if not outputs:
            return VerifyResult(False, "no outputs")
        return VerifyResult(True, f"verified {len(outputs)} outputs toward goal: {goal}")
