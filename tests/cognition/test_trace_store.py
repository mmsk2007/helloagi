"""ThinkingTraceStore — write/read/query/update tests.

The store is the substrate Phase 4 crystallization will read from. It must:
- round-trip a CouncilTrace through disk without losing fields
- find traces by fingerprint, newest-first
- find recent traces capped to ``limit``
- update_outcome patches a single trace and the index
- re-writes for the same trace_id replace, never duplicate
"""

import tempfile
import unittest
from pathlib import Path

from agi_runtime.cognition.trace import (
    CouncilTrace,
    DebateRound,
    ThinkingTraceStore,
)


def _trace(fp: str, *, decision: str = "do-it", outcome=None) -> CouncilTrace:
    return CouncilTrace(
        fingerprint=fp,
        user_input=f"user input for {fp}",
        rounds=[
            DebateRound(
                round_index=0,
                agent_outputs={"planner": "step 1; step 2", "critic": "step 1 is risky"},
                critiques=["risky tool"],
                votes={"planner": "yes", "critic": "no"},
            ),
        ],
        final_decision=decision,
        reasoning_summary="planner won 1-1; tie broken by synthesizer",
        srg_decision={"decision": "allow", "risk": 0.2},
        outcome=outcome,
        agent_weights_at_run={"planner": 1.0, "critic": 1.0, "synthesizer": 1.2},
    )


class TestThinkingTraceStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ThinkingTraceStore(path=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_then_read_round_trip(self):
        t = _trace("fp_alpha")
        self.store.write(t)
        got = self.store.get(t.trace_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.final_decision, "do-it")
        self.assertEqual(len(got.rounds), 1)
        self.assertEqual(got.rounds[0].agent_outputs["planner"], "step 1; step 2")
        self.assertEqual(got.srg_decision["decision"], "allow")

    def test_find_by_fingerprint_returns_newest_first(self):
        a = _trace("fp_shared", decision="first")
        b = _trace("fp_shared", decision="second")
        # Force a deterministic ordering.
        a.created_at = 100.0
        b.created_at = 200.0
        self.store.write(a)
        self.store.write(b)
        results = self.store.find_by_fingerprint("fp_shared")
        self.assertEqual([r.final_decision for r in results], ["second", "first"])

    def test_find_recent_caps_to_limit(self):
        for i in range(7):
            t = _trace(f"fp_{i}")
            t.created_at = float(i)
            self.store.write(t)
        recents = self.store.find_recent(limit=3)
        self.assertEqual(len(recents), 3)
        # Newest first — fp_6, fp_5, fp_4.
        self.assertEqual([r.fingerprint for r in recents], ["fp_6", "fp_5", "fp_4"])

    def test_update_outcome_patches_and_persists(self):
        t = _trace("fp_outcome")
        self.store.write(t)
        ok = self.store.update_outcome(t.trace_id, "pass")
        self.assertTrue(ok)
        got = self.store.get(t.trace_id)
        self.assertEqual(got.outcome, "pass")
        # New store reading the same dir sees the updated outcome via index.
        store2 = ThinkingTraceStore(path=self.tmp.name)
        recents = store2.find_recent(limit=1)
        self.assertEqual(recents[0].outcome, "pass")

    def test_update_outcome_unknown_id_returns_false(self):
        self.assertFalse(self.store.update_outcome("ct_does_not_exist", "fail"))

    def test_rewrite_does_not_duplicate_index_entry(self):
        t = _trace("fp_repeat")
        self.store.write(t)
        # Mutate and re-write the same trace_id.
        t.final_decision = "updated"
        self.store.write(t)
        results = self.store.find_by_fingerprint("fp_repeat")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].final_decision, "updated")

    def test_index_persists_across_instances(self):
        a = _trace("fp_persist_a")
        b = _trace("fp_persist_b")
        self.store.write(a)
        self.store.write(b)
        store2 = ThinkingTraceStore(path=self.tmp.name)
        # Both fingerprints findable from the fresh instance.
        self.assertEqual(len(store2.find_by_fingerprint("fp_persist_a")), 1)
        self.assertEqual(len(store2.find_by_fingerprint("fp_persist_b")), 1)

    def test_journal_logs_write(self):
        captured = []

        class FakeJournal:
            def write(self, kind, payload):
                captured.append((kind, payload))

        store = ThinkingTraceStore(path=self.tmp.name, journal=FakeJournal())
        t = _trace("fp_logged")
        store.write(t)
        kinds = [k for k, _ in captured]
        self.assertIn("trace.written", kinds)


if __name__ == "__main__":
    unittest.main()
