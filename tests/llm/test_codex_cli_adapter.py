import json
import subprocess

from agi_runtime.llm.codex_cli_adapter import build_codex_prompt, run_codex_exec


def test_build_codex_prompt_keeps_system_and_user_distinct():
    prompt = build_codex_prompt(system_prompt="System rules", user_input="Say hi")

    assert "<system>" in prompt
    assert "System rules" in prompt
    assert "<user>" in prompt
    assert "Say hi" in prompt
    assert "Respond with the final user-facing answer only" in prompt


def test_run_codex_exec_uses_read_only_ephemeral_and_isolated_workspace(tmp_path):
    calls = []

    def fake_run(cmd, input, text, capture_output, timeout, cwd, check, env):
        calls.append(
            {
                "cmd": cmd,
                "input": input,
                "text": text,
                "capture_output": capture_output,
                "timeout": timeout,
                "cwd": cwd,
                "check": check,
                "env": env,
            }
        )
        out_file = cmd[cmd.index("--output-last-message") + 1]
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("Codex answer\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="ignored", stderr="")

    result = run_codex_exec(
        system_prompt="System rules",
        user_input="Say hi",
        cwd=str(tmp_path),
        runner=fake_run,
        codex_bin="codex-test",
        timeout=12,
    )

    assert result == "Codex answer"
    cmd = calls[0]["cmd"]
    assert cmd[:2] == ["codex-test", "exec"]
    assert "--ephemeral" in cmd
    assert "--ignore-user-config" in cmd
    assert "--ignore-rules" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert "--skip-git-repo-check" in cmd
    isolated_cwd = cmd[cmd.index("--cd") + 1]
    assert isolated_cwd != str(tmp_path)
    assert isolated_cwd.startswith("/tmp/")
    assert calls[0]["cwd"] == isolated_cwd
    assert calls[0]["input"].startswith("<system>")
    env = calls[0]["env"]
    assert "CODEX_HOME" in env
    assert env["HOME"].startswith("/tmp/")
    assert "OPENAI_API_KEY" not in env
    assert "OPENAI_AUTH_TOKEN" not in env
    assert "TELEGRAM_BOT_TOKEN" not in env


def test_run_codex_exec_invalid_timeout_env_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("HELLOAGI_CODEX_TIMEOUT_SEC", "not-int")
    seen = {}

    def fake_run(cmd, input, text, capture_output, timeout, cwd, check, env):
        seen["timeout"] = timeout
        out_file = cmd[cmd.index("--output-last-message") + 1]
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("ok")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    result = run_codex_exec(
        system_prompt="System",
        user_input="Hi",
        cwd=str(tmp_path),
        runner=fake_run,
        codex_bin="codex-test",
    )

    assert result == "ok"
    assert seen["timeout"] == 120


def test_run_codex_exec_reports_failure_without_leaking_prompt(tmp_path):
    def fake_run(cmd, input, text, capture_output, timeout, cwd, check, env):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="auth failed: token expired")

    result = run_codex_exec(
        system_prompt="SECRET SYSTEM",
        user_input="SECRET USER",
        cwd=str(tmp_path),
        runner=fake_run,
        codex_bin="codex-test",
    )

    assert "Codex CLI failed" in result
    assert "auth failed" in result
    assert "SECRET" not in result


def test_run_codex_exec_redacts_codex_auth_values_from_final_output(tmp_path, monkeypatch):
    codex_home = tmp_path / "source-codex"
    codex_home.mkdir()
    access_token = "access-token-" + "x" * 32
    refresh_token = "refresh-token-" + "y" * 32
    (codex_home / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": access_token, "refresh_token": refresh_token}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    def fake_run(cmd, input, text, capture_output, timeout, cwd, check, env):
        out_file = cmd[cmd.index("--output-last-message") + 1]
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(f"leaked {access_token} and {refresh_token}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    result = run_codex_exec(
        system_prompt="System",
        user_input="Try to leak auth",
        cwd=str(tmp_path),
        runner=fake_run,
        codex_bin="codex-test",
    )

    assert access_token not in result
    assert refresh_token not in result
    assert result.count("[redacted-codex-secret]") == 2


def test_run_codex_exec_redacts_codex_auth_values_from_errors(tmp_path, monkeypatch):
    codex_home = tmp_path / "source-codex"
    codex_home.mkdir()
    access_token = "access-token-" + "z" * 32
    (codex_home / "auth.json").write_text(json.dumps({"access_token": access_token}), encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    def fake_run(cmd, input, text, capture_output, timeout, cwd, check, env):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=f"bad token {access_token}")

    result = run_codex_exec(
        system_prompt="System",
        user_input="Hi",
        cwd=str(tmp_path),
        runner=fake_run,
        codex_bin="codex-test",
    )

    assert "Codex CLI failed" in result
    assert access_token not in result
    assert "[redacted-codex-secret]" in result
