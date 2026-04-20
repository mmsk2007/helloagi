from concurrent.futures import Future

import asyncio

from agi_runtime.tools.builtins.send_voice_tool import send_voice
from agi_runtime.tools.registry import reset_tool_context, set_tool_context


class _RunningLoop:
    def is_running(self):
        return True


class _VoiceCapableChannel:
    name = "test-voice"
    capabilities = frozenset({"text", "voice", "file"})
    _loop = _RunningLoop()

    async def send_voice(self, channel_id: str, path: str, caption: str = ""):
        return {"ok": True, "message_id": "1", "error": None}


class _FileOnlyChannel:
    name = "test-file"
    capabilities = frozenset({"text", "file"})
    _loop = _RunningLoop()

    async def send_file(self, channel_id: str, path: str, caption: str = "", filename: str = ""):
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
    monkeypatch.setattr(
        "agi_runtime.tools.builtins.send_voice_tool._synthesize_wav_bytes",
        lambda text, style_hint="default": b"wav",
    )

    def _fake_run(coro, loop):
        coro.close()
        return _completed({"ok": True, "message_id": "1", "error": None})

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _fake_run)
    token = set_tool_context(channel=_VoiceCapableChannel(), channel_id="123")
    try:
        result = send_voice("hello")
    finally:
        reset_tool_context(token)
    assert result.ok is True
    assert "delivered voice note" in result.output


def test_send_voice_falls_back_to_file_delivery(monkeypatch):
    monkeypatch.setattr(
        "agi_runtime.tools.builtins.send_voice_tool._synthesize_wav_bytes",
        lambda text, style_hint="default": b"wav",
    )

    def _fake_run(coro, loop):
        coro.close()
        return _completed({"ok": True, "message_id": "2", "error": None})

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _fake_run)
    token = set_tool_context(channel=_FileOnlyChannel(), channel_id="123")
    try:
        result = send_voice("hello")
    finally:
        reset_tool_context(token)
    assert result.ok is True
    assert "delivered voice note" in result.output
