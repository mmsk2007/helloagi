#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- Colors ---------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[HelloAGI]${NC} $1"; }
ok()    { echo -e "${GREEN}[HelloAGI]${NC} $1"; }
warn()  { echo -e "${YELLOW}[HelloAGI]${NC} $1"; }
fail()  { echo -e "${RED}[HelloAGI]${NC} $1"; exit 1; }

# --- Header ----------------------------------------------------------------
echo ""
echo -e "${BOLD}  HelloAGI Installer${NC}"
echo -e "  The first open-source AGI framework with governed autonomy"
echo -e "  ─────────────────────────────────────────────────────────"
echo ""

# --- Check Python ----------------------------------------------------------
info "Checking Python version..."
if ! command -v python3 &>/dev/null; then
    fail "Python 3 is required but not found. Install Python 3.9+ and try again."
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
    fail "Python 3.9+ is required (found $PY_VERSION)."
fi
ok "Python $PY_VERSION detected"

# --- Install ---------------------------------------------------------------
info "Installing HelloAGI..."

if [ "${HELLOAGI_GLOBAL_INSTALL:-}" = "1" ]; then
    python3 -m pip install -e "$ROOT" --quiet
    HELLOAGI_CMD="helloagi"
    ok "Installed globally (editable mode)"
else
    python3 -m pip install "$ROOT" --target "$ROOT/_local_install" --quiet
    HELLOAGI_CMD="PYTHONPATH=$ROOT/_local_install python3 -m agi_runtime.cli"
    ok "Installed locally to _local_install/"
fi

# --- Initialize config -----------------------------------------------------
info "Initializing runtime config..."
eval "$HELLOAGI_CMD init" 2>/dev/null || true
ok "Config ready (helloagi.json)"

# --- API key check ---------------------------------------------------------
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo ""
    warn "ANTHROPIC_API_KEY is not set."
    warn "HelloAGI works in local/template mode without it,"
    warn "but you need it for full Claude Opus 4.6 responses."
    echo ""
    echo -e "  Set it with:  ${BOLD}export ANTHROPIC_API_KEY=sk-ant-...${NC}"
    echo -e "  Or copy:      ${BOLD}cp .env.example .env${NC}  and edit"
    echo ""
fi

# --- Health check ----------------------------------------------------------
info "Running health check..."
eval "$HELLOAGI_CMD doctor" 2>/dev/null || warn "Doctor check had issues (non-critical)"

# --- Done ------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}  Installation complete!${NC}"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo ""
echo -e "  1. Onboard your agent:"
echo -e "     ${CYAN}$HELLOAGI_CMD onboard${NC}"
echo ""
echo -e "  2. Start an interactive session:"
echo -e "     ${CYAN}$HELLOAGI_CMD run --goal \"Build useful intelligence\"${NC}"
echo ""
echo -e "  3. Try autonomous mode:"
echo -e "     ${CYAN}$HELLOAGI_CMD auto --goal \"ship v1\" --steps 5${NC}"
echo ""
echo -e "  4. Start the HTTP API:"
echo -e "     ${CYAN}$HELLOAGI_CMD serve${NC}"
echo ""
echo -e "  Full CLI reference: ${BOLD}$HELLOAGI_CMD --help${NC}"
echo ""
