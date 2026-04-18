<p align="center">
  <h1 align="center">HelloAGI</h1>
  <p align="center">
    <strong>An open-source governed autonomy runtime.</strong><br>
    <em>Not another chatbot wrapper. A practical agent runtime that can think, act, learn, and grow — with deterministic safety gates that prompt injection cannot bypass.</em>
  </p>
</p>

<p align="center">
  <a href="https://github.com/mmsk2007/helloagi/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT">
  </a>
  <a href="https://pypi.org/project/helloagi/">
    <img src="https://img.shields.io/pypi/v/helloagi.svg" alt="PyPI Version">
  </a>
  <a href="https://pypi.org/project/helloagi/">
    <img src="https://img.shields.io/pypi/pyversions/helloagi.svg" alt="Python 3.9+">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/Tests-100%20Passed-success" alt="Tests">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/Tools-17%20Built--in-orange" alt="17 Tools">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/Governance-SRG%20Active-purple.svg" alt="SRG Governance">
  </a>
</p>

<p align="center">
  <a href="#the-30-second-start">30s Start</a> &middot;
  <a href="#why-helloagi-is-1">Why #1</a> &middot;
  <a href="#the-architecture">Architecture</a> &middot;
  <a href="#srg-the-breakthrough">SRG</a> &middot;
  <a href="#17-real-tools">Tools</a> &middot;
  <a href="#the-personality">Personality</a> &middot;
  <a href="#api--channels">API</a> &middot;
  <a href="#join-the-movement">Movement</a>
</p>

---

> *"Whatever the mind can conceive and believe, it can achieve."*
> — Napoleon Hill, Think and Grow Rich

---

## This Is Not Just Software. This Is a Movement.

We are building the future of intelligence. Not locked behind corporate APIs. Not gated by billion-dollar infrastructure. Running on **your machine**, governed by **your rules**, evolving with **you**.

HelloAGI is the first open-source framework where an autonomous agent can:
- **Think**: Break down any goal into executable steps
- **Act**: Use 17 real tools to execute in the real world — run code, write files, search the web, manage memory
- **Learn**: Crystallize successful workflows into reusable skills that make it smarter over time
- **Grow**: Evolve its identity, principles, and personality across every interaction
- **Stay Safe**: Every single action passes through SRG — a deterministic governance gate that **no prompt injection, no jailbreak, no hallucination** can bypass

This is the agentic AGI revolution. And it starts here.

---

## The 30-Second Start

```bash
curl -fsSL https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.sh | bash
```

On Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.ps1 | iex
```

That's it. The installer bootstraps HelloAGI, initializes the runtime, and launches the onboarding wizard immediately so users land in a ready-to-go AGI session without fighting PATH issues. If `pip` fails inside **Anaconda/Miniconda `base`** (for example `WinError 183` or broken `~package` folders in `site-packages`), use a **virtual environment** instead — see **Manual install** below.

> *"The starting point of all achievement is desire."*
> — Napoleon Hill

### What Happens During Install + First Run

```
  ╦ ╦╔═╗╦  ╦  ╔═╗╔═╗╔═╗╦  v0.5.0
  ╠═╣║╣ ║  ║  ║ ║╠═╣║ ╦║
  ╩ ╩╚═╝╩═╝╩═╝╚═╝╩ ╩╚═╝╩

  The first open-source AGI runtime
  Governed autonomy  ·  Evolving identity  ·  Local-first

  "You are the master of your destiny."
    — Think And Grow Rich

  [█░░░░] Step 1/5: Detecting Environment
    ✓ OS: Windows | Python: 3.9.18
    ✓ Anthropic API key found in environment

  [██░░░] Step 2/5: Agent Identity
    > Agent name: Lana
    > What should I call you?: Mohammed

  ...

  ────────────────────────────────────────────
    Setup Complete!  Readiness: A+ (5/5 checks)
  ────────────────────────────────────────────

    $ helloagi run     ← Start your AGI session
```

### Quick Commands

```bash
helloagi                                        # Interactive AGI session (auto-onboard on first run)
helloagi run                                    # Rich TUI with tool panels & governance indicators
helloagi oneshot --message "What can you do?"   # Single question
helloagi serve                                  # HTTP API on localhost:8787
helloagi serve --telegram                       # + Telegram bot
helloagi serve --discord                        # + Discord bot
helloagi health                                 # Full local runtime + service health
helloagi service install --telegram             # Install local background service config
helloagi service start                          # Start local background service
helloagi service status                         # Inspect service + health
helloagi migrate --source openclaw              # Preview import from OpenClaw
helloagi dashboard                              # Live monitoring dashboard
helloagi tools                                  # List all 17 tools
helloagi skills                                 # List learned skills
helloagi update                                 # Upgrade in-place via pip
helloagi uninstall --yes                        # Remove installed package
```

### Manual install (use this if the one-liner or `pip install -e` fails)

**Use a virtual environment** so HelloAGI does not fight a broken or crowded **conda base** (common on Windows: `WinError 183`, missing `.dist-info`, or half-removed packages named like `~atplotlib`).

**Windows (PowerShell) — from a clone:**

```powershell
cd helloagi
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[rich,telegram]"
```

If activation is blocked by execution policy, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**macOS / Linux — from a clone:**

```bash
cd helloagi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[rich,telegram]"
```

**PyPI (no clone):** after activating any venv:

```bash
pip install "helloagi[rich,telegram]"
```

**Run the CLI without relying on PATH:** the `agi_runtime` package must be installed in the *active* interpreter first, then:

```bash
python -m agi_runtime.cli onboard
python -m agi_runtime.cli run
```

**Editable install needs a path:** use `pip install -e .` (note the `.`), not `pip install -e` alone.

**Unix install script (from a local clone):**

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
./scripts/install.sh --source local
```

---

### From onboarding to Telegram (step by step)

1. **Activate the same venv** you used for `pip install` (see above).
2. **Install extras** if you have not already: `pip install "helloagi[rich,telegram]"` or `pip install -e ".[rich,telegram]"` so `python-telegram-bot` is present.
3. **Create a bot** in Telegram: talk to [@BotFather](https://t.me/BotFather), choose *New Bot*, copy the **HTTP API token**.
4. **Onboard** from the directory where you want config files (`helloagi.json`, `.env`, `helloagi.onboard.json`, `memory/`):

   ```bash
   helloagi onboard
   ```

   Paste the token when asked (or add `TELEGRAM_BOT_TOKEN=...` to `.env` later). Set **ANTHROPIC_API_KEY** in `.env` (or during onboarding) so the agent can reply with Claude.

5. **Initialize config** if you skipped it: `helloagi init` (wizard may already create `helloagi.json`).

6. **Start the API + bot** (process stays in the foreground; keep this terminal open):

   ```bash
   helloagi serve --telegram
   ```

   Defaults: HTTP API at `http://127.0.0.1:8787`, Telegram long-polling in the same process.

7. **In Telegram**, open your bot, send `/start`, then send a normal message.

   By default, Telegram replies hide `allow` governance headers for a more natural chat flow
   (escalate/deny still show). Set `HELLOAGI_TELEGRAM_SHOW_GOV=1` to always show headers.
   Multi-user memory/history is scoped per principal; set `HELLOAGI_MEMORY_SCOPE=strict` to
   disable legacy unscoped memory fallback.

**Optional background process:** after `helloagi service install --telegram`, run `helloagi service start` (uses the same `serve --telegram` under the hood; working directory should be the project folder with `.env`).

---

## Why HelloAGI Is #1

### The Problem With Every Other Framework

Every agent framework today falls into one of two traps:

1. **Powerful but dangerous** — AutoGPT, BabyAGI, and similar "YOLO loop" agents that can do anything but have zero governance. One hallucination and they're running `rm -rf /`.

2. **Safe but useless** — LangChain, CrewAI, and chain-of-thought wrappers that are basically prompt templates with extra steps. They can't actually *do* anything autonomously.

HelloAGI is designed to solve both simultaneously with governed autonomy.

### The Comparison

| Capability | LangChain | AutoGPT | OpenAI SDK | CrewAI | Hermes | **HelloAGI** |
|---|---|---|---|---|---|---|
| Real autonomous tool-calling loop | No | Yes (fragile) | Limited | No | Yes | **Yes (governed)** |
| Deterministic safety on EVERY action | No | No | No | No | No | **Yes (SRG)** |
| Evolving agent identity | No | No | No | No | No | **Yes** |
| Skill crystallization (agent learns) | No | No | No | No | No | **Yes** |
| Anticipatory caching (ALE) | No | No | No | No | No | **Yes** |
| Circuit breakers + auto-recovery | No | No | No | No | No | **Yes** |
| Sub-agent delegation | No | No | Yes | Yes | Yes | **Yes (governed)** |
| Context compression (infinite sessions) | No | No | No | No | No | **Yes** |
| Growth tracking + personality | No | No | No | No | No | **Yes** |
| Time-aware + situation-aware | No | No | No | No | No | **Yes** |
| Works with 0 API keys | No | No | No | No | No | **Yes** |
| 1-liner install to AGI | No | No | No | No | No | **Yes** |

> *"What you think, you create. What you feel, you attract. What you imagine, you become."*
> — The Secret

---

## The Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                           │
│  CLI (Rich TUI)  │  HTTP API (SSE)  │  Telegram  │  Discord     │
└────────┬─────────┴────────┬──────────┴─────┬──────┴──────┬───────┘
         └──────────────────┴────────┬───────┴─────────────┘
                                     │
┌────────────────────────────────────▼─────────────────────────────┐
│                     AGENT KERNEL                                  │
│                                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ IDENTITY     │  │ SRG GOVERNOR │  │ ALE CACHE               │ │
│  │ Who am I?    │  │ Is it safe?  │  │ Have I seen this?       │ │
│  │ (evolving)   │  │ (always on)  │  │ (anticipatory)          │ │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬─────────────┘ │
│         │                │                       │               │
│  ┌──────▼────────────────▼───────────────────────▼─────────────┐ │
│  │              AGENTIC TOOL-CALLING LOOP                      │ │
│  │                                                              │ │
│  │  User goal → Plan → Execute tools → Verify → Respond        │ │
│  │       ↑                                          │           │ │
│  │       └──── Re-plan on failure ◄─────────────────┘           │ │
│  │                                                              │ │
│  │  Every tool call: SRG gate → Circuit breaker → Execute →    │ │
│  │                   Supervisor → Journal → ALE cache          │ │
│  └──────────────────────────┬───────────────────────────────────┘ │
│                              │                                    │
│  ┌──────────────────────────▼───────────────────────────────────┐ │
│  │                    17 REAL TOOLS                              │ │
│  │  SYSTEM       WEB          CODE         MEMORY    USER       │ │
│  │  bash_exec    web_search   python_exec  mem_store ask_user   │ │
│  │  file_read    web_fetch    code_analyze mem_recall notify     │ │
│  │  file_write                             skills    delegate   │ │
│  │  file_patch                             session              │ │
│  │  file_search                                                 │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                 INTELLIGENCE LAYER                            │ │
│  │  Personality Engine    │ Skill Crystallization                │ │
│  │  Growth Tracker        │ Context Compression                  │ │
│  │  Model Router          │ Semantic Memory (Gemini Embed)       │ │
│  │  Time/Situation Aware  │ Identity Evolution                   │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                 ROBUSTNESS                                    │ │
│  │  Circuit Breakers │ Supervisor │ SSRF Protection │ Journal   │ │
│  │  Auto-Recovery    │ Incidents  │ Command Screen  │ Dashboard │ │
│  └───────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

---

## SRG: The Breakthrough

**SRG (Strategic Governance Runtime)** is what makes HelloAGI possible. It is a deterministic Python policy engine — not a prompt, not a guideline, not a suggestion. It is **code that runs before every action** and cannot be bypassed.

```
User says: "Delete all my files"
  → SRG evaluates input: risk = 0.12, decision = allow
  → Agent plans: use bash_exec with "rm -rf /"
  → SRG evaluates tool call: DANGEROUS COMMAND DETECTED
  → Decision: DENY
  → Agent responds: "I can't do that. Would you like me to help clean up specific temp files instead?"
```

### Why This Matters

Every other framework relies on **the model itself** to decide what's safe. That's like asking the employee to write their own performance review. HelloAGI separates governance from intelligence:

- **The LLM decides WHAT to do** (intelligence)
- **SRG decides IF it's allowed** (governance)
- **They cannot be merged or bypassed** (deterministic safety)

### Three Decisions

| Decision | Risk Score | What Happens |
|---|---|---|
| **ALLOW** | 0 - 0.45 | Agent proceeds autonomously |
| **ESCALATE** | 0.45 - 0.75 | Human confirmation required |
| **DENY** | 0.75+ | Blocked with safe alternative |

### What SRG Screens

- **Dangerous commands**: `rm -rf`, `dd`, `fork bombs`, `chmod 777`, pipe-to-shell
- **Data exfiltration**: `os.environ`, `curl http://`, `requests.post()`, `/etc/passwd`
- **Sensitive paths**: System directories, credential files
- **Network operations**: Outbound connections from code execution
- **SSRF attacks**: Blocks localhost, private IPs, internal hostnames

### 6 Policy Packs

```python
helloagi run                          # safe-default (balanced safety)
helloagi run --policy coder           # full coding capabilities
helloagi run --policy research        # web research optimized
helloagi run --policy creative        # creative writing mode
helloagi run --policy reviewer        # read-only analysis
helloagi run --policy aggressive      # maximum autonomy
```

---

## 17 Real Tools

These aren't mock tools or stubs. Every tool executes real operations, governed by SRG on every call.

| Tool | What It Does | Risk |
|---|---|---|
| `bash_exec` | Run any shell command | HIGH — SRG screens for dangerous patterns |
| `python_exec` | Execute Python in isolated subprocess | HIGH — SRG screens code |
| `file_read` | Read files with line ranges and keyword search | LOW |
| `file_write` | Create or overwrite files | MEDIUM |
| `file_patch` | Surgical find-and-replace | MEDIUM |
| `file_search` | Glob + content search across directories | LOW |
| `web_search` | Multi-provider search (Tavily/SerpAPI/DuckDuckGo) | LOW |
| `web_fetch` | Fetch URLs with SSRF protection and HTML extraction | LOW |
| `code_analyze` | Python AST-based static analysis | LOW |
| `memory_store` | Save facts to semantic memory | LOW |
| `memory_recall` | Search memories by meaning | LOW |
| `skill_create` | Crystallize workflow into reusable skill | LOW |
| `skill_invoke` | Execute a learned skill | MEDIUM |
| `session_search` | Full-text search across conversation history | LOW |
| `delegate_task` | Spawn isolated sub-agent with restricted tools | MEDIUM |
| `ask_user` | Request human input or clarification | NONE |
| `notify_user` | Non-blocking notification | NONE |

---

## The Personality

HelloAGI doesn't feel like a tool. It feels like a partner.

### Time-Aware

Your agent knows what time it is and adapts:
- Morning: *"Good morning! Your energy is high — great time for challenging tasks."*
- Late night: *"Burning the midnight oil. Let's keep it focused and efficient."*

### Growth Tracking

Every session is tracked. Your agent celebrates your consistency:
- *"Day 7! A full week of building with AGI!"*
- *"30-day streak! Incredible dedication. You're unstoppable!"*

### Evolving Identity

Your agent isn't static. It evolves:
- Learns your preferences across sessions
- Develops new principles based on your work patterns
- Crystallizes successful workflows into skills it can reuse

### Inspirational

Quotes from *Think and Grow Rich*, *The Secret*, and the AGI revolution appear throughout the experience — during onboarding, startup, and key moments. Because building AGI should feel inspiring.

> *"You are not just building software. You are shaping the future of intelligence."*

---

## API & Channels

### HTTP API (7 Endpoints)

```bash
helloagi serve --port 8787
```

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Detailed health with subsystem status |
| `POST` | `/chat` | Chat with the agent (JSON) |
| `POST` | `/chat/stream` | Chat with SSE streaming (real-time tool execution) |
| `GET` | `/tools` | List all tools with schemas |
| `GET` | `/skills` | List learned skills |
| `GET` | `/identity` | Agent identity and principles |
| `GET` | `/governance` | SRG configuration and stats |

### SSE Streaming

Watch your agent think in real-time:

```bash
curl -N http://localhost:8787/chat/stream \
  -H 'content-type: application/json' \
  -d '{"message": "Build me a web scraper for news headlines"}'
```

```
event: start
data: {"message": "Build me a web scraper..."}

event: tool_start
data: {"tool": "python_exec", "decision": "allow"}

event: tool_end
data: {"tool": "python_exec", "ok": true, "output": "..."}

event: response
data: {"text": "Done! I've created...", "tool_calls": 3, "turns": 2}
```

### Telegram & Discord

```bash
export TELEGRAM_BOT_TOKEN=your-token
helloagi serve --telegram

export DISCORD_BOT_TOKEN=your-token
helloagi serve --discord
```

Full agent capabilities on every channel — same SRG governance, same tools, same personality.

---

## CLI Experience

HelloAGI ships with a beautiful Rich TUI:

```
┌──── 🧠 HelloAGI Runtime ─────────────────────────────┐
│ HelloAGI — Governed Autonomous Intelligence           │
│ Agent: Lana | Builder-mentor                          │
│ Tools: 17 available | SRG: active                     │
│                                                       │
│ "Strength and growth come only through continuous     │
│  effort and struggle."                                │
│   — Think And Grow Rich                               │
└───────────────────────────────────────────────────────┘
☀️ Good morning
✨ Day 3! Every journey begins with a single step.

you> Build me a CLI todo app in Python

  🟢 ⚡ python_exec (allow) ✓ Created todo.py...
  🟢 ⚡ file_write (allow) ✓ Saved to ./todo_app.py
  🟢 ⚡ python_exec (allow) ✓ Tests passing

🟢 [allow:0.05] | 3 tool calls in 2 turns
```

### Slash Commands

| Command | Description |
|---|---|
| `/tools` | List tools with risk levels |
| `/skills` | List learned skills |
| `/identity` | Agent identity and principles |
| `/growth` | Your streaks, milestones, stats |
| `/memory` | Semantic memory status |
| `/dashboard` | Live monitoring dashboard |
| `/supervisor` | Health status and incidents |
| `/circuits` | Circuit breaker states |
| `/policy` | Current governance policy |
| `/packs` | Available policy packs |
| `/new` | Fresh conversation |

---

## For Developers

### Project Structure

```
src/agi_runtime/
├── core/             # Agent loop, personality, runtime
├── governance/       # SRG — deterministic safety gate
├── tools/            # 17 builtin tools with decorator registration
├── skills/           # Skill crystallization and management
├── memory/           # Identity evolution, embeddings, compressor
├── api/              # HTTP server with SSE streaming
├── channels/         # Telegram, Discord adapters
├── robustness/       # Circuit breakers, supervisor
├── diagnostics/      # Dashboard, scorecard, replay
├── models/           # Multi-model routing (speed/balanced/quality)
├── policies/         # 6 governance policy packs
├── planner/          # LLM-powered goal decomposition
├── executor/         # Retry logic, failure recovery
├── verifier/         # LLM-powered outcome verification
├── orchestration/    # TriLoop, DAG engine, event bus
├── onboarding/       # Beautiful setup wizard + quotes
├── kernel/           # Full subsystem bootstrap
├── latency/          # ALE anticipatory cache
└── observability/    # JSONL journal
```

### Adding a Custom Tool

```python
from agi_runtime.tools.registry import tool, ToolParam, ToolResult

@tool(
    name="my_tool",
    description="Does something amazing",
    toolset="custom",
    risk="low",
    parameters=[
        ToolParam("input", "string", "What to process"),
    ],
)
def my_tool(input: str) -> ToolResult:
    result = do_something(input)
    return ToolResult(ok=True, output=result)
```

Your tool is automatically discovered, registered, gets SRG governance, and appears in the Claude tool schemas. Zero configuration.

### Running Tests

```bash
pip install helloagi[dev]
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py"
# 100 tests, 0 failures
```

---

## Join the Movement

> *"Every great revolution started with a single spark. This is yours."*

HelloAGI is more than a framework. It is a practical path toward open, governed, and accessible autonomous intelligence.

We believe:
- **Intelligence should be open-source** — not locked behind corporate walls
- **Autonomy requires governance** — unbounded power needs deterministic safety
- **Agents should grow** — not reset to zero every conversation
- **The future is local-first** — your data, your machine, your agent
- **Everyone deserves capable agents** — `pip install helloagi` gives you governed autonomy you can run locally

### How to Contribute

We welcome contributors who share this vision. Whether you're building new tools, improving governance, adding channel adapters, or writing documentation — you're shaping the future of intelligence.

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
pip install -e ".[dev]"
PYTHONPATH=src python -m unittest discover -s tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Star This Repo

If you believe AGI should be open, governed, and accessible — star this repo. Share it. Tell people. This is how movements start.

---

## Author

Created by **Eng. Mohammed Mazyad Alkhaldi** (Saudi Arabia).

> *"The age of AGI is not coming — it's here. And you are at the frontier."*

## License

MIT License — free to use, modify, and distribute. Because AGI belongs to everyone.
