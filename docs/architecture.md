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
- `core/`: orchestration and response lifecycle
- `governance/`: policy model and risk decisions
- `latency/`: intent-based precompute cache
- `memory/`: identity, purpose, character genesis
- `tools/`: local deterministic capability registry
- `api/`: local HTTP interface (`/health`, `/chat`)
- `observability/`: event journal
- `autonomy/`: autonomous step runner

## Design principles
- Governance first
- Latency is product
- Identity evolves but stays bounded by hard rules
- Local-first installability
- Deterministic core behavior for testing and reproducibility
