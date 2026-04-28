# Peer parity roadmap (Hermes, OpenClaw, Thoth)

This document captures **product/architecture gaps** compared to adjacent open agents in this ecosystem. It is a roadmap, not a commitment to implement every item.

## Execution and resilience

| Area | Peer pattern | HelloAGI status |
|------|----------------|-----------------|
| Tool loop | Hermes `IterationBudget`, grace call, refund on some abort paths | Fixed `max_turns` + LoopBreaker + RecoveryManager + max-turn synthesis; **no iteration refund** when a turn is spent on SRG-denied tools (same net cost as a wasted model call — mitigated by SRG + phantom/stop validators instead) |
| Transcript repair | OpenClaw / Pi embedded runner sanitizes tool pairs after compaction | Context compressor + history shape; **no dedicated transcript repair pass** — add if malformed pairs appear in production logs |
| Sub-agents | Hermes nested budgets | `delegate_task` supported on **Anthropic and Google** (isolated sub-loop); still single-process |

## Memory and “Thoth-class” scope

Thoth adds a **personal knowledge graph**, nightly **dream cycle**, multi-step **tasks** UI, and **LangGraph** checkpoints with `interrupt()` gates.

HelloAGI today focuses on **SRG-governed tool autonomy**, embeddings memory, skills, and JSONL journals — **not** a graph DB, LangGraph runtime, or desktop task designer.

**If** you need Thoth-class features:

1. Specify **memory model** (graph vs vector-only) and privacy boundaries first.
2. Prefer **optional packages** or sidecars over hard-coupling LangGraph into the core runtime.
3. Reuse patterns from Thoth (`tasks.py`, `agent.py` stream events) for UX research, not blind imports.

## Channel policy matrix

OpenClaw documents Telegram streaming modes (`partial` / `block` / `progress`) and interaction with preview vs block streaming. HelloAGI uses **live preview + optional stream consumer**; see [streaming-contract.md](streaming-contract.md) and `HELLOAGI_TELEGRAM_LIVE` in the README.

## Scheduling

See [reminders-scheduling.md](reminders-scheduling.md) for cron/reminder scope vs Hermes/OpenClaw/Thoth job runners.
