"""Tests for the VLAA Reliability Layer (Milestone 3).

All tests use stubs and no API keys.
"""

from __future__ import annotations

import unittest
from agi_runtime.reliability.completion_verifier import CompletionVerifier
from agi_runtime.reliability.loop_breaker import LoopBreaker
from agi_runtime.reliability.recovery_manager import RecoveryManager
from agi_runtime.reliability.stop_validator import StopValidator


class TestCompletionVerifier(unittest.TestCase):
    def setUp(self):
        self.verifier = CompletionVerifier()

    def test_verify_empty(self):
        check = self.verifier.verify("")
        self.assertEqual(check.status, "verified")

    def test_verify_no_claims(self):
        check = self.verifier.verify("Hello, how can I help you?", tool_calls_made=0)
        self.assertEqual(check.status, "verified")
        self.assertEqual(check.claims_found, 0)

    def test_verify_phantom_claim(self):
        # Claims to have created a file but no tools were used
        text = "I've just created the file for you."
        check = self.verifier.verify(text, tool_calls_made=0)
        self.assertEqual(check.status, "phantom")
        self.assertGreater(check.claims_found, 0)
        self.assertEqual(check.claims_verified, 0)
        self.assertTrue(any(r.startswith("phantom:") for r in check.reasons))

    def test_verify_valid_claim(self):
        # Claims to have created a file and tool was used
        text = "I've created the script."
        check = self.verifier.verify(text, tool_calls_made=1, tools_used=["file_write"])
        self.assertEqual(check.status, "verified")
        self.assertEqual(check.claims_verified, 1)

    def test_verify_unverified_task_complete(self):
        text = "The task is complete."
        check = self.verifier.verify(text, tool_calls_made=0)
        self.assertEqual(check.status, "unverified")

    def test_verify_task_complete_with_tools(self):
        text = "The task is complete."
        check = self.verifier.verify(text, tool_calls_made=2)
        self.assertEqual(check.status, "verified")


class TestLoopBreaker(unittest.TestCase):
    def setUp(self):
        self.breaker = LoopBreaker(window_size=10, repetition_threshold=3)

    def test_no_loop_initial(self):
        signal = self.breaker.check("sess1")
        self.assertFalse(signal.detected)

    def test_same_tool_loop(self):
        for _ in range(3):
            self.breaker.record_call("bash_exec", {"command": "ls"}, session_id="sess1")
        signal = self.breaker.check("sess1")
        self.assertTrue(signal.detected)
        self.assertEqual(signal.loop_type, "same-tool-call")

    def test_different_args_no_loop(self):
        self.breaker.record_call("bash_exec", {"command": "ls"}, session_id="sess1")
        self.breaker.record_call("bash_exec", {"command": "pwd"}, session_id="sess1")
        self.breaker.record_call("bash_exec", {"command": "whoami"}, session_id="sess1")
        signal = self.breaker.check("sess1")
        self.assertFalse(signal.detected)

    def test_same_error_loop(self):
        for i in range(3):
            self.breaker.record_call("python_exec", f"bad code {i}", error="SyntaxError", session_id="sess1")
        signal = self.breaker.check("sess1")
        self.assertTrue(signal.detected)
        self.assertEqual(signal.loop_type, "same-error")

    def test_same_response_loop(self):
        for i in range(3):
            self.breaker.record_call("web_search", f"query {i}", response="No results found", session_id="sess1")
        signal = self.breaker.check("sess1")
        self.assertTrue(signal.detected)
        self.assertEqual(signal.loop_type, "same-response")

    def test_exhausted_recovery(self):
        # Trigger loops to exhaust recovery attempts (max=5)
        for _ in range(6):
            for i in range(3):
                self.breaker.record_call("bash_exec", {"command": f"fail {i}"}, error="Failed", session_id="sess2")
            signal = self.breaker.check("sess2")
            if signal.loop_type == "recovery-exhausted":
                break
        self.assertTrue(signal.detected)
        self.assertEqual(signal.loop_type, "recovery-exhausted")

    def test_reset(self):
        for _ in range(3):
            self.breaker.record_call("bash_exec", {"command": "ls"}, session_id="sess1")
        self.breaker.reset("sess1")
        signal = self.breaker.check("sess1")
        self.assertFalse(signal.detected)

    def test_web_search_many_queries_higher_bar_than_bash(self):
        """News-style research: many web_search calls should not trip same-tool-name at 5."""
        b = LoopBreaker(window_size=40, repetition_threshold=3, same_name_threshold=5)
        for i in range(10):
            b.record_call("web_search", {"q": str(i)}, response=f"results-{i}", session_id="news")
        self.assertFalse(b.check("news").detected)
        for i in range(10, 15):
            b.record_call("web_search", {"q": str(i)}, response=f"results-{i}", session_id="news")
        self.assertFalse(b.check("news").detected)
        b.record_call("web_search", {"q": "last"}, response="results-last", session_id="news")
        sig = b.check("news")
        self.assertTrue(sig.detected)
        self.assertEqual(sig.loop_type, "same-tool-name")


class TestRecoveryManager(unittest.TestCase):
    def setUp(self):
        self.manager = RecoveryManager()

    def test_suggest_sequence(self):
        # 1. different-tool
        a1 = self.manager.suggest(session_id="s1")
        self.assertEqual(a1.strategy, "different-tool")
        # 2. search
        a2 = self.manager.suggest(session_id="s1")
        self.assertEqual(a2.strategy, "search")
        # 3. simplify
        a3 = self.manager.suggest(session_id="s1")
        self.assertEqual(a3.strategy, "simplify")
        # 4. ask-user
        a4 = self.manager.suggest(session_id="s1")
        self.assertEqual(a4.strategy, "ask-user")
        # 5. abort
        a5 = self.manager.suggest(session_id="s1")
        self.assertEqual(a5.strategy, "abort")
        self.assertFalse(a5.exhausted)
        # 6. exhausted
        a6 = self.manager.suggest(session_id="s1")
        self.assertEqual(a6.strategy, "abort")
        self.assertTrue(a6.exhausted)

    def test_suggest_with_context(self):
        a = self.manager.suggest(failed_tool="bash_exec", error_msg="Timeout", session_id="s2")
        self.assertIn("bash_exec", a.instruction)
        self.assertIn("Timeout", a.instruction)

    def test_exhausted_user_message_is_not_model_abort_prompt(self):
        msg = RecoveryManager.exhausted_user_message()
        self.assertIn("stopped", msg.lower())
        self.assertNotIn("Do NOT claim success", msg)


class TestStopValidator(unittest.TestCase):
    def setUp(self):
        self.validator = StopValidator()

    def test_empty_response(self):
        check = self.validator.validate("")
        self.assertEqual(check.decision, "proceed")

    def test_informational_response(self):
        check = self.validator.validate("Here is the information you requested.")
        self.assertEqual(check.decision, "proceed")

    def test_completion_claimed_no_tools(self):
        check = self.validator.validate("The task is done.")
        self.assertEqual(check.decision, "disclaim")
        self.assertIn("note:", check.disclaimer.lower() if check.disclaimer else "")

    def test_multi_step_insufficient(self):
        check = self.validator.validate("I am working on it.", tool_calls_made=1, is_multi_step=True)
        self.assertEqual(check.decision, "continue")

    def test_valid_stop(self):
        check = self.validator.validate("The task is done.", tool_calls_made=3, is_multi_step=True)
        self.assertEqual(check.decision, "proceed")

if __name__ == "__main__":
    unittest.main()
