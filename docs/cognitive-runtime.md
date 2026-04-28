# Dual-System Cognitive Runtime

HelloAGI's cognitive runtime mirrors fast/slow human cognition. A
deterministic router decides, before every reasoning turn, whether the
task should use the cheap fast path (**System 1**) or the deep
deliberative path (**System 2**). Successful System 2 runs crystallize
into stored Skills, so the next matching task routes back to System 1
— the runtime gets cheaper and smarter with experience.

The whole subsystem is gated behind a flag and ships disabled by
default. Behavior is identical to pre-cognitive HelloAGI until you
flip it on.

## Activation

In `helloagi.json`:

```json
{
  "cognitive_runtime": {
    "enabled": true,
    "mode": "dual",
    "system1_relevance_threshold": 0.75,
    "system1_confidence_threshold": 0.70,
    "risk_escalation_threshold": 0.50,
    "council": {
      "agents": ["planner", "critic", "risk_auditor", "synthesizer"],
      "min_quorum": 3,
      "max_rounds": 2,
      "tie_breaker": "synthesizer"
    },
    "crystallization": {
      "min_council_successes": 3,
      "min_agent_agreement": 0.66
    },
    "stall": {
      "enabled": true,
      "silent_turn_budget": 4,
      "warm_up_tool_calls": 5,
      "text_threshold": 40
    }
  }
}
```

Recommended ramp:

1. `mode: "observe"` — router scores every turn, logs the decision to
   the journal, but the agent path is unchanged. Inspect routing for a
   day before continuing.
2. `mode: "system1_only"` — familiar tasks route to System 1; novel
   tasks fall through to the legacy default loop.
3. `mode: "dual"` — full router behavior. Novel/risky tasks go to the
   Agent Council.

## System 1 — Expert Mode

**When**: a stored Skill matches the task with relevance ≥ posture
floor (default 0.75) **and** that Skill's confidence ≥ 0.70 **and**
risk score < 0.50.

**How**: Haiku-driven thin loop, plan/verify minimized, system prompt
references the matched Skill so the model knows it's executing a
proven recipe. Same SRG gates, same tool registry, same circuit
breakers — just less tokens spent thinking.

Expected outcome: tasks the agent has seen before run faster and
cheaper. A System 1 failure auto-decays the Skill's confidence and
demotes it to `candidate` if its success rate falls below 25% over ≥5
uses, forcing the next matching task back through the Council.

## System 2 — Agent Council

**When**: any task that fails the System 1 gate. By default that's
new fingerprints, low-confidence Skills, high-risk tools, or SRG
escalations.

**Roster**: four agents, each a thin LLM wrapper with a role prompt:

- **Planner** — proposes concrete steps + tools.
- **Critic** — attacks the plan; surfaces missed cases.
- **Risk Auditor** — scores against SRG-style risk dimensions.
- **Synthesizer** — breaks ties, writes the final reasoning summary.

**Debate**: bounded by `max_rounds` (default 2). Each round, agents
respond, vote (`yes`/`no`/`abstain`), and the votes are aggregated
with per-agent weights. Consensus triggers an early exit so we don't
burn tokens on a settled question. The Synthesizer breaks ties.

**Per-agent circuit breakers**: an agent that raises or returns
parse-error abstains 3+ times gets sidelined for 30 seconds — the
debate continues with the rest of the council. Calibration prevents a
flaky voice from blocking the room.

**Trace storage**: every deliberation writes a `CouncilTrace` JSON
file under `memory/cognition/traces/` with the rounds, votes, final
decision, SRG verdict, and outcome. Replayable.

## Self-improvement loop

When System 2 produces a verified pass:

1. The trace's outcome is patched to `pass`.
2. Per-agent vote weights nudge: `yes` voters get a small boost
   (`+0.06`), `no` voters get trimmed (`-0.10`). Reversed on a verified
   fail. Clamped to `[0.1, 3.0]` so a runaway feedback loop can't
   silence anyone.
3. The crystallizer inspects the fingerprint's trace history. Once a
   fingerprint accumulates `min_council_successes` passes (default 3)
   with average inter-agent agreement ≥ `min_agent_agreement` (default
   0.66), the most recent passing trace becomes a new candidate Skill
   stamped with `task_fingerprint` and `council_origin_trace_id`.
4. The router picks up the new Skill on the next matching task and
   routes to System 1.

The loop is idempotent — re-crystallizing the same fingerprint
refreshes the existing Skill instead of duplicating it.

## Three failure-mode guards

The runtime ships with three concrete guards designed to prevent the
"40-turn flounder" failure mode (agent burning turn budget on a task
it should know how to solve):

1. **Pattern hint injection** — `PatternDetector.get_tools_for_topic`
   surfaces tools the agent has historically used for similar topic
   words and injects them into the system prompt as a
   `<task-pattern-hint>` block.
2. **Stall detector** — observes each turn (text length + tool call
   count). After `silent_turn_budget` consecutive silent tool-only
   turns past the warm-up window, injects a
   `<turn-budget-warning>` reminder asking the agent to summarize and
   reconsider.
3. **Council Critic** — when System 2 fires, the Critic role's whole
   job is to attack the plan. A bad plan that survives the Critic and
   the SRG gate is much rarer than a bad plan that survives only the
   Planner.

## Observability

```bash
# Recent decisions, outcomes, agent weights, skill graduations:
python scripts/cognitive_dashboard.py

# Pretty-print a specific council trace:
python scripts/replay_trace.py <trace_id>

# Re-deliberate the same input against the live council:
python scripts/replay_trace.py <trace_id> --rerun
```

Journal events emitted:

- `routing.decided` — every turn, with `system`, `fingerprint`, `risk`.
- `system1.outcome` — pass/fail + skill confidence delta.
- `system2.outcome` — pass/fail + trace id.
- `council.deliberated` — rounds, winner, consensus.
- `skill.crystallized` — when a fingerprint graduates to a Skill.
- `trace.written` / `trace.outcome` — trace store mutations.

## Files

```
src/agi_runtime/cognition/
├── router.py              # CognitiveRouter — the System 1 vs System 2 decision
├── fingerprint.py         # task_fingerprint() — hash of normalized goal
├── risk.py                # RiskScorer
├── system1.py             # ExpertMode — Haiku-driven thin loop
├── system2/
│   ├── council.py         # AgentCouncil — orchestrates debate
│   ├── agents.py          # CouncilAgent + role prompts
│   ├── debate.py          # round-robin debate w/ early-exit
│   ├── voting.py          # weighted aggregation + outcome nudges
│   ├── synthesis.py       # final decision + reasoning_summary
│   └── llm_agent.py       # LLMCouncilAgent (Anthropic SDK wrapper)
├── stall.py               # StallDetector + reminder injection
├── trace.py               # ThinkingTraceStore (per-trace JSON files)
├── crystallize.py         # SkillCrystallizer (System 2 → Skill)
└── feedback.py            # OutcomeRecorder
```
