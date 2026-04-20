import asyncio
import time

from agi_runtime.channels.telegram import TelegramChannel
from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent


class _Msg:
    def __init__(self, text: str = ""):
        self.calls = []
        self.text = text

    async def reply_text(self, text, **kwargs):
        self.calls.append({"text": text, "kwargs": kwargs})


class _User:
    id = 1


class _Chat:
    id = 2
    type = "private"


class _Update:
    def __init__(self, text: str = ""):
        self.effective_user = _User()
        self.effective_chat = _Chat()
        self.message = _Msg(text=text)


def test_start_command_plain_text_avoids_markdown_fragility():
    settings = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    agent = HelloAGIAgent(settings=settings)
    channel = TelegramChannel(agent=agent, token="dummy")
    update = _Update(text="what can you do")

    asyncio.run(channel._cmd_start(update, context=None))

    assert update.message.calls
    payload = update.message.calls[0]
    assert "parse_mode" not in payload["kwargs"]
    assert "*HelloAGI" not in payload["text"]


def test_busy_telegram_principal_gets_immediate_busy_reply():
    settings = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    agent = HelloAGIAgent(settings=settings)
    channel = TelegramChannel(agent=agent, token="dummy")
    update = _Update(text="check the status")
    principal_id = channel._principal_id_for_update(update)
    agent.principals.update(principal_id, onboarded=True, preferred_name="Alex")
    channel._inflight_by_principal[principal_id] = {
        "started_at": time.monotonic() - 5.0,
        "preview": "check flights to DXB",
    }

    asyncio.run(channel._handle_message(update, context=None))

    assert update.message.calls
    payload = update.message.calls[0]
    assert "still working on your previous task" in payload["text"]
    assert "check flights to DXB" in payload["text"]
