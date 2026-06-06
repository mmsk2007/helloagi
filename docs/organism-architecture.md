# HelloAGI Organism Architecture

HelloAGI uses an organism model as an architectural discipline: every capability should belong to an organ system with a clear boundary, observable signals, health checks, and governance. This is not a claim that every organ is fully implemented today. The table below separates **implemented**, **partial**, and **planned** responsibilities so public docs stay honest.

See also: `docs/plans/bioagent-organism-intelligence-phases.md`.

## Organ-System Map

### Brain / Cortex

**Purpose:** Turn user intent into typed plans, workspace state, verification notes, and response/action decisions.

**Current modules:**
- `src/agi_runtime/core/agent.py` — response lifecycle and prompt contract.
- `src/agi_runtime/context_unrolling.py` — typed intermediate workspace for task primitives, provenance, confidence, and verification.
- `docs/cognitive-runtime.md` — dual-system cognition design.

**Status:** Partial. Context unrolling exists and is exposed through `helloagi context-plan`; future work should make it a default pre-action substrate for non-trivial tasks.

### Nervous System

**Purpose:** Move observations, decisions, interrupts, approvals, progress, and action results between organs with traceable IDs.

**Current modules:**
- `src/agi_runtime/core/agent.py` — turn lifecycle and in-memory turn start/end event emission.
- `src/agi_runtime/events.py` — typed in-memory event spine helpers.
- `src/agi_runtime/diagnostics/replay.py` — replayable event/diagnostic support.
- `memory/events.jsonl` in local runtime checkouts — runtime journal; not public source state.

**Status:** Partial. A public-safe in-memory `OrganEvent` spine now exists for traceable turn/context signals; future work should broaden emitters and connect the spine to richer diagnostics without leaking runtime state.

### Senses

**Purpose:** Receive input from users, channels, APIs, commands, tools, and environment observations.

**Current modules:**
- `src/agi_runtime/channels/telegram.py` — Telegram channel adapter and group policy.
- `src/agi_runtime/api/server.py` — local HTTP API.
- `src/agi_runtime/cli.py` — CLI commands and one-shot/run flows.
- `docs/channels.md` and `docs/cli-reference.md` — user-facing channel/CLI docs.

**Status:** Implemented for core CLI/API/Telegram surfaces, with ongoing product-readiness hardening.

### Effectors / Muscles

**Purpose:** Execute governed actions: tool calls, replies, workflow steps, service operations, and channel messages.

**Current modules:**
- `src/agi_runtime/tools/` — built-in deterministic tools.
- `src/agi_runtime/service/manager.py` — service lifecycle actions and doctor/status flows.
- `src/agi_runtime/channels/telegram.py` and `src/agi_runtime/api/server.py` — outward replies.

**Status:** Partial. Tools and service/channel actions exist; future work should add action-result events and stronger evidence reporting.

### Immune System

**Purpose:** Keep the model from bypassing policy: deterministic governance, approvals, incident evidence, prompt-injection resistance, and private artifact controls.

**Current modules/docs:**
- SRG/governance-related runtime paths as documented in `docs/security.md` and `docs/srg-integration.md`.
- `src/agi_runtime/diagnostics/public_readiness.py` — public-source hygiene checks for secrets, runtime artifacts, docs, and organism architecture.
- `docs/production-checklist.md` — release and operational safety checklist.

**Status:** Partial and central. SRG remains the deterministic decision layer; public readiness now also checks that organism claims are documented and mapped.

### Memory / Hippocampus

**Purpose:** Store and retrieve episodic events, semantic facts, skills, preferences, incidents, and provenance without leaking private runtime state into public source.

**Current modules/docs:**
- `src/agi_runtime/tools/builtins/memory_store.py` and related memory built-ins.
- Local runtime `memory/` directory, ignored by git for private state.
- `docs/privacy.md`, `docs/environment.md`, and memory sections in product docs.

**Status:** Partial. Durable memory exists; future work should formalize taxonomy, confidence decay, skill promotion, and forgetting.

### Metabolism

**Purpose:** Manage finite resources: token/time/cost budgets, provider rate limits, retries, backpressure, and scheduling.

**Current modules/docs:**
- Provider configuration and routing docs in `docs/providers.md`.
- Service/diagnostic flows in `src/agi_runtime/service/manager.py`.
- Scheduling/reminder docs in `docs/reminders-scheduling.md`.

**Status:** Planned/partial. Some resource surfaces exist; future work should expose explicit budget signals to the router and health output.

### Circulatory System

**Purpose:** Carry typed `OrganEvent` records between organs so work is observable and replayable.

**Current modules:**
- Existing journal/replay diagnostics provide a foundation.
- `src/agi_runtime/events.py` defines `OrganEvent` and `EventSpine` for JSON-safe in-memory event flow.
- `helloagi context-plan` emits a local context-plan event and shows the trace ID/event count.

**Status:** Partial. Phase 1 has started with a typed in-memory spine; persistence and broader organ emitters remain planned.

### Homeostasis

**Purpose:** Keep the organism stable: health checks, degraded mode, stall detection, safe-mode recommendations, and recovery.

**Current modules/docs:**
- `src/agi_runtime/diagnostics/health.py` — organism-level health categories and safe-mode recommendations.
- `src/agi_runtime/diagnostics/public_readiness.py` — public release readiness.
- `src/agi_runtime/service/manager.py` — service doctor/status behavior.
- `docs/cognitive-runtime.md` — stall detection design.
- `docs/troubleshooting.md` — user recovery paths.

**Status:** Partial. `helloagi health` now maps runtime state to organ categories, reports provider configured-vs-usable details with secret-redacted recovery hints, includes service doctor recovery issues/recommendations, renders channel extension readiness with missing env/module hints, and includes safe degraded-mode recommendations; future work should deepen richer automatic recovery and make safe mode active rather than advisory.

### Growth System

**Purpose:** Convert verified successful behavior into reusable skills, benchmarks, scorecards, and roadmap promotion while demoting unreliable behavior.

**Current modules/docs:**
- `docs/cognitive-runtime.md` — skill crystallization and council trace design.
- `docs/EVALUATION_SCORECARD.md` — public evaluation framing.
- `docs/roadmap/MASTERPLAN.md` — multi-phase product roadmap.

**Status:** Planned/partial. Growth design exists; future work must prove promotion/demotion with tests and scorecards.

## Design Rules

1. **Every organ must be observable.** Add events, diagnostics, or tests before claiming runtime behavior.
2. **Every action crosses the immune system.** The model may propose; deterministic governance decides.
3. **Every non-trivial task should build a brain workspace.** Use context unrolling for provenance, confidence, and verification before action.
4. **Every public claim must be mapped.** If an organ is only planned, say planned.
5. **Every daily sprint should improve one organ.** Prefer earliest incomplete phase unless a real user blocker is more urgent.

## Phase-0 Acceptance Status

- Organ systems and boundaries: documented here.
- Existing modules mapped to organs: documented here.
- Unsupported organs labeled planned/partial: documented here.
- Roadmap link: `docs/roadmap/MASTERPLAN.md`.
- Readiness gate: `organism_architecture` check in `src/agi_runtime/diagnostics/public_readiness.py`.
