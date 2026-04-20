"""send_file/send_image must degrade gracefully when no channel can deliver attachments."""

from pathlib import Path

import pytest

from agi_runtime.tools.builtins.send_file_tool import send_file
from agi_runtime.tools.builtins.send_image_tool import send_image
from agi_runtime.tools.registry import set_tool_context, reset_tool_context


class _TextOnlyChannel:
    name = "test-text-only"
    capabilities = frozenset({"text"})
    _loop = None


class _FileCapableChannel:
    name = "test-file"
    capabilities = frozenset({"text", "file", "image"})
    _loop = None  # tool will report loop-not-running before any await happens


def test_send_file_returns_text_fallback_when_channel_lacks_capability(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("hi")
    token = set_tool_context(channel=_TextOnlyChannel(), channel_id="123")
    try:
        result = send_file(str(f))
    finally:
        reset_tool_context(token)
    assert result.ok is True
    assert "[file ready]" in result.output
    assert str(f) in result.output


def test_send_file_returns_text_fallback_when_no_channel_active(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("hi")
    token = set_tool_context(channel=None, channel_id=None)
    try:
        result = send_file(str(f))
    finally:
        reset_tool_context(token)
    assert result.ok is True
    assert "[file ready]" in result.output


def test_send_file_missing_file_errors(tmp_path):
    token = set_tool_context(channel=None, channel_id=None)
    try:
        result = send_file(str(tmp_path / "does_not_exist.txt"))
    finally:
        reset_tool_context(token)
    assert result.ok is False
    assert "file not found" in (result.error or "")


def test_send_image_text_fallback_for_url_in_text_only_channel():
    token = set_tool_context(channel=_TextOnlyChannel(), channel_id="123")
    try:
        result = send_image("https://example.com/cat.png")
    finally:
        reset_tool_context(token)
    assert result.ok is True
    assert "[image ready]" in result.output


def test_send_file_reports_when_channel_loop_not_running(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("hi")
    token = set_tool_context(channel=_FileCapableChannel(), channel_id="123")
    try:
        result = send_file(str(f))
    finally:
        reset_tool_context(token)
    assert result.ok is False
    assert "event loop" in (result.error or "")
