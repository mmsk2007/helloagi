# VLAA-GUI — analysis for HelloAGI

**Core idea:** GUI agents fail via false completion and loops; mandatory **Completeness Verifier** and **Loop Breaker** modules reduce both.

**Key architecture:** Manager agent with post-action checks; optional search/coding/grounding agents for recovery.

**Useful for HelloAGI:** `CompletionVerifier`, `LoopBreaker`, `RecoveryManager`, `StopValidator` integrated in `HelloAGIAgent` think-loops; governance logging on blocked completions.

**Defer:** Full OSWorld-scale multimodal grounding, specialized search agents.

**MVP implemented:** Reliability package + hooks in Claude/Gemini paths.

**SRG integration:** Verifier outcomes logged via `SRGAdapter.logger`; destructive recovery still obeys tool SRG.

**Risks:** Regex-based claims miss nuanced UI evidence; extend with tool-grounded checks as browser tools mature.
