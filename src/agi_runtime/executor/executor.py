from dataclasses import dataclass


@dataclass
class ExecResult:
    ok: bool
    outputs: list[str]


class Executor:
    def run(self, steps: list[str]) -> ExecResult:
        outputs = [f"executed: {s}" for s in steps]
        return ExecResult(ok=True, outputs=outputs)
