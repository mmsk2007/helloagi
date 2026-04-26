# Competitor Comparison: HelloAGI vs Hermes Agent vs OpenClaw

> **Updated**: 2026-04-26 (post skill-bank, VLAA reliability, context manager, browser tools, SRG adapter)  
> **Scope**: Architecture comparison across 15 dimensions

---

## Overview

| Feature | HelloAGI | Hermes Agent | OpenClaw |
|---------|----------|--------------|----------|
| **Language** | Python | Python | TypeScript/Node |
| **License** | MIT | MIT | MIT |
| **Version** | 0.5.0 | ~0.10.0 | Active dev |
| **Primary LLM** | Claude + Gemini | Multi-model | Multi-model |
| **Governance** | SRG + MemoryGuard + OutputGuard (deterministic) | None built-in | None built-in |
| **Entry points** | CLI, API, Telegram, Discord, Voice | CLI, TUI, Web | CLI, Web, Desktop (Electron), Mobile |
| **Skills** | Skill contracts + bank + TriLoop extraction + semantic hints | Skills dir, toolsets | Skills snapshot in agent loop |
| **Browser** | SRG-governed `browser_*` tools (Playwright + HTTP fallback, optional extra) | Full browser / computer-use stack | Puppeteer / embedded pi sessions |
| **Run bounds** | `max_turns`, optional `reliability.soft_timeout_sec` wall clock | Very high turn budgets | Per-run timeout / wait RPCs |
| **Codebase size** | Compact Python runtime | Very large (gateway + tools) | Very large monorepo |

---

## Detailed Comparison

### 1. Agent Planning

| Aspect | HelloAGI (Score: 6/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Planner | LLM + template fallback | Plans / routines | Rich workflows + ACP |
| Plan review | SRG in TriLoop | None | None |
| Default path | `think()` tool loop; TriLoop opt-in via `create_tri_loop()` | `run_conversation` | Gateway `agent` / embedded pi |

**Gap:** Deeper planner integration into the default `think()` loop (today TriLoop is explicit).

### 2. Memory

| Aspect | HelloAGI (Score: 8/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Semantic | Gemini embeddings (optional) | Memory tools | Session store + embeddings |
| Guard | MemoryGuard | None | None |
| Rolling context | `ContextManager` + compressor | Massive trajectory stack | Session compaction docs |

**Strength:** Write-side memory governance remains rare.

### 3. Tool Usage

| Aspect | HelloAGI (Score: 8/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Risk + SRG | Per-tool risk + evaluate_tool | Policy via config, not deterministic runtime gate | Policy via config / gateway |
| Parallel batch | Sequential execution | **Parallel** independent read-only batches | Concurrent lanes / queues |
| Circuit breaker | Yes | Partial patterns | Retries at layers |

**Gap:** Hermes-style **parallel tool batches** for independent reads (HelloAGI still runs tool calls sequentially per turn).

### 4. Browser / Computer Control

| Aspect | HelloAGI (Score: 6/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Web text | `web_fetch` + SSRF checks | Broad | Broad |
| Browser session | `browser_navigate` / `read` / `screenshot`, sandbox + governor | Mature computer use | Mature desktop + gateway |
| Governance on browse | URL rate limit + SSRF + policy hide when disabled | Operator trust | Operator trust |

**Gap:** Depth of GUI automation (click/type chains, recorded flows) vs Hermes/OpenClaw.

### 5. Task Decomposition

| Aspect | HelloAGI (Score: 6/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| DAG | Planner + orchestrator | Batch + delegate | Workflow graphs |
| Parallel | Planner deps; tools not parallel | Parallel tools | Parallel nodes / lanes |

### 6. Long-Horizon Task Execution

| Aspect | HelloAGI (Score: 7/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Turns | `policy_pack.max_turns` | 250+ typical | Configurable |
| Wall clock | `reliability.soft_timeout_sec` (optional) | Operator / host | `agent.wait` + timeouts |
| Recovery | TriLoop replan + main-loop VLAA (verifier, loop breaker, recovery) | Ad hoc | Retries + streaming |
| Compression | `ContextCompressor` + rolled memory | Very large compressor module | Queue + compaction |

### 7. Skill Reuse

| Aspect | HelloAGI (Score: 7/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Storage | `SkillBank` JSON contracts + legacy markdown | Directories + toolsets | Skills dir / snapshots |
| Discovery | Semantic hints + trigger match | Tooling | Load-time snapshot |
| Learning | TriLoop extract + SRG `check_skill_promotion` | Manual / optional | Plugins |

**Remaining gap:** Embedding-heavy retrieval across huge banks; merge/split/retire automation like full COSPLAY.

### 8. Multi-Agent Orchestration

| Aspect | HelloAGI (Score: 6/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Delegation | `delegate_task` SRG-governed | Rich `delegate_tool` tree | Nested sessions / agent steps |
| Isolation | Sub-agent policy + tools | Depth limits, spawn pause | Session keys + lanes |

### 9. Safety / Governance

| Aspect | HelloAGI (Score: 9/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Gates | SRG + guards + posture + adapter logging | None at Python gate | None at TS gate |
| Audit | JSONL journal + `governance.*` kinds | Logs | Logs + RPC streams |

**Advantage:** Deterministic runtime policy remains HelloAGI’s clearest differentiator.

### 10. Recovery from Failure

| Aspect | HelloAGI (Score: 8/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Loops / phantom text | VLAA-inspired verifier + loop breaker + stop validator | Varies by surface | Streaming + retries |
| Replan | TriLoop | Manual | Workflow |

### 11. End-to-End Testing

| Aspect | HelloAGI (Score: 5/10) | Hermes | OpenClaw |
|--------|------------------------|--------|----------|
| Unit / integration | ~396 tests | Broad | Broad |
| E2E | Stubs + TriLoop e2e | mini_swe_runner, etc. | QA / benchmarks |

**Gap:** Named scenario harness with recorded transcripts (see `evaluation/scenarios.py` stub).

### 12–15. Developer Experience, Extensibility, Documentation, OSS appeal

Roughly unchanged: HelloAGI wins on **simplicity + governance**; Hermes/OpenClaw win on **surface area, polish, and community**.

---

## Scorecard (revised)

| Category | Score | Notes |
|----------|-------|-------|
| Agent planning | **6** | TriLoop SRG-governed; not default in `think()` |
| Memory | **8** | Principal scope + MemoryGuard + embeddings |
| Tool usage | **8** | SRG every call; **no parallel batch yet** |
| Browser / computer | **6** | Governed browser MVP + shell/code |
| Task decomposition | **6** | DAG planner; limited parallel execution |
| Long-horizon | **7** | Compression + soft timeout + VLAA layer |
| Skill reuse | **7** | Bank + extraction + semantic hints |
| Multi-agent | **6** | Delegation exists; less fan-out than Hermes |
| Safety / governance | **9** | Still the standout |
| Recovery | **8** | VLAA + TriLoop |
| E2E testing | **5** | Stubs; needs harness |
| Developer experience | **6** | pip-friendly |
| Extensibility | **7** | Tools + channels + packs |
| Documentation | **7** | Audit + upgrade + research notes |
| OSS appeal | **5** | Community size |
| **Average** | **6.7** | |

---

## What to add next (priority)

1. **Parallel read-only tool batches** (Hermes parity) with SRG pre-check per tool and safe merge of results.  
2. **Richer browser tool surface** (click, type, wait) under the same governor.  
3. **Scenario benchmark runner** wired to `evaluation/scenarios.py` (no API keys; mocked tools).  
4. **Optional default TriLoop** for high-risk postures only (keep `think()` fast for chat).  
5. Keep marketing accurate: **governed autonomy**, not “only safe agent” unless benchmarked.
