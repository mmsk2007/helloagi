# Architecture

## Runtime loop
1. Input arrives
2. SRG governor evaluates risk and policy posture
3. ALE checks anticipatory cache
4. Identity engine updates bounded character/purpose state
5. Agent emits response/action plan
6. Adapter layer can forward actions to host systems (OpenClaw, APIs, etc.)

## Design principles
- Governance first
- Latency is product
- Identity evolves but stays bounded by hard rules
- Local-first installability
