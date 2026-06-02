# BioAgent Organism Intelligence Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Evolve HelloAGI from a governed agent runtime into a BioAgent-style organism: modular organs that sense, reason, act, regulate risk, learn from outcomes, and stay healthy over long-running operation.

**Architecture:** Keep the current HelloAGI foundations — SRG governance, dual-system cognition, context unrolling, memory, channels, service/API — but reorganize future work around organ systems with explicit interfaces, telemetry, and health checks. Each phase must produce public-safe repo changes, tests, docs, and an observable product improvement.

**Tech Stack:** Python, pytest, HelloAGI runtime/service/channel layers, SRG policy engine, context-unrolling workspace, memory journals, CLI/API diagnostics, Telegram/service smoke tests.

---

## Operating Rules for Daily Schedule

- The daily HelloAGI sprint must read this plan before choosing work.
- Pick exactly one PR-sized improvement per run from the earliest incomplete phase unless a higher-severity product-readiness blocker exists.
- Treat every organ system as a product feature, not only architecture: it must improve install, onboarding, runtime behavior, governance, observability, or real user task execution.
- Keep all changes public-safe: no private Telegram IDs, OAuth files, local DBs, memory dumps, credentials, server details, or company-private state.
- Every implementation day must leave evidence: tests, git diff/status, secret/privacy scan, commit hash if committed, and ledger entry.
- Do not mark a phase complete until its acceptance criteria and verification commands pass.

---

## Organ-System Model

HelloAGI organism systems:

- **Brain / Cortex:** planner, dual-system router, agent council, context-unrolling workspace, verifier.
- **Nervous System:** event bus, task graph, interrupts, progress signals, escalation signals.
- **Senses:** channel adapters, CLI/API input, environment/tool observations, user/task context extraction.
- **Effectors / Muscles:** governed tool execution, workflow actions, channel replies, service operations.
- **Immune System:** SRG, approval gates, prompt-injection resistance, secret/privacy scanning, incident handling.
- **Memory / Hippocampus:** episodic events, semantic facts, skills, provenance, recall and forgetting policy.
- **Metabolism:** budgets for tokens/time/cost/rate limits, backpressure, scheduling, retries.
- **Circulatory System:** typed runtime events flowing between organs with trace IDs and health metrics.
- **Homeostasis:** health checks, self-diagnostics, stall detection, recovery, safe-mode fallback.
- **Growth System:** crystallization of successful traces into skills, capability benchmarks, roadmap promotion.

---

## Phase 0: Organ Architecture Baseline

**Objective:** Make the organism architecture explicit and testable without changing runtime behavior.

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap/MASTERPLAN.md`
- Create: `docs/organism-architecture.md`
- Test: `tests/diagnostics/test_public_readiness.py` or a new docs/readiness test if docs coverage exists

**Tasks:**
1. Document organ systems and boundaries.
2. Map existing modules to organs: `core`, `context_unrolling`, `channels`, `tools`, `diagnostics`, `service`, `memory`.
3. Add a public readiness criterion: docs must not claim organ capabilities before implementation exists.
4. Add a roadmap section linking this phase plan.
5. Verify docs links and public-readiness tests.

**Acceptance Criteria:**
- A new contributor can see which current modules implement which organ.
- Unsupported organs are labeled planned, not shipped.
- Roadmap points to this plan.

**Verification:**
```bash
pytest tests/diagnostics/test_public_readiness.py -q
pytest -q
```

---

## Phase 1: Circulatory Event Spine

**Objective:** Introduce a typed event spine so organs can exchange observations, decisions, actions, and health signals with provenance.

**Files:**
- Create/modify: `src/agi_runtime/events.py` or `src/agi_runtime/core/events.py`
- Modify: `src/agi_runtime/core/agent.py`
- Modify: `src/agi_runtime/context_unrolling.py`
- Test: `tests/core/test_event_spine.py`

**Tasks:**
1. Define `OrganEvent` with fields: `event_id`, `trace_id`, `organ`, `kind`, `timestamp`, `payload`, `provenance`, `confidence`, `verified`.
2. Add in-memory append/read helpers with JSON-safe serialization.
3. Emit events for context plan creation and agent turn start/end.
4. Add tests for schema, trace correlation, provenance, and serialization.
5. Keep persistence optional; no private memory files in repo.

**Acceptance Criteria:**
- Context-unrolling and agent-turn events share a trace ID.
- Events distinguish observed vs generated vs verified information.
- Existing behavior remains unchanged when event consumers are absent.

**Verification:**
```bash
pytest tests/core/test_event_spine.py -q
pytest tests/test_context_unrolling.py tests/core/test_prompt_contracts.py -q
```

---

## Phase 2: Homeostasis and Health Signals

**Objective:** Make HelloAGI aware of its runtime health and able to degrade safely.

**Files:**
- Modify: `src/agi_runtime/diagnostics/public_readiness.py`
- Modify: `src/agi_runtime/service/manager.py`
- Modify: `src/agi_runtime/cli.py`
- Test: `tests/diagnostics/test_public_readiness.py`
- Test: `tests/test_service_manager_doctor.py`

**Tasks:**
1. Add health categories for brain, senses, effectors, immune, memory, metabolism, and channels.
2. Report provider usable vs configured, tool availability, memory path safety, and service/channel reachability.
3. Add safe-mode recommendation when critical organs are missing.
4. Ensure `helloagi health` output is user-readable and does not expose secrets.
5. Add tests for honest degraded states.

**Acceptance Criteria:**
- A user can tell why HelloAGI cannot act yet and what to configure next.
- Health output maps failures to organ systems.
- Secret/private paths are not leaked in public-facing diagnostics.

**Verification:**
```bash
pytest tests/diagnostics/test_public_readiness.py tests/test_service_manager_doctor.py -q
helloagi health || true
```

---

## Phase 3: Brain/Cortex Workspace Upgrades

**Objective:** Make the context-unrolling workspace the default pre-action reasoning substrate for non-trivial tasks.

**Files:**
- Modify: `src/agi_runtime/context_unrolling.py`
- Modify: `src/agi_runtime/core/agent.py`
- Modify: `docs/context-unrolling.md`
- Test: `tests/test_context_unrolling.py`
- Test: `tests/core/test_prompt_contracts.py`

**Tasks:**
1. Add primitive selection reasons and action-readiness status to the context workspace.
2. Require verifier notes before high-risk action proposals.
3. Inject compact workspace summaries into agent prompts where appropriate.
4. Add tests for provenance, confidence, and verified/unverified state.
5. Document how this supports organism brain behavior.

**Acceptance Criteria:**
- Plans distinguish raw user intent, inferred goals, retrieved memory, and verified facts.
- High-risk proposed actions cannot appear as “ready” without verification metadata.
- Prompt contract tests prove the workspace is used without bloating prompts unnecessarily.

**Verification:**
```bash
pytest tests/test_context_unrolling.py tests/core/test_prompt_contracts.py -q
helloagi context-plan "Diagnose why my Telegram bot is silent" --json
```

---

## Phase 4: Immune System Hardening

**Objective:** Strengthen deterministic governance and incident visibility around organism actions.

**Files:**
- Modify: SRG-related modules under `src/agi_runtime/` as discovered
- Modify: `docs/security.md`
- Create/modify: `tests/security/` or existing governance tests
- Modify: `docs/production-checklist.md`

**Tasks:**
1. Inventory current SRG/action-gating implementation.
2. Add tests for safe, escalated, denied, and injection-like instructions.
3. Add incident event types for denied/escalated actions.
4. Add production checklist items for approvals, rollback, and evidence.
5. Document immune-system boundaries: model proposes; SRG decides.

**Acceptance Criteria:**
- Risky actions are blocked/escalated deterministically outside the model prompt.
- Incident/approval evidence is visible without exposing secrets.
- Public docs do not overclaim jailbreak immunity beyond tested SRG boundaries.

**Verification:**
```bash
pytest tests -q -k "srg or security or governance"
pytest -q
```

---

## Phase 5: Memory, Metabolism, and Growth

**Objective:** Convert successful verified work into reusable skills while managing costs, latency, and forgetting.

**Files:**
- Modify: memory/skill-related runtime modules as discovered
- Modify: `docs/cognitive-runtime.md`
- Create/modify: `tests/memory/` or `tests/core/`

**Tasks:**
1. Define memory event taxonomy: episodic, semantic, skill, preference, incident.
2. Add outcome metadata and confidence decay rules where missing.
3. Add budget fields for token/time/cost/rate-limit decisions.
4. Add tests for skill crystallization and confidence demotion.
5. Document how metabolism prevents runaway autonomous loops.

**Acceptance Criteria:**
- HelloAGI records why a workflow became a skill and when it should stop trusting it.
- Runtime budgets are explicit enough for future router decisions.
- Tests cover both learning and safe forgetting/demotion.

**Verification:**
```bash
pytest tests -q -k "memory or skill or cognition or budget"
pytest -q
```

---

## Phase 6: Senses and Effectors Product Proof

**Objective:** Prove the organism can sense through real channels and act through governed tools in user-facing flows.

**Files:**
- Modify: `src/agi_runtime/channels/telegram.py`
- Modify: `src/agi_runtime/api/server.py`
- Modify: `src/agi_runtime/tools/` as discovered
- Test: `tests/channels/`
- Test: API/tool tests as discovered

**Tasks:**
1. Add channel observation events for Telegram/API/CLI inputs.
2. Add action result events for replies/tool outputs.
3. Add group-chat low-noise behavior tests.
4. Add first useful task smoke path that performs one safe deterministic action.
5. Document limitations for unavailable credentials/channels.

**Acceptance Criteria:**
- A new user sees HelloAGI sense a request, decide safely, act, and report evidence.
- Group chats remain low-noise and governed.
- Missing credentials produce honest failure, not vague silence.

**Verification:**
```bash
pytest tests/channels -q
pytest tests/test_cli_contract.py tests/diagnostics/test_public_readiness.py -q
```

---

## Phase 7: Organism Evaluation and Release Readiness

**Objective:** Ship a reproducible scorecard proving organism behavior across cognition, governance, memory, channels, and recovery.

**Files:**
- Modify: `docs/EVALUATION_SCORECARD.md`
- Modify: `src/agi_runtime/diagnostics/public_readiness.py`
- Modify: `docs/production-checklist.md`
- Test: `tests/diagnostics/test_scorecard.py`

**Tasks:**
1. Add an organism scorecard with criteria per organ system.
2. Add benchmark/smoke commands for each organ.
3. Add release gate requiring docs, tests, health output, and no private artifact leakage.
4. Add a daily report section for phase, organ touched, evidence, and next phase task.
5. Prepare v1.0 readiness recommendations.

**Acceptance Criteria:**
- HelloAGI can be evaluated as an organism, not only a CLI package.
- Scorecard reports implemented/proven/planned states honestly.
- Daily schedule reports are comparable over time.

**Verification:**
```bash
pytest tests/diagnostics/test_scorecard.py tests/diagnostics/test_public_readiness.py -q
pytest -q
```

---

## Daily Report Addendum

Every HelloAGI daily cron report should include:

- Organism phase: Phase N + name
- Organ touched: brain / nervous / senses / effectors / immune / memory / metabolism / circulatory / homeostasis / growth
- Change type: docs / tests / runtime / diagnostics / channel / governance
- Evidence: tests, health output, commit/push status
- Phase status: not started / in progress / blocked / complete
- Next organ-system task

---

## Completion Definition

This plan is complete when:

- All phases have implementation evidence in public repo commits.
- `helloagi health` reports organism-level health categories.
- Context unrolling is used as a typed brain workspace for non-trivial tasks.
- SRG/immune decisions are tested and observable.
- Memory/growth can promote and demote skills based on verified outcomes.
- Senses/effectors are proven through at least CLI plus one channel or API path.
- The evaluation scorecard clearly distinguishes shipped, experimental, and planned capabilities.
