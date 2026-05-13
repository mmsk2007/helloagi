"""ServiceManager.doctor / reinstall helpers."""

import tempfile
from pathlib import Path

from agi_runtime.service.manager import ServiceConfig, ServiceManager


def test_doctor_when_not_installed():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "state.json"
        sm = ServiceManager(state_path=str(p), native_control=False)
        d = sm.doctor()
        assert d["installed"] is False
        assert d["ok"] is True
        assert d["issues"] == []


def test_doctor_detects_missing_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "state.json"
        sm = ServiceManager(state_path=str(p), native_control=False)
        cfg = ServiceConfig(
            installed=True,
            native_registered=True,
            manifest_path=str(Path(tmp) / "nonexistent.service"),
            workdir=tmp,
            backend="systemd-user",
        )
        sm.save(cfg)
        d = sm.doctor()
        assert "manifest_missing" in d["issues"]
        assert d["ok"] is False


def test_doctor_windows_detached_service_notes_without_native_registration():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "state.json"
        manifest = Path(tmp) / "run-helloagi-service.cmd"
        manifest.write_text("python command", encoding="utf-8")
        sm = ServiceManager(state_path=str(p), platform_name="windows", native_control=False)
        cfg = ServiceConfig(
            installed=True,
            native_registered=False,
            manifest_path=str(manifest),
            workdir=tmp,
            backend="windows-task",
        )
        sm.save(cfg)

        d = sm.doctor()

        assert "native_not_registered" not in d["issues"]
        assert d["notes"]
        assert any("Task Scheduler is off by default" in note for note in d["notes"])


def test_reinstall_requires_prior_install():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "state.json"
        sm = ServiceManager(state_path=str(p), native_control=False)
        try:
            sm.reinstall()
        except RuntimeError as e:
            assert "not installed" in str(e).lower()
        else:
            raise AssertionError("expected RuntimeError")
