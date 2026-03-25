# Install & Setup Guide

## Requirements

- **Python 3.9+** (3.11 recommended)
- **pip** (comes with Python)
- **Anthropic API key** (optional — needed for Claude backbone, not required for local-only mode)

---

## Option A: One-Liner Install (recommended)

```bash
pip install helloagi
helloagi onboard
```

This installs the `helloagi` CLI command globally and launches the interactive onboarding wizard.

## Option B: Install from Source

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
pip install -e .
helloagi onboard
```

## Option C: Quick Install Script

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
./scripts/install.sh
```

The install script handles dependency installation, config initialization, and health checks. For a global editable install:

```bash
HELLOAGI_GLOBAL_INSTALL=1 ./scripts/install.sh
```

## Option D: Docker

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

The interactive wizard configures agent identity, timezone, model tier, and API keys. Saves to `helloagi.onboard.json`.

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
source .env
```

### 4. Verify the installation

```bash
helloagi doctor
helloagi doctor-score
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
| `command not found: helloagi` | Run `pip install -e .` or `pip install helloagi` |
| `ModuleNotFoundError: anthropic` | Run `pip install anthropic` |
| Agent returns template responses | Set `ANTHROPIC_API_KEY` for Claude backbone |
| Doctor shows missing files | Run `helloagi init` first |
| Port 8787 in use | Use `--port 8788` or stop the other process |

---

## Uninstall

```bash
# If installed with pip
pip uninstall helloagi

# Clean up generated files
rm -f helloagi.json helloagi.onboard.json
rm -rf memory/
```
