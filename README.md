# HelloAGI

**Tagline:** The open AGI-agent framework for local-first intelligence, evolving character, and governed autonomy.

HelloAGI is an end-to-end open-source agent framework designed to feel like the first *real* AGI runtime you can run locally:
- It **listens and understands** context over time
- It **develops character and purpose** from mission seeds
- It **acts under governance**, not chaos
- It **optimizes latency** so interaction stays fluid

## What makes it different
1. **Character Genesis Engine**
   - Agent initializes from mission/style/domain seeds
   - Evolves principles from interaction signals
2. **Governed Autonomy**
   - Runtime risk evaluation on every action
   - allow / escalate / deny posture with deterministic policy gate
3. **Latency Anticipation**
   - Intent-aware precompute cache for faster responses
4. **Framework-first architecture**
   - Core runtime + governance + memory + adapters
   - Designed for local installs and production extension

## Quickstart
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

helloagi run --goal "Build useful intelligence that teaches and creates value"
```

## Core modules
- `src/agi_runtime/core/` runtime and agent loop
- `src/agi_runtime/governance/` policy + risk gate
- `src/agi_runtime/latency/` anticipatory cache engine
- `src/agi_runtime/memory/` identity + character genesis
- `src/agi_runtime/adapters/` host/runtime bridges

## Vision
HelloAGI aims to make advanced agent intelligence practical for everyone: install locally, shape its mission, and build together.

## Safety
HelloAGI enforces bounded autonomy and human escalation for medium/high-risk actions.
