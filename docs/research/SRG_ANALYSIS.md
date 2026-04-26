# Strategic Governance Runtime (reference SRG repo) — analysis for HelloAGI

**Core idea:** Independent control plane that governs autonomy with deterministic rules, auditability, delegation, and replay—**models predict, SRG governs**.

**Key architecture (TypeScript reference):** Governor + policy engine + state + decay + authority artifacts.

**HelloAGI mapping:** Python `SRGGovernor`, policy packs, posture engine, `MemoryGuard`, `OutputGuard`, JSONL `Journal`. New code should prefer `SRGAdapter` to centralize logging without duplicating policy.

**Useful for HelloAGI:** Adapter pattern for skill promotion, browser navigation, completion gates; journal namespaces `governance.*`.

**Defer:** Cryptographic artifact signing, full TS parity, cross-runtime delegation.

**MVP implemented:** `GovernanceLogger`, `SRGAdapter.check_skill_promotion`, completion logs from reliability layer.

**Risks:** Double-logging if both raw governor and adapter record the same gate—migrate call sites gradually.
