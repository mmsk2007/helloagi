import asyncio

from agi_runtime.channels.telegram import TelegramChannel
from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent


class _Msg:
    def __init__(self):
        self.calls = []

    async def reply_text(self, text, **kwargs):
        self.calls.append({"text": text, "kwargs": kwargs})


class _User:
    id = 1


class _Chat:
    id = 2
    type = "private"


class _Update:
    def __init__(self):
        self.effective_user = _User()
        self.effective_chat = _Chat()
        self.message = _Msg()


def test_start_command_plain_text_avoids_markdown_fragility():
    settings = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    agent = HelloAGIAgent(settings=settings)
    channel = TelegramChannel(agent=agent, token="dummy")
    update = _Update()

    asyncio.run(channel._cmd_start(update, context=None))

    assert update.message.calls
    payload = update.message.calls[0]
    assert "parse_mode" not in payload["kwargs"]
    assert "*HelloAGI" not in payload["text"]

