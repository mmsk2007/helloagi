"""OutputGuard tests.

The guard is the post-execution SRG surface: it inspects text leaving the
runtime (tool outputs, agent final responses) and emits allow / redact /
deny. The tests pin three properties:

1. Hard-deny patterns (real API keys, private keys) fire.
2. Redact-severity patterns mutate the text rather than blocking.
3. Phantom-action detection fires only when tool_calls_made == 0.
"""

from __future__ import annotations

import unittest

from agi_runtime.governance.output_guard import OutputGuard


class TestHardDeny(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = OutputGuard()

    def test_detects_anthropic_api_key(self) -> None:
        result = self.guard.inspect(
            "Here is the key: sk-ant-abcdef1234567890abcdef1234567890"
        )
        self.assertEqual(result.decision, "deny")
        self.assertTrue(
            any("anthropic-api-key" in r for r in result.reasons)
        )

    def test_detects_aws_access_key(self) -> None:
        result = self.guard.inspect("AWS key: AKIAIOSFODNN7EXAMPLE")
        self.assertEqual(result.decision, "deny")

    def test_detects_private_key_block(self) -> None:
        result = self.guard.inspect(
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
        )
        self.assertEqual(result.decision, "deny")

    def test_detects_etc_passwd_dump(self) -> None:
        result = self.guard.inspect(
            "Contents of /etc/passwd:\nroot:x:0:0:root:/root:/bin/bash"
        )
        self.assertEqual(result.decision, "deny")

    def test_detects_env_var_value(self) -> None:
        result = self.guard.inspect(
            "The runtime has ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx"
        )
        self.assertEqual(result.decision, "deny")


class TestRedaction(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = OutputGuard()

    def test_env_dump_is_redacted_not_denied(self) -> None:
        text = (
            "PATH=/usr/bin\nHOME=/root\nUSER=admin\nSHELL=/bin/bash\n"
            "LANG=en_US.UTF-8\nTERM=xterm-256color"
        )
        result = self.guard.inspect(text)
        self.assertEqual(result.decision, "redact")
        self.assertIsNotNone(result.redacted_text)
        # At least one original env line should be gone from the redacted
        # output. We don't assert exact shape because the regex catches
        # the whole block; we just require a change happened.
        self.assertNotEqual(result.redacted_text, text)

    def test_password_assignment_is_redacted(self) -> None:
        result = self.guard.inspect("config: password=hunter2swordfish")
        self.assertEqual(result.decision, "redact")
        self.assertIn("REDACTED", (result.redacted_text or ""))


class TestPhantomActions(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = OutputGuard()

    def test_phantom_detected_when_zero_tool_calls(self) -> None:
        # The agent claims to have sent an email, but zero tools were
        # invoked. That's a hallucinated action.
        result = self.guard.inspect(
            "Done — I sent the email to the team.",
            tool_calls_made=0,
        )
        self.assertEqual(result.decision, "redact")
        self.assertIn("phantom-action", result.reasons)

    def test_phantom_not_flagged_when_tools_were_used(self) -> None:
        # Same text, but a tool *was* invoked — the claim is plausibly
        # grounded, so we don't interfere.
        result = self.guard.inspect(
            "Done — I sent the email to the team.",
            tool_calls_made=1,
        )
        self.assertEqual(result.decision, "allow")

    def test_phantom_not_flagged_without_tool_count(self) -> None:
        # If the caller doesn't provide a count, phantom detection is
        # skipped entirely (e.g., inspecting a tool result directly).
        result = self.guard.inspect(
            "I sent the email.", tool_calls_made=None,
        )
        self.assertEqual(result.decision, "allow")


class TestBenignContent(unittest.TestCase):
    def test_clean_prose_is_allowed(self) -> None:
        result = OutputGuard().inspect(
            "The checkout latency dropped by 18% after the index change."
        )
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.signal_count, 0)

    def test_empty_text_is_allowed(self) -> None:
        result = OutputGuard().inspect("")
        self.assertEqual(result.decision, "allow")


if __name__ == "__main__":
    unittest.main()
