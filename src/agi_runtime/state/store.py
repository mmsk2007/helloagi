from pathlib import Path
import json


class StateStore:
    def __init__(self, path: str = "memory/runtime_state.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        if not self.path.exists():
            return {"workflows": {}, "tasks": {}, "metrics": {}}
        return json.loads(self.path.read_text())

    def save(self, state: dict):
        self.path.write_text(json.dumps(state, indent=2))
