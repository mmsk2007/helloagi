# Repo Learnings Incorporated

## OpenClaw
- Strong channel/tool orchestration patterns.
- Need hardened runtime controls for safety and policy enforcement.

## OpenFang
- OS-style architecture, capability model, robust modular layering.
- Informed crate/module boundary style in this runtime.

## SRG (Strategic Governance Runtime)
- Governance sidecar pattern and deterministic control layer.
- Implemented as `SRGGovernor` decision gate before action execution.

## Agency-Agents
- Persona/specialization matters for usability and adoption.
- Applied via identity + purpose engine.

## LifeMaster (LMI-adjacent practical stack)
- Real-world systems need persistence, state, and utility over demos.
- Applied through local state files + repeatable CLI operation.

## Daily learnings
- Autonomous schedulers need dedupe/cancel/queue introspection so retries do not pile up and operators can inspect the next run cleanly.
- Failure replay tooling should preserve line numbers, skip malformed journal entries safely, and surface the last triggering input for faster operator debugging.
- Governance layers should treat prompt-injection and hidden-instruction exfiltration attempts as first-class runtime risks, not just generic unsafe text.
- Scheduler runtimes should expose a compact queue summary (next run, agent counts, reason counts) so operators can spot retry storms and backlog shape without reading raw queue entries.
