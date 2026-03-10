# HelloAGI Masterplan (Multi-Month)

## Mission
Build a production-grade, local-first AGI orchestration framework with governance, memory, planning, tools, model routing, and observability.

## Definition of Done (v1.0)
- End-to-end orchestration runtime (planner + executor + verifier loops)
- Multi-model routing with fallback ladder and cost/latency policy
- Durable memory (episodic + semantic + task graph state)
- Policy governance on every action edge
- Tool/plugin SDK with permission model
- Workflow DAG engine + scheduling + retries + compensation
- API + CLI + dashboard
- Benchmarks and reproducible test harness
- Docker install + release artifacts + ops runbooks

## Program Phases

### Phase 0 (now): Foundation hardening
- Runtime boundaries and package architecture
- State store abstraction
- Orchestrator skeleton with event bus
- Workflow graph primitives

### Phase 1: Core orchestration
- Task graph planner
- Executor with concurrency limits
- Verification/reflection loop
- Recovery and retry policy engine

### Phase 2: Intelligence substrate
- Model router (quality/speed/cost tiers)
- Context packing + memory retrieval
- Long-horizon goal decomposition

### Phase 3: Ecosystem
- Plugin SDK
- External tool adapters
- Governance policy packs

### Phase 4: Productization
- Web dashboard
- Installation pathways
- Benchmarks + public docs

## Operating Cadence
- Daily: implementation + tests
- Every 3 days: tagged capability release
- Weekly: benchmark report (latency/reliability/governance)
