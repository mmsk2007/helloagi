from dataclasses import dataclass


@dataclass
class OpenClawTask:
    summary: str
    requires_human_confirm: bool = False


def to_openclaw_task(response_text: str, decision: str) -> OpenClawTask:
    return OpenClawTask(
        summary=response_text,
        requires_human_confirm=(decision == "escalate"),
    )
