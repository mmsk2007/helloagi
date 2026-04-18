import asyncio

from agi_runtime.channels.telegram import TelegramChannel
from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.reminders.service import ReminderService
from agi_runtime.reminders.store import ReminderStore


class _Msg:
    def __init__(self):
        self.calls = []
        self.text = ""

    async def reply_text(self, text, **kwargs):
        self.calls.append({"text": text, "kwargs": kwargs})


class _User:
    id = 123


class _Chat:
    id = 123
    type = "private"


class _Update:
    def __init__(self):
        self.effective_user = _User()
        self.effective_chat = _Chat()
        self.message = _Msg()


class _Ctx:
    def __init__(self, args):
        self.args = args


def _build_channel(tmp_path):
    settings = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    agent = HelloAGIAgent(settings=settings)
    ch = TelegramChannel(agent=agent, token="dummy")
    ch._reminder_service = ReminderService(ReminderStore(path=str(tmp_path / "reminders.json")))
    return ch


def test_cmd_remind_and_list(tmp_path):
    channel = _build_channel(tmp_path)
    update = _Update()
    asyncio.run(channel._cmd_remind(update, _Ctx(["in", "30m", "|", "test", "message"])))
    assert update.message.calls
    assert "Created reminder" in update.message.calls[-1]["text"]

    update2 = _Update()
    asyncio.run(channel._cmd_reminders(update2, _Ctx([])))
    assert update2.message.calls
    assert "test message" in update2.message.calls[-1]["text"]

