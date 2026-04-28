<p align="center">
  <img src="docs/assets/HelloAGI.png" alt="HelloAGI" width="650">
</p>
<h1 align="center">HelloAGI</h1>
<p align="center">
  <strong>An open-source governed autonomy runtime.</strong><br>
  <em>Not another chatbot wrapper. A practical agent runtime that can think, act, learn, and grow — with deterministic safety gates that prompt injection cannot bypass.</em>
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
  <a href="#srg-deterministic-governance">
    <img src="https://img.shields.io/badge/Governance-SRG-purple.svg" alt="SRG Governance">
  </a>
</p>

<p align="center">
  <a href="#the-30-second-start">Install</a> &middot;
  <a href="#what-it-looks-like">Demo</a> &middot;
  <a href="#how-helloagi-is-different">Design</a> &middot;
  <a href="#srg-deterministic-governance">SRG</a> &middot;
  <a href="#dual-system-cognitive-runtime">Cognition</a> &middot;
  <a href="#tools">Tools</a> &middot;
  <a href="#the-architecture">Architecture</a> &middot;
  <a href="#api--channels">API</a> &middot;
  <a href="#contributing">Contribute</a>
</p>

---

HelloAGI is an **open-source autonomous agent runtime with deterministic governance**. The agent plans and uses real tools to do real work, and **every tool call runs through SRG** — a Python policy engine, not a prompt — that cannot be jailbroken by the model it's governing. It runs **local-first** with the option of Telegram, Discord, local voice, and an HTTP API. It keeps **per-principal memory and identity** across sessions, and it's **time-aware** (current date, IANA timezone, UTC anchor in every turn).

## What it looks like

```
you> clean up all .log files older than 30 days in /tmp

  🟡 bash_exec       ESCALATE  risk 0.62  →  awaiting your approval
                     find /tmp -name "*.log" -mtime +30 -delete
  [approve] [deny]

you> approve

  🟢 bash_exec       ALLOW     ran in 0.12s   (42 files removed)
  🟢 memory_store    ALLOW     saved skill "tmp-log-cleanup"

Cleaned 42 log files older than 30 days. I saved this as a skill, so next
time you can just say "clean logs" and I'll run the same workflow.
```

Three things are happening that most agents don't do:
1. **SRG saw the `bash_exec` call, scored it, and blocked it for approval** — the LLM couldn't talk its way past that.
2. **Approval came back through the same Telegram / CLI session** you were in — not a separate dashboard.
3. **The successful workflow became a reusable skill** the agent can invoke by name next time.

---

## The 30-Second Start

```bash
curl -fsSL https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.sh | bash
```

On Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.ps1 | iex
```

That's it. The installer bootstraps HelloAGI, initializes the runtime, and launches the onboarding wizard immediately so users land in a ready-to-go session without fighting PATH issues. If `pip` fails inside **Anaconda/Miniconda `base`** (for example `WinError 183` or broken `~package` folders in `site-packages`), use a **virtual environment** instead — see **Manual install** below.

Docs by goal:
- Install and setup: [docs/install.md](docs/install.md)
- CLI and commands: [docs/cli-reference.md](docs/cli-reference.md)
- Migration: [docs/migration.md](docs/migration.md)
- Channels and extensions: [docs/channels.md](docs/channels.md)
- Security: [docs/security.md](docs/security.md)
- Privacy: [docs/privacy.md](docs/privacy.md)
- Environment variables: [docs/environment.md](docs/environment.md)
- Platforms: [docs/platforms.md](docs/platforms.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
- Upgrade (feature flags, browser extra): [docs/UPGRADE_GUIDE.md](docs/UPGRADE_GUIDE.md)
- Dual-system cognitive runtime: [docs/cognitive-runtime.md](docs/cognitive-runtime.md)
- Vision: [docs/HELLOAGI_VISION.md](docs/HELLOAGI_VISION.md)
- Implementation plan: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)

### What Happens During Install + First Run

The installer launches a real setup flow immediately. The wizard now covers:

- environment detection and optional OpenClaw/Hermes import
- agent identity and focus
- runtime mode: `cli`, `hybrid`, or `service`
- active provider choice: `template`, `anthropic`, or `google`
- provider auth mode: `api_key` or `auth_token`
- Telegram, Discord, and local voice enablement
- local service auth token generation with `HELLOAGI_API_KEY`
- readiness checks and exact next commands

```
  ╦ ╦╔═╗╦  ╦  ╔═╗╔═╗╔═╗╦  v0.5.0
  ╠═╣║╣ ║  ║  ║ ║╠═╣║ ╦║
  ╩ ╩╚═╝╩═╝╩═╝╚═╝╩ ╩╚═╝╩

  Governed autonomy  ·  Evolving identity  ·  Local-first

  [#------] Step 1/7: Environment
    ok Python 3.9.18 on Windows
    ok Anthropic credential detected

  [##-----] Step 2/7: Agent Identity
    > Agent name: Lana
    > What should I call you: Alex
    > Your IANA timezone (e.g. America/New_York): America/New_York

  ...

  Setup complete (5/5 checks passed)

    $ helloagi run
```

### Quick Commands

```bash
helloagi                                        # Interactive AGI session (auto-onboard on first run)
helloagi run                                    # Rich TUI with tool panels & governance indicators
helloagi oneshot --message "What can you do?"   # Single question
helloagi health                                 # Full local runtime + service health
helloagi service install --telegram             # Production: install OS service (then service start)
helloagi service start                          # Start background service (bots go online)
helloagi service status                         # Inspect service + health
helloagi serve                                  # Dev: HTTP API on localhost:8787 (foreground)
helloagi serve --telegram                       # Dev: + Telegram (foreground; closes with terminal)
helloagi serve --discord                        # Dev: + Discord
helloagi serve --voice                          # Dev: + local wake-word voice channel
helloagi migrate --source openclaw              # Preview import from OpenClaw
helloagi migrate --source openclaw --apply --rename-imports
helloagi migrate --source hermes --apply        # Import Hermes secrets + artifacts
helloagi extensions list                        # Inspect optional extensions
helloagi extensions doctor                      # Check extension readiness
helloagi extensions enable telegram             # Persistently enable Telegram extension
helloagi runs list                              # Inspect orchestration runs
helloagi runs show <run-id>                     # Inspect a workflow run
helloagi onboard-status                         # Show saved + live runtime readiness
helloagi dashboard                              # Live monitoring dashboard
helloagi tools                                  # List all 23 built-in tools
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

   The wizard can import an existing OpenClaw/Hermes setup, choose the active provider (`template`, `anthropic`, or `google`), accept `api_key` or `auth_token` auth modes, create the active auth profile, generate `HELLOAGI_API_KEY` for the local service, and enable Telegram, Discord, or local voice in the same flow.

   **Non-interactive `--provider`:** only `template`, `anthropic`, or `google` are valid. **OpenAI** is not a primary `--provider` value. For OpenAI, set `OPENAI_API_KEY` or `OPENAI_AUTH_TOKEN` in `.env` (or use the interactive wizard’s optional OpenAI step).

   For scripted installs, the same setup can run without prompts:

   ```bash
   helloagi onboard --non-interactive --provider anthropic --auth-mode auth_token --runtime-mode service --enable-extension telegram
   ```

   Paste the Telegram token when asked (or add `TELEGRAM_BOT_TOKEN=...` to `.env` later). For model-backed replies, choose Anthropic or Google during onboarding and provide either the API key or auth token for that provider.

5. **Initialize config** if you skipped it: `helloagi init` (wizard may already create `helloagi.json`).

6. **Stay online (recommended):** from the same directory as `.env` / `helloagi.json`, install the OS background service, **start** it, then verify. This matches how OpenClaw uses a gateway **daemon** or how Hermes is often run under **systemd** — one long-lived `serve` process supervised by the OS.

   ```bash
   helloagi service install --telegram
   helloagi service start
   helloagi service status
   ```

   Use the **same Python venv** you used for `pip install` when you run these commands (the unit records an absolute interpreter path at install time).

7. **In Telegram**, open your bot, send `/start`, then send a normal message.

   **Try-it / dev:** to skip the system service and test quickly, run `helloagi serve --telegram` in a terminal you keep open (HTTP API at `http://127.0.0.1:8787`; stops when the terminal closes).

   By default, Telegram replies hide `allow` governance headers for a more natural chat flow
   (escalate/deny still show). Set `HELLOAGI_TELEGRAM_SHOW_GOV=1` to always show headers.
   **Live status** (OpenClaw-style): one placeholder message is edited as tools run, then
   replaced with the final answer. With **`TelegramStreamConsumer`**, **Claude** and **Gemini**
   (when `google-genai` aio streaming is available) also forward **token deltas** through the
   same preview. See [docs/streaming-contract.md](docs/streaming-contract.md). It is **on by default**;
   set `HELLOAGI_TELEGRAM_LIVE=0` to disable.
   `HELLOAGI_TELEGRAM_LIVE_MIN_INTERVAL_MS` (default 550) debounces preview edits to reduce
   rate limits. Multi-user memory/history is scoped per principal; set `HELLOAGI_MEMORY_SCOPE=strict` to
   disable legacy unscoped memory fallback.

   Reminder commands (Telegram-scheduled **notifications**; not a full agent cron runner — see
   [docs/reminders-scheduling.md](docs/reminders-scheduling.md)):
   - `/remind in 30m | check deployment`
   - `/remind tomorrow 9am | standup prep`
   - `/remind cron:0 9 * * * | daily planning`
   - `/reminders`
   - `/reminder_cancel <id>` / `/reminder_pause <id>` / `/reminder_resume <id>` / `/reminder_run_now <id>`

If onboarding offered “prepare background service” and you accepted it, HelloAGI **registered** the service but you still run **`helloagi service start`** unless the wizard asked to start immediately (interactive). HelloAGI uses OS-native backends where possible: Windows Scheduled Task, macOS `launchd`, Linux `systemd --user`.

### Platform, Service, and Secret Model

- Secrets live in environment variables and local `.env`.
- Supported provider secret forms: `*_API_KEY` and `*_AUTH_TOKEN`.
- `HELLOAGI_API_KEY` is the shared auth token for the local API, dashboard, and service-aware clients.
- `helloagi.onboard.json` stores onboarding metadata only, not provider or channel secrets.
- `helloagi auth list|show|activate|deactivate|doctor` manages provider auth profiles and runtime precedence.
- Channels are optional extensions. Use `helloagi extensions doctor` to check readiness.
- `helloagi serve` and `helloagi service install` honor persistently enabled channel extensions.
- `helloagi serve --require-auth` enforces `HELLOAGI_API_KEY` even outside service mode.
- `helloagi runs export <id>` produces a redacted workflow summary for operator review.
- Migration imports secrets into `.env`, copies source artifacts into `memory/imports/`, and copies imported skills into `memory/skills/`.

---

## How HelloAGI Is Different

Most agent stacks fall into one of two camps:

1. **YOLO autonomy** — AutoGPT-style loops that can execute anything the model emits. One hallucination can run `rm -rf /`.
2. **Prompt-chain safety theater** — LangChain/CrewAI-style orchestration where "safety" is a system prompt the model can talk itself out of.

HelloAGI is designed to be **autonomous and governed at the same time**. The things that actually make us different:

- **SRG is code, not a prompt.** Every tool call passes through a deterministic Python policy engine (`governance/srg.py`). The LLM has no way to bypass it because it never runs inside the LLM. See [SRG: Deterministic Governance](#srg-deterministic-governance).
- **Dual-system cognition.** A deterministic router decides per turn whether to use a fast Haiku-driven path (System 1) for familiar tasks or a debating Agent Council (System 2) for novel/risky ones. Successful debates crystallize into Skills, so the runtime gets cheaper and smarter with experience. See [Dual-System Cognitive Runtime](#dual-system-cognitive-runtime).
- **Skill crystallization.** A successful multi-step workflow can be saved as a reusable skill that the agent invokes by name later — not just chat history, real stored procedures.
- **Persistent, per-principal identity and memory.** Each Telegram/Discord/CLI principal has their own state, preferences, timezone, and relationship history. Conversations don't reset to zero.
- **Grounded time awareness.** Every system prompt includes current date, user-local clock, IANA timezone, and a UTC anchor, resolved per-principal. The agent knows what day it is and what zone you're in.
- **ALE (Anticipatory Latency Engine).** A content-addressed cache of the agent's own outputs for recurring intents — identical queries return without burning another model call.
- **Circuit breakers + supervisor.** Tool failures trip breakers; repeated dangerous patterns pause the loop. The agent doesn't spin forever.
- **Runs local-first.** Config, memory, journal, and policy live on your machine. Providers are swappable (Anthropic, Google) — or stub-only for tire-kicking.

### What we don't claim
- We're not faster or cheaper than a bare model call for single-shot Q&A. ALE helps only for recurring intents.
- We're not a replacement for a coding agent like Claude Code or Cursor inside an IDE. HelloAGI is a **runtime** you embed in your own channels (chat, API, service).
- Template-only mode (no provider key) is a setup-check and demo surface, not real autonomy.

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
│  │            COGNITIVE ROUTER  (System 1 vs System 2)          │ │
│  │   familiar + low-risk → Haiku Expert     novel/risky → Council│ │
│  │       ▲   System 2 successes crystallize back into Skills    │ │
│  └──────┬───────────────────────────────────────────────────────┘ │
│         │                                                         │
│  ┌──────▼──────────────────────────────────────────────────────┐ │
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
│  │                    23 REAL TOOLS                              │ │
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

## SRG: Deterministic Governance

**SRG (Safety & Risk Governor)** is a deterministic Python policy engine — not a prompt, not a guideline. It runs **before every action** and cannot be bypassed, because it doesn't live inside the model.

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

## Dual-System Cognitive Runtime

HelloAGI's cognitive runtime mirrors fast/slow human cognition. A **deterministic router** decides, before every reasoning turn, whether the task should use the cheap fast path (**System 1**) or the deep deliberative path (**System 2**). Successful System 2 runs **crystallize into stored Skills**, so the next matching task routes back to System 1 — the runtime gets cheaper and smarter with experience.

```
you> generate a status report from the latest sprint board

  [router] fingerprint=fp_8a2c risk=0.12 skill_match=sprint-status-recap (conf=0.82)
  [router] decision: SYSTEM 1  (Haiku, expert mode)

  🟢 web_fetch       ALLOW   sprint board API
  🟢 file_write      ALLOW   wrote ./reports/sprint-23.md

Done. (1 turn, 2 tool calls — System 1)
```

```
you> design a multi-region failover for our Postgres cluster with zero data loss

  [router] fingerprint=fp_4f31 risk=0.71  no skill match
  [router] decision: SYSTEM 2  (Agent Council)

  [council] round 0
    planner   : proposes synchronous replication + Patroni + HAProxy
    critic    : questions cross-region latency budget on synchronous writes
    risk_audit: flags split-brain risk during regional partition
    synth     : revised plan — quorum-based commit + automated failover
    vote      : yes×4  consensus

  🟡 SRG: ESCALATE — schema-changing tool calls require approval
  ...
```

Three things make this different from a "router-shaped prompt":

1. **The router is code, not a prompt.** Same as SRG. Routing decisions are journaled and replayable.
2. **System 2 is a real debate, not a chain-of-thought trick.** Four LLM agents (Planner, Critic, Risk Auditor, Synthesizer) each take a structured turn with bounded rounds and per-agent vote weights. Consensus triggers an early exit.
3. **Successful debates train the System 1 path.** After three council passes for the same fingerprint with ≥66% inter-agent agreement, the recipe crystallizes into a Skill. The next matching task routes to the cheap path automatically.

### When the runtime picks System 1 vs System 2

| Signal | Goes to |
|---|---|
| Skill match relevance ≥ 0.75 **and** confidence ≥ 0.70 **and** risk < 0.50 | **System 1** (Haiku) |
| Anything else (novel fingerprint, low-confidence skill, risky tool, SRG escalation) | **System 2** (Council) |
| System 1 skill failure rate < 25% over ≥5 uses | Auto-demoted; next match goes to System 2 |

### Self-improvement loop

```
System 2 pass  →  weight nudges (yes-voters +0.06, no-voters -0.10)
              →  fingerprint accumulator
              →  if ≥3 passes & ≥66% agreement: crystallize to Skill
              →  next matching task: routes to System 1
```

Failures decay both the offending Skill's confidence and the offending agent's vote weight. Weight clamping (`[0.1, 3.0]`) prevents a runaway feedback loop from silencing any voice.

### Failure-mode guards

The runtime ships with three concrete guards designed to prevent the agent from burning its turn budget floundering on a task it should know how to solve:

- **Pattern-hint injection** — the system prompt gets a `<task-pattern-hint>` block listing tools the agent has historically used for similar topic words.
- **Stall detector** — after N consecutive silent tool-only turns past a warm-up window, injects a `<turn-budget-warning>` reminder asking the agent to summarize and reconsider its approach.
- **Per-agent circuit breakers** — a council agent that raises or returns parse-error abstains 3+ times gets sidelined for 30s. The debate continues with the rest of the council.

### Activation

The cognitive runtime ships **disabled by default**. Behavior is identical to pre-cognitive HelloAGI until you flip the flag in `helloagi.json`:

```json
{
  "cognitive_runtime": {
    "enabled": true,
    "mode": "dual"
  }
}
```

Recommended ramp: `observe` → `system1_only` → `dual`. Full configuration reference and observability tooling: [docs/cognitive-runtime.md](docs/cognitive-runtime.md).

```bash
# Inspect routing decisions, outcomes, weight calibration:
python scripts/cognitive_dashboard.py

# Replay or re-deliberate a council trace:
python scripts/replay_trace.py <trace_id> [--rerun]
```

---

## Tools

23 built-in tools, all governed by SRG on every call. No mocks — every one executes a real operation.

**System & files**

| Tool | What it does | Risk |
|---|---|---|
| `bash_exec` | Run any shell command | HIGH — SRG screens for dangerous patterns |
| `python_exec` | Execute Python in isolated subprocess | HIGH — SRG screens code |
| `file_read` | Read files with line ranges and keyword search | LOW |
| `file_write` | Create or overwrite files | MEDIUM |
| `file_patch` | Surgical find-and-replace | MEDIUM |
| `file_search` | Glob + content search across directories | LOW |
| `code_analyze` | Python AST-based static analysis | LOW |

**Web**

| Tool | What it does | Risk |
|---|---|---|
| `web_search` | Multi-provider search (Tavily / SerpAPI / DuckDuckGo) | LOW |
| `web_fetch` | Fetch URLs with SSRF protection and HTML extraction | LOW |

**Memory & skills**

| Tool | What it does | Risk |
|---|---|---|
| `memory_store` | Save facts to semantic memory | LOW |
| `memory_recall` | Search memories by meaning | LOW |
| `skill_create` | Crystallize workflow into reusable skill | LOW |
| `skill_invoke` | Execute a learned skill | MEDIUM |
| `session_search` | Full-text search across conversation history | LOW |
| `delegate_task` | Spawn isolated sub-agent with restricted tools | MEDIUM |

**Reminders**

| Tool | What it does | Risk |
|---|---|---|
| `reminder_create` | Schedule one-shot or cron-style reminder | LOW |
| `reminder_list` | List active reminders for this principal | LOW |
| `reminder_cancel` / `reminder_pause` / `reminder_resume` | Lifecycle controls | LOW |
| `reminder_run_now` | Trigger a reminder immediately | LOW |

**Human-in-the-loop**

| Tool | What it does | Risk |
|---|---|---|
| `ask_user` | Request human input or clarification | NONE |
| `notify_user` | Non-blocking notification | NONE |

---

## Identity, Memory, and Time

### Grounded time awareness

Every system prompt includes a `<time-context>` block:

```
Current date: Sunday, 2026-04-19
Local time: 21:22 (+03:00, Asia/Riyadh)
UTC: 2026-04-19T18:22Z
```

Timezone resolution order: **per-principal override → runtime setting → host-local**. So "remind me tomorrow at 9am" means 9am *your* time, not UTC, not server-local. Set your zone during onboarding or via `/start` on Telegram.

### First-run wizard on every channel

CLI and Telegram both onboard a new principal before doing anything else:

- CLI wizard: agent name, owner name, **IANA timezone** (validated against `zoneinfo`), focus, provider, runtime mode, channels, service auth — all persisted.
- Telegram `/start` (new user): "What should I call you?" → "What's your IANA timezone?" → welcome. Stored in the per-principal profile, reused forever after.

### Human-in-the-loop SRG approvals

When SRG escalates a risky tool call on Telegram, the agent sends an inline keyboard and **blocks the agentic loop** until you press Approve or Deny. Timeout (default 5 min) counts as deny. No silent auto-approvals.

### Persistent identity + growth

- `IdentityEngine` carries the agent's name, mission, and principles across restarts and lets them evolve.
- `GrowthTracker` counts sessions, tool calls, skills learned, and streak days — used to personalize prompts, not as gamification dressing.
- `SkillManager` stores successful workflows as named, invocable skills.

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

### Telegram, Discord, and Voice

For **production** uptime, prefer `helloagi service install --telegram` (or `--discord`) then `helloagi service start` from the directory with `.env` — see the step-by-step section above. The snippets below are **foreground / dev** (`serve` stops when the shell exits).

```bash
export TELEGRAM_BOT_TOKEN=your-token
helloagi serve --telegram

export DISCORD_BOT_TOKEN=your-token
helloagi serve --discord

helloagi serve --voice

Then open `http://127.0.0.1:8787/voice/monitor` to see the built-in live voice indicator while the local voice channel is listening, thinking, or speaking.
```

Full agent capabilities on every channel — same SRG governance, same tools, same personality. The voice channel routes reasoning through the normal HelloAGI provider stack and can use either local audio I/O or Gemini audio I/O.

On Windows, the voice channel uses the built-in `System.Speech` APIs through PowerShell, so you do not need a `PyAudio` wheel. On macOS and Linux, the voice extra installs `SpeechRecognition` + `pyttsx3`, and your OS may still need a local microphone backend.
If a user installed base `helloagi` first and enables voice later, they can recover in-place with `helloagi extensions install voice`.

To force a specific Gemini model for agent reasoning, set `HELLOAGI_GOOGLE_MODEL` in `.env`, for example `gemini-flash-latest` or `gemini-3.1-pro-preview`.
To transcribe the microphone with Gemini Live, set `HELLOAGI_VOICE_INPUT_PROVIDER=gemini_live`.
If the Live preview is unavailable, the channel falls back to `HELLOAGI_VOICE_GEMINI_INPUT_MODEL` for one-shot Gemini audio transcription.
To synthesize spoken replies with Gemini instead of the local OS voice, set `HELLOAGI_VOICE_OUTPUT_PROVIDER=gemini_tts` and optionally tune `HELLOAGI_VOICE_GEMINI_TTS_MODEL` / `HELLOAGI_VOICE_GEMINI_TTS_VOICE`.
To add audible “working on it” feedback while the agent is thinking or using tools, set `HELLOAGI_VOICE_WORK_SOUND=piano` (or `chime`, `pulse`, `off`).
To personalize voice acknowledgements, set `HELLOAGI_OWNER_NAME`, and to shape delivery further, use `HELLOAGI_VOICE_GEMINI_TTS_STYLE`. Gemini TTS also supports inline audio tags like `[warmly]`, `[serious]`, and `[whispers]` inside the spoken transcript.
By default, local voice now shares the same principal as local CLI (`local:default`), so memory carries across local text and voice. Override with `HELLOAGI_VOICE_PRINCIPAL_ID` if you intentionally want a separate voice profile.

Telegram reminder scheduler settings:
- `HELLOAGI_REMINDER_TICK_SECONDS` (default `5`)
- `HELLOAGI_REMINDER_STUCK_SECONDS` (default `600`)
- `HELLOAGI_REMINDER_ONESHOT_GRACE_SECONDS` (default `300`)
- `HELLOAGI_REMINDER_TIMEZONE` (default `UTC`)

---

## CLI Experience

HelloAGI ships with a beautiful Rich TUI:

```
┌──── HelloAGI Runtime ────────────────────────────────┐
│ Agent:   Lana (builder-mentor)                        │
│ Tools:   23 available | SRG: active                   │
│ Zone:    Asia/Riyadh  | 2026-04-19  21:22             │
│ Session: day 3 | 12 tool calls this week              │
└───────────────────────────────────────────────────────┘

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
├── cognition/        # Dual-system runtime: router, System 1, System 2 council, crystallizer
├── tools/            # 23 builtin tools with decorator registration
├── skills/           # Skill crystallization and management
├── memory/           # Identity evolution, embeddings, compressor
├── api/              # HTTP server with SSE streaming
├── channels/         # Telegram, Discord, and voice adapters
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
├── intelligence/     # PatternDetector — historical tool/topic stats
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
pytest tests/
```

---

## Design principles

- **Intelligence is open-source.** Not locked behind corporate walls.
- **Autonomy requires governance.** Unbounded power needs deterministic safety — in code, not in a prompt.
- **Agents should grow.** Per-principal memory, identity, and learned skills that persist across sessions.
- **Local-first.** Your data, your machine, your agent. Providers are swappable.

## Contributing

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
pip install -e ".[dev]"
pytest tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. New tools, channel adapters, policy packs, and honest benchmarks are all welcome.

## Author

Created by **Eng. Mohammed Mazyad Alkhaldi** (Saudi Arabia).

> *"Whatever the mind can conceive and believe, it can achieve."* — Napoleon Hill

## License

MIT.
