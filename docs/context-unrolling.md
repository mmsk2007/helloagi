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

## Operations/action-gating application

For an operations task, HelloAGI should build context like:

```json
{
  "goal": "Delete temp build artifacts after confirming scope",
  "text_constraints": ["only local temp artifacts", "no production service changes"],
  "action_risk": ["destructive filesystem operation"],
  "scope": ["paths inspected", "rollback/restore option identified"],
  "verification_results": ["generated assumptions verified before action"]
}
```

The `context-plan` CLI supports `--task-type operations` so first users can see the risk-identification and scope-verification primitives before any high-risk action. It also renders a compact `workspace_summary` showing the observed goal item, any observed `artifact_references` extracted from relative file/test mentions in the goal, verified `artifact_existence` evidence for whether those repo-relative files/tests exist from the current working directory without recording absolute paths, content-safe `artifact_metadata` evidence with path/byte/line/kind counts for present references, optional `pytest_collection` evidence for referenced pytest node IDs using a static AST check without executing repository code or storing stdout/stderr/traceback content, and the generated `primitive_selection` item with source, confidence, observed/generated state, and verification state. When pytest evidence is present, the CLI prints a note that this is a static Python-test check and that parameterized bracket suffixes are counted at the base node. The CLI now also renders a machine-checkable action-gate summary from `evaluate_action_readiness()`, including required high-risk evidence types (`action_risk`, `scope`) and explicit blockers such as unverified generated context or missing verified scope/risk evidence. That makes the planning command itself demonstrate Context Unrolling instead of only listing primitive names.

Actual tool execution now enforces the Context Unrolling action gate before normal Anthropic, OpenAI, and Gemini model-driven tool calls execute, then journals a compact `context_workspace_tool_evidence` event after execution. The pre-execution gate builds typed evidence for the observed user request, generated tool intent, SRG governance verification, action risk, scope, and optional user approval; high-risk/escalated calls are blocked unless generated intent, risk, and scope are verified. Blocked events include the provider (`anthropic`, `openai`, or `google`) so replay/debug tooling can prove which model loop returned the gate result without executing the tool. The post-execution event adds tool result evidence while avoiding duplicated full prompts, file paths, or tool outputs in the context workspace payload. `helloagi replay-failure` renders the latest valid pre-failure context-workspace summary in human-readable text, skipping malformed workspace events, so users can audit observed/generated/verified counts and action-readiness without opening raw JSONL.

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

1. Integrate `ContextWorkspace` into planning/orchestration paths beyond tool evidence journaling.
2. Add primitive adapters for existing tools: file search/read, tests, browser screenshot/OCR, web fetch, verifier.
3. Strengthen Gemini parity with a mocked end-to-end tool-call/journal assertion.
4. Add additional replay coverage for multiple valid context-workspace events across separate failures.
5. Add richer public diagnostics for context-action gate blockers and required evidence.
