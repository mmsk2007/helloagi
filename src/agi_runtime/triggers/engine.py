from dataclasses import dataclass


@dataclass
class TriggerRule:
    keyword: str
    action: str


class TriggerEngine:
    def __init__(self):
        self.rules: list[TriggerRule] = []

    def add_rule(self, keyword: str, action: str):
        self.rules.append(TriggerRule(keyword=keyword, action=action))

    def evaluate(self, text: str) -> list[str]:
        t = text.lower()
        return [r.action for r in self.rules if r.keyword.lower() in t]
