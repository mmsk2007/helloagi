from concurrent.futures import Future

import asyncio
from pathlib import Path
import tempfile

from agi_runtime.tools.builtins.send_voice_tool import send_voice
from agi_runtime.tools.registry import reset_tool_context, set_tool_context


class _RunningLoop:
    def is_running(self):
        return True


class _VoiceCapableChannel:
    capabilities = frozenset({"text", "voice", "file"})
    _loop = _RunningLoop()

    def __init__(self, name: str = "test-voice"):
        self.name = name
        self.last_path = None

    async def send_voice(self, channel_id: str, path: str, caption: str = ""):
        self.last_path = path
        return {"ok": True, "message_id": "1", "error": None}


class _FileOnlyChannel:
    name = "test-file"
    capabilities = frozenset({"text", "file"})
    _loop = _RunningLoop()

    def __init__(self):
        self.last_path = None
        self.last_filename = None

    async def send_file(self, channel_id: str, path: str, caption: str = "", filename: str = ""):
        self.last_path = path
        self.last_filename = filename
        return {"ok": True, "message_id": "2", "error": None}


def _completed(result):
    future = Future()
    future.set_result(result)
    return future


def test_send_voice_requires_active_channel(monkeypatch):
    monkeypatch.setattr(
        "agi_runtime.tools.builtins.send_voice_tool._synthesize_wav_bytes",
        lambda text, style_hint="default": b"wav",
    )
    token = set_tool_context(channel=None, channel_id=None)
    try:
        result = send_voice("hello")
    finally:
        reset_tool_context(token)
    assert result.ok is False
    assert "no active channel" in (result.error or "")


def test_send_voice_uses_voice_capability(monkeypatch):
    channel = _VoiceCapableChannel()
    monkeypatch.setattr(
        "agi_runtime.tools.builtins.send_voice_tool._synthesize_wav_bytes",
        lambda text, style_hint="default": b"wav",
    )

    def _fake_run(coro, loop):
        return _completed(asyncio.run(coro))

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _fake_run)
    monkeypatch.setattr(
        "agi_runtime.tools.builtins.send_voice_tool._prepare_voice_asset",
        lambda channel, wav_bytes: (Path(tempfile.gettempdir()) / "helloagi-test.wav", False),
    )
    token = set_tool_context(channel=channel, channel_id="123")
    try:
        result = send_voice("hello")
    finally:
        reset_tool_context(token)
    assert result.ok is True
    assert "delivered voice note" in result.output
    assert channel.last_path.endswith(".wav")


def test_send_voice_uses_ogg_for_telegram(monkeypatch):
    channel = _VoiceCapableChannel(name="telegram")
    monkeypatch.setattr(
        "agi_runtime.tools.builtins.send_voice_tool._synthesize_wav_bytes",
        lambda text, style_hint="default": b"wav",
    )

    def _fake_run(coro, loop):
        return _completed(asyncio.run(coro))

    ogg_path = Path(tempfile.gettempdir()) / "helloagi-test.ogg"
    ogg_path.write_bytes(b"ogg")
    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _fake_run)
    monkeypatch.setattr(
        "agi_runtime.tools.builtins.send_voice_tool._prepare_voice_asset",
        lambda channel, wav_bytes: (ogg_path, True),
    )
    token = set_tool_context(channel=channel, channel_id="123")
    try:
        result = send_voice("hello")
    finally:
        reset_tool_context(token)
    assert result.ok is True
    assert channel.last_path.endswith(".ogg")
    assert not ogg_path.exists()


def test_send_voice_falls_back_to_file_delivery(monkeypatch):
    channel = _FileOnlyChannel()
    monkeypatch.setattr(
        "agi_runtime.tools.builtins.send_voice_tool._synthesize_wav_bytes",
        lambda text, style_hint="default": b"wav",
    )

    def _fake_run(coro, loop):
        return _completed(asyncio.run(coro))

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _fake_run)
    monkeypatch.setattr(
        "agi_runtime.tools.builtins.send_voice_tool._prepare_voice_asset",
        lambda channel, wav_bytes: (Path(tempfile.gettempdir()) / "helloagi-test.wav", False),
    )
    token = set_tool_context(channel=channel, channel_id="123")
    try:
        result = send_voice("hello")
    finally:
        reset_tool_context(token)
    assert result.ok is True
    assert "delivered voice note" in result.output
    assert channel.last_filename == "helloagi-voice.wav"
