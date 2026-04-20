"""SRG policy coverage for send_file / send_image."""

from pathlib import Path

import pytest

from agi_runtime.governance.srg import SRGGovernor


class _FakeSettings:
    def __init__(self, workspace: str, max_bytes: int = 20 * 1024 * 1024,
                 allowed=("txt", "md", "png", "pdf")):
        self.file_send_workspace = workspace
        self.max_outbound_file_bytes = max_bytes
        self.allowed_outbound_extensions = allowed


def test_path_inside_workspace_with_allowed_ext_is_allowed(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("ok")
    gov = SRGGovernor(settings=_FakeSettings(str(tmp_path)))
    res = gov.evaluate_tool("send_file", {"path": str(f)}, tool_risk="medium")
    assert res.decision == "allow"


def test_path_outside_workspace_escalates(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("sneaky")
    gov = SRGGovernor(settings=_FakeSettings(str(workspace)))
    res = gov.evaluate_tool("send_file", {"path": str(outside)}, tool_risk="medium")
    assert res.decision in {"escalate", "deny"}
    assert any("outside-workspace" in r for r in res.reasons)


def test_disallowed_extension_escalates(tmp_path):
    f = tmp_path / "danger.exe"
    f.write_text("x")
    gov = SRGGovernor(settings=_FakeSettings(str(tmp_path)))
    res = gov.evaluate_tool("send_file", {"path": str(f)}, tool_risk="medium")
    assert res.decision in {"escalate", "deny"}
    assert any("disallowed-ext" in r for r in res.reasons)


def test_secret_filename_escalates(tmp_path):
    f = tmp_path / ".env"
    f.write_text("API_KEY=xxx")
    gov = SRGGovernor(settings=_FakeSettings(str(tmp_path)))
    res = gov.evaluate_tool("send_file", {"path": str(f)}, tool_risk="medium")
    assert res.decision in {"escalate", "deny"}
    assert any("secret-name-pattern" in r for r in res.reasons)


def test_oversize_file_escalates(tmp_path):
    f = tmp_path / "big.txt"
    f.write_bytes(b"x" * 1024)
    gov = SRGGovernor(settings=_FakeSettings(str(tmp_path), max_bytes=512))
    res = gov.evaluate_tool("send_file", {"path": str(f)}, tool_risk="medium")
    assert res.decision in {"escalate", "deny"}
    assert any("oversize" in r for r in res.reasons)


def test_send_image_url_is_allowed_without_path_checks(tmp_path):
    gov = SRGGovernor(settings=_FakeSettings(str(tmp_path)))
    res = gov.evaluate_tool(
        "send_image",
        {"path_or_url": "https://example.com/cat.png"},
        tool_risk="medium",
    )
    assert res.decision == "allow"
