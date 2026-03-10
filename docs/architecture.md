# Architecture

## Runtime loop
1. Input arrives
2. Governance gate evaluates risk and policy posture
3. Tool parser handles deterministic commands (`/tool ...`)
4. Latency engine checks anticipatory cache
5. Identity engine updates bounded character/purpose state
6. Agent emits response/action plan
7. Journal persists events to JSONL
8. Adapter layer can forward actions to host systems

## Subsystems
- `kernel/`: runtime bootstrapping + subsystem composition
- `registry/`: agent registry
- `capabilities/`: capability grants and checks
- `scheduler/`: time-based execution scheduling
- `background/`: periodic execution tick
- `triggers/`: keyword/event trigger evaluation
- `metering/`: usage counters
- `core/`: orchestration and response lifecycle
- `orchestration/`: event bus + DAG orchestrator + tri-loop
- `models/`: model routing layer
- `governance/`: policy model and risk decisions
- `latency/`: intent-based precompute cache
- `memory/`: identity, purpose, character genesis
- `tools/`: local deterministic capability registry
- `api/`: local HTTP interface (`/health`, `/chat`)
- `observability/`: event journal
- `autonomy/`: autonomous step runner
- `channels/`: channel routing abstraction

## Design principles
- Governance first
- Latency is product
- Identity evolves but stays bounded by hard rules
- Local-first installability
- Deterministic core behavior for testing and reproducibility
