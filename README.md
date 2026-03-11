<p align="center">
  <strong>HelloAGI</strong><br>
  <em>The first open-source framework to achieve AGI-class autonomous behavior through governed intelligence.</em>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> &middot;
  <a href="#why-helloagi">Why HelloAGI</a> &middot;
  <a href="#architecture">Architecture</a> &middot;
  <a href="#srg-the-breakthrough">SRG</a> &middot;
  <a href="#gemini-embedding-2-integration">Embeddings</a> &middot;
  <a href="#cli-reference">CLI</a> &middot;
  <a href="#api">API</a> &middot;
  <a href="docs/roadmap/MASTERPLAN.md">Roadmap</a>
</p>

---

## What is HelloAGI?

HelloAGI is a production-grade, local-first AGI orchestration runtime. It is the first framework to combine **unbounded autonomous agent loops** with **deterministic governance enforcement** — meaning the agent can plan, execute, reflect, and self-correct across multi-step goals without losing safety guarantees at any point in the chain.

Other agent frameworks give you tool-calling wrappers or prompt chains. HelloAGI gives you a **complete runtime**: governance gates, identity evolution, anticipatory caching, workflow orchestration, persistent memory, and full observability — all running locally, all open source.

```
you> help me build an autonomous growth agent
agent[allow:0.05]> [Lana | Builder-mentor] Plan: define objective,
    map constraints, execute measurable steps, verify outcomes.
```

---

## Why HelloAGI is Different

### The AGI Gap in Existing Frameworks

| Capability | LangChain / CrewAI | AutoGPT | OpenClaw | **HelloAGI** |
|---|---|---|---|---|
| Autonomous multi-step execution | Limited | Yes (fragile) | Yes | **Yes (governed)** |
| Deterministic safety gate on every action | No | No | Partial | **Yes (SRG)** |
| Evolving agent identity & memory | No | Basic | No | **Yes** |
| Anticipatory latency optimization | No | No | No | **Yes (ALE)** |
| Plan / Execute / Verify loop | No | Partial | No | **Yes (TriLoop)** |
| DAG workflow orchestration | No | No | Yes | **Yes** |
| Local-first (no cloud dependency) | Partial | Partial | No | **Yes** |
| Full observability journal | No | No | Partial | **Yes** |
| Multimodal semantic memory (Gemini Embedding 2) | No | No | No | **Yes** |
| Policy packs (safe-default, research, aggressive-builder) | No | No | No | **Yes** |

Most agent frameworks are either **powerful but unsafe** (AutoGPT-style yolo loops) or **safe but limited** (simple chain-of-thought wrappers). HelloAGI solves this with the **Strategic Governance Runtime (SRG)** — a deterministic policy layer that evaluates every single action before execution, making true autonomous AGI behavior possible without sacrificing safety.

### What Makes This AGI

AGI is not about a single model being "smart enough." It is about a **runtime architecture** that enables:

1. **Open-ended goal pursuit** — the agent decomposes any goal into steps, executes them, and verifies outcomes
2. **Self-correction** — the TriLoop (Plan -> Execute -> Verify) catches failures and adapts
3. **Bounded autonomy** — SRG governance ensures the agent operates within defined safety boundaries while still acting independently
4. **Persistent identity** — the agent evolves its character, principles, and domain expertise across sessions
5. **Real-time governance** — every action is risk-scored and policy-gated before execution

HelloAGI is the first framework to ship all five of these as a single, integrated runtime.

---

## SRG: The Breakthrough

**SRG (Strategic Governance Runtime)** is the core innovation that makes HelloAGI possible. It is a deterministic, policy-driven governance sidecar that runs **before every action** the agent takes.

### How SRG Works

```
Input -> SRG Governor -> Risk Score -> Decision
                |
                v
    +------------------------+
    | risk <= 0.45 -> ALLOW  |  Agent proceeds autonomously
    | risk <= 0.75 -> ESCALATE | Agent pauses for human confirmation
    | risk >  0.75 -> DENY   |  Agent refuses and suggests alternatives
    +------------------------+
```

SRG uses **policy packs** — configurable rule sets that define what the agent can and cannot do:

- **safe-default** — general-purpose safety boundaries
- **research** — tuned for scientific and analytical workflows
- **aggressive-builder** — broader autonomy for experienced developers

This is not prompt-based safety. It is **deterministic, runtime-enforced governance** that cannot be bypassed by prompt injection or model hallucination. The governance gate runs in Python, outside the LLM, on every single action.

### Why This Matters

Every other agent framework relies on the model itself to "be safe." That is fundamentally broken — models can be jailbroken, hallucinate unsafe actions, or simply make mistakes. SRG moves safety enforcement **out of the model and into the runtime**, making it deterministic and auditable.

---

## Quickstart

### Prerequisites

- Python 3.9+
- An Anthropic API key (for Claude backbone) — *optional for local-only mode*

### Install

**Option A: One-line install**
```bash
git clone https://github.com/user/helloagi.git
cd helloagi
./scripts/install.sh
```

**Option B: pip install**
```bash
git clone https://github.com/user/helloagi.git
cd helloagi
pip install -e .
```

**Option C: Docker**
```bash
git clone https://github.com/user/helloagi.git
cd helloagi
docker build -t helloagi:latest .
docker run --rm -p 8787:8787 -e ANTHROPIC_API_KEY=your-key helloagi:latest
```

### Onboard

Run the interactive onboarding wizard to configure your agent:

```bash
helloagi onboard
```

This walks you through:
- Naming your agent
- Setting your timezone and model tier (speed/balanced/quality)
- Configuring API keys (Anthropic, OpenAI, Google)

### First Run

```bash
# Initialize runtime config
helloagi init

# Verify everything is working
helloagi doctor

# Start your agent
helloagi run --goal "Build useful intelligence that teaches and creates value"
```

### Set Up API Keys

Copy the example env file and add your keys:

```bash
cp .env.example .env
# Edit .env with your API keys:
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...        (optional)
#   GOOGLE_API_KEY=...           (optional)
source .env
```

HelloAGI works without API keys in local/template mode. Add an Anthropic key to unlock the full Claude Opus 4.6 backbone.

---

## Architecture

```
                    +------------------+
  User Input ------>|  SRG Governor    |----> DENY (blocked)
                    |  (policy gate)   |
                    +--------+---------+
                             |
                        ALLOW / ESCALATE
                             |
                    +--------v---------+
                    |  Tool Parser     |  /tool plan|summarize|reflect
                    +--------+---------+
                             |
                    +--------v---------+
                    |  ALE Cache       |  Anticipatory latency engine
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Claude Backbone |  Opus 4.6 (or template fallback)
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Identity Engine |  Evolving character & principles
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Journal         |  Full observability (events.jsonl)
                    +------------------+
```

### Core Subsystems

| Subsystem | Path | Purpose |
|---|---|---|
| **Runtime Core** | `src/agi_runtime/core/` | Agent loop, response lifecycle |
| **SRG Governance** | `src/agi_runtime/governance/` | Policy gate, risk scoring, deny/escalate/allow |
| **ALE Cache** | `src/agi_runtime/latency/` | Intent-based anticipatory response cache |
| **Identity** | `src/agi_runtime/memory/` | Evolving agent character, purpose, principles |
| **Tools** | `src/agi_runtime/tools/` | Plan, summarize, reflect (deterministic) |
| **Orchestration** | `src/agi_runtime/orchestration/` | DAG engine, event bus, TriLoop |
| **Planner** | `src/agi_runtime/planner/` | Goal decomposition into steps |
| **Executor** | `src/agi_runtime/executor/` | Step execution with concurrency |
| **Verifier** | `src/agi_runtime/verifier/` | Outcome verification against goals |
| **Model Router** | `src/agi_runtime/models/` | Multi-model routing (speed/balanced/quality) |
| **Policy Packs** | `src/agi_runtime/policies/` | Configurable governance rule sets |
| **Storage** | `src/agi_runtime/storage/` | SQLite persistence, migrations |
| **API** | `src/agi_runtime/api/` | Local HTTP server (/health, /chat) |
| **Observability** | `src/agi_runtime/observability/` | JSONL event journal |
| **OpenClaw Bridge** | `src/agi_runtime/adapters/` | Claude Agent SDK integration |
| **Kernel** | `src/agi_runtime/kernel/` | Bootstrap, subsystem composition |
| **Autonomy** | `src/agi_runtime/autonomy/` | Autonomous multi-step runner |
| **Onboarding** | `src/agi_runtime/onboarding/` | Interactive setup wizard |
| **Diagnostics** | `src/agi_runtime/diagnostics/` | Replay, scorecard, health checks |

### Design Principles

1. **Governance first** — every action passes through SRG before execution
2. **Latency is product** — ALE cache precomputes responses by intent
3. **Identity evolves but stays bounded** — character growth within hard safety rules
4. **Local-first** — runs on your machine, no cloud dependency required
5. **Deterministic core** — testable, reproducible, auditable behavior

---

## CLI Reference

### Setup & Configuration

```bash
helloagi onboard                              # Interactive onboarding wizard
helloagi onboard-status                       # Check onboarding completion
helloagi init                                 # Initialize runtime config (helloagi.json)
helloagi doctor                               # Verify runtime health
helloagi doctor-score                         # Full readiness scorecard
helloagi db-init                              # Initialize SQLite state database
```

### Running the Agent

```bash
helloagi run --goal "your goal here"          # Interactive session
helloagi oneshot --message "single question"  # One-shot query
helloagi auto --goal "ship v1" --steps 5      # Autonomous multi-step execution
helloagi tri-loop --goal "build feature X"    # Plan/Execute/Verify loop
helloagi openclaw --prompt "complex task"     # Claude Agent SDK mode (governed)
```

### Server & API

```bash
helloagi serve --host 127.0.0.1 --port 8787  # Start HTTP API server
```

### Diagnostics & Benchmarks

```bash
helloagi replay-failure                       # Replay last failure from journal
helloagi benchmark-robustness --text "test"   # Noise tolerance benchmark
helloagi orchestrate-demo                     # Run DAG orchestration demo
helloagi db-demo                              # SQLite state store demo
```

---

## API

HelloAGI exposes a local HTTP API when running in server mode.

### Endpoints

**Health check**
```bash
curl http://127.0.0.1:8787/health
```

**Chat**
```bash
curl http://127.0.0.1:8787/chat \
  -H 'content-type: application/json' \
  -d '{"message": "help me build an agent"}'
```

Response:
```json
{
  "response": "Plan: define objective, map constraints, execute...",
  "decision": "allow",
  "risk": 0.05
}
```

---

## Claude Agent SDK Integration

HelloAGI integrates with the Claude Agent SDK as a fully governed agent. The OpenClaw bridge exposes HelloAGI tools as an in-process MCP server:

- `agi_plan` — structured action planning
- `agi_summarize` — text distillation
- `agi_reflect` — retrospective analysis
- `agi_governance_check` — SRG safety validation

```bash
helloagi openclaw --prompt "Help me plan a product launch"
```

```python
import anyio
from agi_runtime.adapters.openclaw_bridge import run_openclaw_agent

task = anyio.run(run_openclaw_agent, "Help me plan a product launch")
print(task.summary)
print(task.requires_human_confirm)  # True if governance escalated
```

---

## Gemini Embedding 2 Integration

HelloAGI integrates [Google's Gemini Embedding 2](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2/) — the first natively multimodal embedding model — to power semantic memory and intent-based retrieval.

### Why Gemini Embedding 2?

Gemini Embedding 2 maps text, images, video, and audio into a **single unified vector space**, which gives HelloAGI capabilities no other agent framework has:

- **Semantic memory search** — find relevant past interactions by meaning, not just keywords
- **Intent-similarity matching** — the ALE cache uses embeddings to match similar queries even when phrased differently
- **Multimodal understanding** — embed and search across text, images, video, and audio in one space
- **Matryoshka dimensions** — flexible vector sizes (768 to 3,072) to balance quality vs. storage cost
- **100+ language support** — the agent's memory works across languages natively

### How HelloAGI Uses It

```
User Input --> Gemini Embedding 2 --> Vector
                                        |
                    +-------------------+-------------------+
                    |                   |                   |
              ALE Cache           Memory Search       Identity Evolution
         (intent matching)    (semantic retrieval)  (principle clustering)
```

The embedding store persists locally to `memory/embeddings.json`, keeping everything local-first.

### Setup

```bash
# Set your Google API key (same key used for Gemini models)
export GOOGLE_API_KEY=your-key

# Or add to .env
echo "GOOGLE_API_KEY=your-key" >> .env
```

### Usage

```python
from agi_runtime.memory.embeddings import GeminiEmbeddingStore

store = GeminiEmbeddingStore()

# Add entries to semantic memory
store.add("How to build autonomous agents safely", metadata={"topic": "safety"})
store.add("Growth strategy for SaaS products", metadata={"topic": "growth"})

# Search by meaning
results = store.search("agent governance and safety patterns", top_k=3)
for r in results:
    print(f"  {r.score:.3f}  {r.text}")
```

Gemini Embedding 2 is optional — HelloAGI works fully without it, but enabling it unlocks semantic memory capabilities that significantly improve the agent's recall and context-awareness.

---

## Testing

```bash
# Run full test suite
make test

# Or directly
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

22 test files covering governance, tools, orchestration, storage, robustness, diagnostics, and end-to-end flows.

---

## Project Structure

```
helloagi/
├── src/agi_runtime/          # Core runtime (72 modules)
│   ├── core/                 # Agent loop & response lifecycle
│   ├── governance/           # SRG policy gate
│   ├── latency/              # ALE anticipatory cache
│   ├── memory/               # Identity & character evolution
│   ├── tools/                # Deterministic tool registry
│   ├── orchestration/        # DAG engine, event bus, TriLoop
│   ├── planner/              # Goal decomposition
│   ├── executor/             # Step execution
│   ├── verifier/             # Outcome verification
│   ├── models/               # Multi-model routing
│   ├── policies/             # Governance policy packs
│   ├── storage/              # SQLite persistence
│   ├── api/                  # HTTP server
│   ├── adapters/             # Claude Agent SDK bridge
│   ├── observability/        # Event journal
│   ├── onboarding/           # Setup wizard
│   ├── diagnostics/          # Replay & scorecard
│   └── ...                   # kernel, autonomy, extensions, etc.
├── tests/                    # 22 test files
├── docs/                     # Architecture, install, roadmap
├── scripts/                  # Install & setup scripts
├── examples/                 # Demo sessions
├── memory/                   # Persisted agent state
├── Dockerfile                # Container build
├── Makefile                  # Common tasks
└── setup.py                  # Package config (v0.3.0)
```

---

## Configuration

### Runtime Config (`helloagi.json`)

Generated by `helloagi init`. Controls mission, style, domain, and file paths.

### Onboarding Config (`helloagi.onboard.json`)

Generated by `helloagi onboard`. Stores agent name, owner, timezone, model tier, and API keys.

### Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | For Claude backbone | Enables Claude Opus 4.6 responses |
| `OPENAI_API_KEY` | Optional | Multi-model routing |
| `GOOGLE_API_KEY` | Optional | Multi-model routing |

### Policy Packs

Configure governance behavior by selecting a policy pack:

| Pack | Use Case | Autonomy Level |
|---|---|---|
| `safe-default` | General purpose | Conservative |
| `research` | Scientific/analytical work | Moderate |
| `aggressive-builder` | Experienced developers | Broad |

---

## Safety & Governance

HelloAGI enforces **bounded autonomy** through the SRG governance gate:

- **Every action** is risk-scored before execution
- **Deny-listed actions** (harm, bypass safeguards, impersonation) are blocked immediately
- **Medium-risk actions** (finance, medical, legal, production deploys) require human confirmation
- **All events** are logged to the observability journal for audit
- **Policy packs** allow tuning governance to your use case

This is not guardrails-as-an-afterthought. Governance is the **first thing that runs** in the agent loop, before any LLM call, tool execution, or response generation.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing guidelines, and how to submit changes.

---

## License

Open source. See [LICENSE](LICENSE) for details.
