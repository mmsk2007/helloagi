# Context unrolling (ContextPaper-inspired) — analysis for HelloAGI

**Core idea:** Long-horizon omni models need **structured**, **prioritized** context rather than monolithic history dumps—unroll relevant slices per decision.

**Key architecture:** Typed segments (task, session, memory, tool history) with scoring and rolling budgets.

**Useful for HelloAGI:** `ContextSegment`, `ContextManager`, `memory_selector` heuristics; optional rolled `<memory-context>` when `context.managed` is true, alongside existing `ContextCompressor`.

**Defer:** Full multimodal stitcher, learned compression policies, cross-session global optimizers.

**MVP implemented:** Segment assembly with token-ish budgets and relevance sort.

**SRG integration:** Risk-bearing segments (e.g., privileged notes) should still pass memory/output policy before injection.

**Risks:** Over-trimming drops critical facts; tune budgets per channel and expose `context.max_budget_tokens`.
