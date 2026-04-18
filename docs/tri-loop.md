# The TriLoop — SRG-Governed Plan / Execute / Verify / Replan

The TriLoop is Hello AGI's architectural backbone for autonomous execution.
It composes four pre-existing but previously-disconnected components —
`Planner`, `Verifier`, `SRGGovernor`, `Journal` — into a single governed
loop, and adds two new governance primitives (`PostureEngine`,
`OutputGuard`) that close the biggest gaps identified in the 2026-04 audit.

## Why this exists

Before the TriLoop, `autonomy/loop.py` was a 17-line statement repeater:
it called `agent.think()` N times in a row with no planning, no
verification, no replan, no SRG gates beyond whatever `think()` itself
enforced. The docs described a tri-loop (plan → execute → verify → replan);
the code did not implement one. `planner/planner.py` and
`verifier/verifier.py` existed as standalone classes but nothing composed
them.

The TriLoop is the composition.

## The loop

```
run(goal):
    1. Pre-flight
       - SRGGovernor.evaluate(goal)               # input-side gate
       - PostureEngine.select(goal) -> posture    # runtime stance
       - if pre-flight denies -> halt, no planning
    2. For iteration i = 1..(posture.max_replan_budget + 1):
       2a. Plan
           - i == 1: Planner.make_plan(goal)
           - else:   Planner.replan(prev_plan, failure_context)
       2b. Plan review (if posture.require_plan_review)
           - SRGGovernor.evaluate(serialized_plan)
           - if denied -> halt
       2c. Execute steps in dependency order
           - per step:
               - SRGGovernor.evaluate(step.action)  # step-level gate
               - agent.think(step.action)
               - OutputGuard.inspect(response.text, tool_calls_made)
                                                    # post-execution gate
               - deny -> mark failed; streak++
               - redact -> use redacted text
               - consecutive failures >= posture.max_consecutive_failures
                 -> halt iteration
       2d. Verifier.check(outputs, goal) -> verdict (PASS/PARTIAL/FAIL)
           - PASS: return TriLoopResult(status="passed", ...)
           - else: build failure_context, loop back to 2a
    3. If no iteration passed -> status="exhausted" or
       "replan_budget_exhausted"
```

Every state transition writes to `Journal`. The journal *is* the audit
trail; replay tooling reconstructs the decision sequence from it.

## Posture

`Posture` is the SRG-derived runtime stance for *this specific goal*. It
scales four things:

| Axis                        | conservative | balanced | aggressive |
|-----------------------------|--------------|----------|------------|
| max_risk_allow              | 0.25         | 0.45     | 0.55       |
| max_risk_escalate           | 0.55         | 0.75     | 0.85       |
| max_replan_budget           | 1            | 3        | 5          |
| max_consecutive_failures    | 2            | 3        | 5          |
| require_plan_review         | true         | true     | false      |
| require_output_guard        | true         | true     | true       |

Posture is *derived*, not *chosen by the caller*. A caller can supply a
`bias` argument, but bias can only make the posture stricter, never
looser — otherwise callers could launder risky goals through a permissive
bias. `OutputGuard` is never disabled, at any posture.

## OutputGuard

`SRGGovernor` has always been a pre-execution gate: it evaluates *what
the agent is about to do*. `OutputGuard` is its post-execution sibling:
it evaluates *what the agent is about to say*.

It catches three classes of failure:

1. **Secret leakage** — API keys, private keys, env-var values, JWTs,
   `/etc/passwd` content. Deterministic regex patterns, same philosophy
   as SRG (prompt-injection-immune). Decision: `deny` for unambiguous
   patterns, `redact` for pattern families where false positives have
   benign shapes (env dumps, `password=` assignments).
2. **Phantom actions** — text like "I sent the email" emitted when the
   `AgentResponse.tool_calls_made` count is 0. A hallucinated claim of
   action is reported as `redact`, not `deny`; the caller can strip the
   claim and retry via a real tool. Pattern source: cross-agent
   learnings from the `openfang` sibling project.
3. **Defense in depth** — even with a clean pre-flight, a compromised
   web page or a subtly phrased tool input can produce a response that
   leaks secrets. OutputGuard is the second lock.

## Integration points

- **With the agent**: TriLoop only needs a duck-typed object with
  `.think(prompt) -> response-like`. `HelloAGIAgent` satisfies this; so
  does a stub for tests.
- **With the existing SRG**: TriLoop reuses `agent.governor` when
  available so policy packs stay consistent between interactive
  `think()` calls and autonomous runs.
- **With the Journal**: `agent.journal` is auto-discovered; otherwise
  callers pass their own `Journal`. Nil journals are supported (no-op).
- **With `AutonomousLoop`**: The old 17-line loop is still present at
  `agi_runtime.autonomy.loop.AutonomousLoop` — nothing is breaking.
  It's now marked as a backward-compatibility shim in
  `agi_runtime.autonomy.__init__`.

## What this does *not* do yet

Explicit non-goals for this landing:

- **Per-step tool invocation.** TriLoop executes each step by prompting
  `agent.think(step.action)` — the agent still drives its own tool
  calls. A future refinement is to drive `step.tool` / `step.tool_input`
  directly when present, bypassing the LLM for mechanical steps.
- **Parallel step execution.** Steps run sequentially even when the
  dependency graph permits parallelism. The topological ordering is in
  place; a `concurrent.futures` executor layer is the follow-up.
- **Uncertainty quantification.** The `VerifyResult.confidence` field is
  carried through but isn't yet an input to posture changes mid-run.
  "Adaptive posture" — tightening the stance after a low-confidence
  verdict — is on the roadmap.
- **Checkpointing / reversibility.** Git-backed checkpoints (inspired
  by `shannon`'s pattern) are still TBD. Once present, the TriLoop will
  snapshot before risky steps and rollback on failure.

## Test surface

`tests/autonomy/test_tri_loop.py`, `tests/governance/test_posture.py`,
`tests/governance/test_output_guard.py` pin the invariants:

- Pre-flight deny halts before planning.
- Clean goals pass via the heuristic verifier (no LLM required).
- Secret leakage in outputs is blocked and reported as `output-denied`.
- Replan budget is honored on conservative posture.
- Journal records the full phase sequence.
- Posture bias is a ceiling, not a floor.
- Canonical postures are monotone along every axis.

All tests run without an `ANTHROPIC_API_KEY` — Planner and Verifier
have deterministic fallbacks, and the TriLoop is agent-agnostic so a
stub suffices.
