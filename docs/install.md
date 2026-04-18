# Install & Setup Guide

## Requirements

- **Python 3.9+** (3.11 recommended)
- **pip** (comes with Python)
- **Anthropic API key** (optional — needed for Claude backbone, not required for local-only mode)

---

## Option A: One-Liner Install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.sh | bash
```

The installer installs `helloagi[rich]`, initializes the runtime, runs a health check, and launches the onboarding wizard immediately.

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.ps1 | iex
```

This follows the same flow on Windows and launches onboarding without requiring the `helloagi` console script to be on PATH yet.

## Option B: PyPI Install

```bash
python -m pip install --user "helloagi[rich,telegram]"
python -m agi_runtime.cli onboard
```

This is the most reliable manual install path because it works even before shell PATH refreshes expose the `helloagi` command.

## Option C: Install from Source

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
./scripts/install.sh --source local
```

Or on Windows:

```powershell
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
.\scripts\install.ps1 -Source local
```

## Option D: Git Install Without Cloning

```bash
curl -fsSL https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.sh | bash -s -- --source git --ref main
```

This installs from the GitHub repo directly instead of PyPI.

## Option E: Docker

```bash
docker pull ghcr.io/mmsk2007/helloagi:latest
docker run --rm -p 8787:8787 -e ANTHROPIC_API_KEY=your-key ghcr.io/mmsk2007/helloagi:latest
```

Or build from source:

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
docker build -t helloagi:latest .
docker run --rm -p 8787:8787 -e ANTHROPIC_API_KEY=your-key helloagi:latest
```

The container runs the HTTP API server on port 8787 by default.

---

## Post-Install Setup

### 1. Run the onboarding wizard

```bash
helloagi onboard
```

The interactive wizard configures agent identity, timezone, model tier, provider keys, and optional Telegram bot token. Non-secret onboarding state is saved to `helloagi.onboard.json`; secrets are written to local `.env`.

### 2. Initialize runtime config

```bash
helloagi init
```

Creates `helloagi.json` with default mission, style, domain, and file paths.

### 3. Set up API keys (optional)

```bash
cp .env.example .env
# Edit .env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...        (optional)
#   GOOGLE_API_KEY=...           (optional)
#   TELEGRAM_BOT_TOKEN=...       (optional)
source .env
```

### 4. Verify the installation

```bash
helloagi doctor
helloagi health
helloagi doctor-score
helloagi update
```

### 5. Initialize the state database (optional)

```bash
helloagi db-init
```

---

## First Session

```bash
# Interactive mode
helloagi run --goal "Build useful intelligence that teaches and creates value"

# Single question
helloagi oneshot --message "help me plan a launch"

# Autonomous multi-step
helloagi auto --goal "ship v1" --steps 5

# Plan/Execute/Verify loop
helloagi tri-loop --goal "build a growth engine"

# Claude Agent SDK mode
helloagi openclaw --prompt "Help me architect a microservice"

# Local background service
helloagi service install --telegram
helloagi service start
helloagi service status

# Migration preview/apply
helloagi migrate --source openclaw
helloagi migrate --source hermes --apply
```

---

## Verify HTTP API

```bash
# Start the server
helloagi serve --host 127.0.0.1 --port 8787

# In another terminal:
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/chat \
  -H 'content-type: application/json' \
  -d '{"message": "help me build an agent"}'
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `command not found: helloagi` | Run `python -m agi_runtime.cli run`, then add Python's user scripts directory to PATH |
| `ModuleNotFoundError: anthropic` | Run `pip install anthropic` |
| Agent returns template responses | Set `ANTHROPIC_API_KEY` for Claude backbone |
| Doctor shows missing files | Run `helloagi init` first |
| Service is installed but not reachable | Run `helloagi service status` then `helloagi health` |
| Want to import another agent setup | Run `helloagi migrate --source openclaw` or `helloagi migrate --source hermes` |
| Port 8787 in use | Use `--port 8788` or stop the other process |
| Need to remove the package safely | Run `helloagi uninstall --yes` |

---

## Uninstall

```bash
# If installed with pip
python -m pip uninstall helloagi

# Clean up generated files
rm -f helloagi.json helloagi.onboard.json
rm -rf memory/
```

See also: [Updating](updating.md) and [Uninstall](uninstall.md)
