# Context Unrolling for HelloAGI

**Source:** `Context Unrolling in Omni Models` paper uploaded by the Chairman on 2026-05-13.

## What HelloAGI should learn from the paper

The useful lesson is not just “multimodal models are good.” The useful lesson is:

> Before answering or acting, an agent should build the right typed intermediate workspace, verify it, then act from that enriched context.

The paper describes this as:

```text
C[t+1] = C[t] + primitive(input, C[t])
answer/action = actor(input | C[T])
```

For HelloAGI, this means moving from:

```text
prompt -> answer/tool call
```

toward:

```text
goal -> typed context workspace -> task-relevant primitives -> verification -> answer/action
```

## Important principles

1. **Do not just think longer.** More context is not automatically better.
2. **Use task-relevant context.** A coding task needs files, tests, stack traces, dependency graphs, and patch critiques. A browser task needs screenshot/OCR/UI layout/action verification.
3. **Track provenance.** Every context item must say where it came from.
4. **Separate observed from generated.** A test log is observed evidence. A suspected root cause is generated context.
5. **Verify before high-risk action.** Generated assumptions should not trigger destructive or irreversible actions without verification.
6. **Use budgets.** The agent should not run every primitive on every task.

## Initial implementation in HelloAGI

The first implementation is intentionally small and public-safe:

- `agi_runtime.context_unrolling.ContextWorkspace`
- `agi_runtime.context_unrolling.WorkspaceItem`
- `agi_runtime.context_unrolling.ContextPrimitive`
- `agi_runtime.context_unrolling.PrimitiveResult`
- `agi_runtime.context_unrolling.ContextUnrollingController`

This gives HelloAGI a typed workspace with:

- type
- source
- confidence
- timestamp
- relation to goal
- observed vs generated flag
- verified flag

The first controller selects task-relevant primitives by task type and budget. Future work can make this policy learned, LLM-planned, uncertainty-aware, or RL-trained.

## Software-engineering application

For a coding task, HelloAGI should build context like:

```json
{
  "goal": "Fix checkout failure",
  "observations": ["issue text", "test output", "stack trace"],
  "text_constraints": ["must not change public API"],
  "code_context": ["relevant files", "dependency graph"],
  "generated_hypotheses": ["total rounding bug"],
  "verification_results": ["targeted test passed", "full suite passed"]
}
```

High-risk actions such as file writes, service restarts, pushes, or deploys should require verified context.

## Browser/computer-use application

For a UI task, HelloAGI should build context like:

```json
{
  "goal": "Submit the settings form",
  "observations": ["screenshot", "OCR text"],
  "visual_context": ["button bounding boxes", "layout graph"],
  "generated_predictions": ["clicking Save submits settings"],
  "verification_results": ["sandbox click triggered PATCH /settings"]
}
```

The action should be taken only after the goal-to-element mapping is verified enough for the risk level.

## Research/document application

For a paper or document task, HelloAGI should build:

- section summaries
- claims
- equations explained
- assumptions
- benchmark findings
- limitations
- implementation plan
- experiment/test plan

## Next implementation steps

1. Add CLI/dev command to show a context-unrolling plan for a goal.
2. Integrate `ContextWorkspace` into planning/orchestration paths.
3. Add primitive adapters for existing tools: file search/read, tests, browser screenshot/OCR, web fetch, verifier.
4. Add risk-gated actor behavior: high-risk actions require verified context.
5. Add journaling so context items can be audited without leaking private runtime state.
