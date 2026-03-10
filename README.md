# HelloAGI

**Tagline:** The open AGI-agent framework for local-first intelligence, evolving character, and governed autonomy.

HelloAGI is an end-to-end open-source agent framework designed to run locally with real runtime components:
- **Identity + character genesis**
- **Governance gate** (allow/escalate/deny)
- **Latency anticipation cache**
- **Tool calling** (`/tool plan|summarize|reflect`)
- **Observability journal** (`memory/events.jsonl`)
- **Kernel architecture skeleton** (registry, scheduler, capabilities, triggers, metering, supervisor)
- **Workflow orchestration skeleton** (DAG + orchestrator + event bus + tri-loop)
- **Interactive CLI + autonomous mode + local API server**

## Install
```bash
./scripts/install.sh
```

(If you prefer manual install, see `docs/install.md`.)

## Quickstart
```bash
helloagi init
helloagi doctor
helloagi run --goal "Build useful intelligence that teaches and creates value"
```

## CLI commands
```bash
helloagi onboard --path helloagi.onboard.json
helloagi onboard-status --path helloagi.onboard.json
helloagi init --config helloagi.json
helloagi db-init --config helloagi.json
helloagi db-demo --config helloagi.json
helloagi doctor --config helloagi.json
helloagi oneshot --message "help me plan a launch"
helloagi auto --goal "ship v1" --steps 5
helloagi serve --host 127.0.0.1 --port 8787
helloagi orchestrate-demo
helloagi tri-loop --goal "ship v1"
helloagi benchmark-robustness --text "hello how are you"
```

## HTTP API
- `GET /health`
- `POST /chat` with JSON body: `{ "message": "..." }`

Example:
```bash
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/chat -H 'content-type: application/json' -d '{"message":"help me build an agent"}'
```

## Architecture
- `src/agi_runtime/core/` runtime and agent loop
- `src/agi_runtime/governance/` policy + risk gate
- `src/agi_runtime/latency/` anticipatory cache engine
- `src/agi_runtime/memory/` identity + character genesis
- `src/agi_runtime/tools/` local deterministic tools
- `src/agi_runtime/api/` local HTTP server
- `src/agi_runtime/observability/` event journal

## Safety
HelloAGI enforces bounded autonomy and human escalation for medium/high-risk actions.
