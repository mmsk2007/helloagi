"""Phase 3 — AgentCouncil + debate + voting + synthesis tests.

Exercises the System 2 path end-to-end with ``StubCouncilAgent``s so we
can verify orchestration without an LLM. Covers:
- weighted vote aggregation, tie-breaking via the synthesizer role
- per-agent ``VoteWeights`` persist across instances
- bounded debate; consensus → early-exit; dissent → all rounds run
- deterministic synthesizer output prefers Synthesizer → Planner → any
- AgentCouncil writes a CouncilTrace through the ThinkingTraceStore
- council exits cleanly even when no synthesizer is on the roster
"""

import tempfile
import unittest

from agi_runtime.cognition.system2 import (
    AgentCouncil,
    AgentTurn,
    PLANNER_ROLE,
    CRITIC_ROLE,
    RISK_AUDITOR_ROLE,
    SYNTHESIZER_ROLE,
    StubCouncilAgent,
    VoteWeights,
    aggregate_votes,
    run_debate,
)
from agi_runtime.cognition.trace import ThinkingTraceStore


def _stub(name, role, *, vote="yes", output="ok", critique="", confidence=0.8, tools=None):
    return StubCouncilAgent(
        name=name,
        role=role,
        canned=AgentTurn(
            agent=name,
            role=role,
            output=output,
            vote=vote,
            confidence=confidence,
            critique=critique,
            suggested_tools=tools or [],
        ),
    )


class TestAggregateVotes(unittest.TestCase):
    def test_majority_wins_without_weights(self):
        turns = [
            AgentTurn(agent="a", role=PLANNER_ROLE, vote="yes", confidence=0.8),
            AgentTurn(agent="b", role=CRITIC_ROLE, vote="yes", confidence=0.8),
            AgentTurn(agent="c", role=RISK_AUDITOR_ROLE, vote="no", confidence=0.8),
        ]
        result = aggregate_votes(turns)
        self.assertEqual(result.winner, "yes")
        self.assertGreater(result.yes_weight, result.no_weight)

    def test_synthesizer_breaks_tie(self):
        turns = [
            AgentTurn(agent="a", role=PLANNER_ROLE, vote="yes", confidence=0.8),
            AgentTurn(agent="b", role=CRITIC_ROLE, vote="no", confidence=0.8),
            AgentTurn(agent="s", role=SYNTHESIZER_ROLE, vote="no", confidence=0.8),
        ]
        # 1×yes vs 1×no without the synth, then synth votes no — synth's
        # vote also lands in no_weight, so direct count picks no anyway.
        result = aggregate_votes(turns)
        self.assertEqual(result.winner, "no")

    def test_pure_tie_with_no_synth_returns_tie(self):
        turns = [
            AgentTurn(agent="a", role=PLANNER_ROLE, vote="yes", confidence=0.8),
            AgentTurn(agent="b", role=CRITIC_ROLE, vote="no", confidence=0.8),
        ]
        result = aggregate_votes(turns)
        self.assertEqual(result.winner, "tie")

    def test_weights_change_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = VoteWeights(path=f"{tmp}/agent_weights.json")
            # The Planner has been very wrong before — weight crushed.
            w.set("planner", 0.1)
            w.set("critic", 1.0)
            turns = [
                AgentTurn(agent="planner", role=PLANNER_ROLE, vote="yes", confidence=1.0),
                AgentTurn(agent="critic", role=CRITIC_ROLE, vote="no", confidence=1.0),
            ]
            result = aggregate_votes(turns, w)
            self.assertEqual(result.winner, "no")

    def test_consensus_flag_set_when_all_agree(self):
        turns = [
            AgentTurn(agent="a", role=PLANNER_ROLE, vote="yes", confidence=0.8),
            AgentTurn(agent="b", role=CRITIC_ROLE, vote="yes", confidence=0.8),
            AgentTurn(agent="c", role=SYNTHESIZER_ROLE, vote="abstain", confidence=0.5),
        ]
        result = aggregate_votes(turns)
        self.assertTrue(result.consensus)


class TestVoteWeights(unittest.TestCase):
    def test_persistence_across_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/agent_weights.json"
            w = VoteWeights(path=path)
            w.set("planner", 0.5)
            w.adjust("critic", 0.7)  # default 1.0 + 0.7 = 1.7
            w2 = VoteWeights(path=path)
            self.assertAlmostEqual(w2.get("planner"), 0.5)
            self.assertAlmostEqual(w2.get("critic"), 1.7)

    def test_clamping(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = VoteWeights(path=f"{tmp}/aw.json")
            w.set("a", 99)   # clamped to MAX
            w.set("b", -5)   # clamped to MIN
            self.assertLessEqual(w.get("a"), 3.0)
            self.assertGreaterEqual(w.get("b"), 0.1)


class TestRunDebate(unittest.TestCase):
    def test_consensus_short_circuits_after_first_round(self):
        agents = [
            _stub("planner", PLANNER_ROLE, vote="yes"),
            _stub("critic", CRITIC_ROLE, vote="yes"),
        ]
        rounds = run_debate(user_input="task", agents=agents, max_rounds=4)
        self.assertEqual(len(rounds), 1)

    def test_dissent_runs_all_rounds(self):
        agents = [
            _stub("planner", PLANNER_ROLE, vote="yes"),
            _stub("critic", CRITIC_ROLE, vote="no"),
        ]
        rounds = run_debate(user_input="task", agents=agents, max_rounds=3)
        self.assertEqual(len(rounds), 3)

    def test_each_round_records_outputs_votes_critiques(self):
        agents = [
            _stub("planner", PLANNER_ROLE, vote="yes", output="step 1; step 2"),
            _stub("critic", CRITIC_ROLE, vote="no", critique="brittle"),
        ]
        rounds = run_debate(user_input="task", agents=agents, max_rounds=1)
        r0 = rounds[0]
        self.assertEqual(r0.agent_outputs["planner"], "step 1; step 2")
        self.assertEqual(r0.votes["critic"], "no")
        self.assertTrue(any("critic" in c for c in r0.critiques))


class TestAgentCouncil(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ThinkingTraceStore(path=self.tmp.name + "/traces")

    def tearDown(self):
        self.tmp.cleanup()

    def test_deliberate_returns_outcome_and_persists_trace(self):
        agents = [
            _stub("planner", PLANNER_ROLE, vote="yes",
                  output="navigate to /profile to read followers count"),
            _stub("critic", CRITIC_ROLE, vote="yes",
                  output="plan looks safe and direct"),
            _stub("synth", SYNTHESIZER_ROLE, vote="yes",
                  output="USE BROWSER: navigate to /profile, read followers."),
        ]
        council = AgentCouncil(
            agents=agents,
            trace_store=self.store,
            max_rounds=2,
        )
        outcome = council.deliberate(
            user_input="how many followers do we have?",
            fingerprint="fp_followers",
            srg_decision={"decision": "allow", "risk": 0.1},
        )
        self.assertIn("BROWSER", outcome.final_decision)
        self.assertEqual(outcome.vote.winner, "yes")
        # Trace persisted and findable by fingerprint.
        traces = self.store.find_by_fingerprint("fp_followers")
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].final_decision, outcome.final_decision)
        # SRG decision round-trips into the trace.
        self.assertEqual(traces[0].srg_decision.get("decision"), "allow")

    def test_council_falls_back_to_planner_when_no_synthesizer(self):
        agents = [
            _stub("planner", PLANNER_ROLE, vote="yes", output="planner plan"),
            _stub("critic", CRITIC_ROLE, vote="yes", output="ok"),
        ]
        council = AgentCouncil(agents=agents, max_rounds=1)
        outcome = council.deliberate(
            user_input="task", fingerprint="fp_no_synth"
        )
        self.assertEqual(outcome.final_decision, "planner plan")

    def test_empty_agents_raises(self):
        with self.assertRaises(ValueError):
            AgentCouncil(agents=[])


if __name__ == "__main__":
    unittest.main()
