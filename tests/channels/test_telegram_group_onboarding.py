from agi_runtime.channels.telegram import TelegramChannel
from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent


class _Msg:
    def __init__(self, text="hello"):
        self.text = text
        self.calls = []
        self.message_id = 1

    async def reply_text(self, text, **kwargs):
        self.calls.append({"text": text, "kwargs": kwargs})


class _User:
    def __init__(self, user_id=123, first_name="Admin"):
        self.id = user_id
        self.first_name = first_name


class _Chat:
    def __init__(self, chat_id=-100123, chat_type="group"):
        self.id = chat_id
        self.type = chat_type


class _Update:
    def __init__(self, *, user=None, chat=None, text="hello"):
        self.effective_user = user or _User()
        self.effective_chat = chat or _Chat()
        self.message = _Msg(text)


def _channel(tmp_path):
    settings = RuntimeSettings(
        memory_path=str(tmp_path / "identity_state.json"),
        journal_path=str(tmp_path / "events.jsonl"),
    )
    agent = HelloAGIAgent(settings=settings)
    return TelegramChannel(agent=agent, token="dummy")


def test_group_principal_links_to_completed_dm_profile(tmp_path):
    channel = _channel(tmp_path)
    user = _User(user_id=777, first_name="Admin")
    dm_pid = "telegram:dm:777"
    group_pid = "telegram:group:-100999:user:777"
    channel.agent.principals.update(
        dm_pid,
        preferred_name="Admin",
        timezone="Asia/Dubai",
        city="Dubai",
        onboarded=True,
        bootstrap_completed=True,
    )

    update = _Update(user=user, chat=_Chat(-100999, "group"), text="normal group conversation")
    state = channel._prepare_principal_for_message(update)

    assert state.onboarded is True
    assert state.preferred_name == "Admin"
    assert state.timezone == "Asia/Dubai"
    assert channel.agent.principals.get(group_pid).principal_id == dm_pid


def test_group_principal_auto_onboards_without_wizard(tmp_path):
    channel = _channel(tmp_path)
    update = _Update(user=_User(user_id=888, first_name="Zillionaire"), chat=_Chat(-100888, "supergroup"))

    state = channel._prepare_principal_for_message(update)

    assert state.onboarded is True
    assert state.bootstrap_completed is True
    assert state.preferred_name == "Zillionaire"
    assert "888" not in channel._wizard_state
