#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

REPO_HTTPS_URL="${HELLOAGI_REPO_URL:-https://github.com/mmsk2007/helloagi.git}"
DEFAULT_GIT_REF="${HELLOAGI_GIT_REF:-main}"
DEFAULT_INSTALL_SOURCE="${HELLOAGI_INSTALL_SOURCE:-pypi}"
DEFAULT_PACKAGE_SPEC="${HELLOAGI_PACKAGE_SPEC:-helloagi[rich]}"
DEFAULT_AUTO_ONBOARD="${HELLOAGI_AUTO_ONBOARD:-1}"
DEFAULT_UPGRADE_PIP="${HELLOAGI_UPGRADE_PIP:-0}"

INSTALL_SOURCE="$DEFAULT_INSTALL_SOURCE"
PACKAGE_SPEC="$DEFAULT_PACKAGE_SPEC"
AUTO_ONBOARD="$DEFAULT_AUTO_ONBOARD"
UPGRADE_PIP="$DEFAULT_UPGRADE_PIP"
GIT_REF="$DEFAULT_GIT_REF"

ROOT=""
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

info()  { echo -e "${CYAN}[HelloAGI]${NC} $1"; }
ok()    { echo -e "${GREEN}[HelloAGI]${NC} $1"; }
warn()  { echo -e "${YELLOW}[HelloAGI]${NC} $1"; }
fail()  { echo -e "${RED}[HelloAGI]${NC} $1"; exit 1; }

print_banner() {
    echo ""
    echo -e "${BOLD}  HelloAGI Installer${NC}"
    echo -e "  Super-fast install for the agentic era"
    echo -e "  Cross-platform Python bootstrap with immediate onboarding"
    echo ""
}

show_help() {
    cat <<'EOF'
HelloAGI installer

Usage:
  curl -fsSL https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.sh | bash
  ./scripts/install.sh [options]

Options:
  --source pypi|git|local   Install source (default: pypi)
  --ref <git-ref>           Git ref to install when source=git (default: main)
  --package <spec>          Override package spec for PyPI install
  --skip-onboard            Install only, do not launch onboarding
  --upgrade-pip             Upgrade pip before installing
  -h, --help                Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            INSTALL_SOURCE="${2:-}"
            shift 2
            ;;
        --ref)
            GIT_REF="${2:-}"
            shift 2
            ;;
        --package)
            PACKAGE_SPEC="${2:-}"
            shift 2
            ;;
        --skip-onboard)
            AUTO_ONBOARD="0"
            shift
            ;;
        --upgrade-pip)
            UPGRADE_PIP="1"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            fail "Unknown option: $1"
            ;;
    esac
done

detect_python() {
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return
    fi
    if command -v python >/dev/null 2>&1; then
        echo "python"
        return
    fi
    fail "Python 3.9+ is required but was not found on PATH."
}

check_python_version() {
    local python_cmd="$1"
    local version
    version="$("$python_cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    local major="${version%%.*}"
    local minor="${version##*.}"
    if [[ "$major" -lt 3 || ( "$major" -eq 3 && "$minor" -lt 9 ) ]]; then
        fail "Python 3.9+ is required (found $version)."
    fi
    ok "Python $version detected"
}

ensure_pip() {
    local python_cmd="$1"
    if "$python_cmd" -m pip --version >/dev/null 2>&1; then
        ok "pip available"
        return
    fi
    info "Bootstrapping pip with ensurepip..."
    "$python_cmd" -m ensurepip --upgrade >/dev/null 2>&1 || fail "pip is unavailable and ensurepip failed."
    ok "pip bootstrapped"
}

maybe_upgrade_pip() {
    local python_cmd="$1"
    if [[ "$UPGRADE_PIP" != "1" ]]; then
        return
    fi
    info "Upgrading pip..."
    "$python_cmd" -m pip install --user --upgrade pip
}

build_install_target() {
    case "$INSTALL_SOURCE" in
        pypi)
            printf '%s\n' "$PACKAGE_SPEC"
            ;;
        git)
            printf '%s\n' "helloagi[rich] @ git+${REPO_HTTPS_URL}@${GIT_REF}"
            ;;
        local)
            [[ -n "$ROOT" ]] || fail "Local install requested but repository root could not be resolved."
            printf '%s\n' "$ROOT[rich]"
            ;;
        *)
            fail "Unsupported install source '$INSTALL_SOURCE'. Use pypi, git, or local."
            ;;
    esac
}

run_post_install() {
    local python_cmd="$1"
    local launcher=("$python_cmd" "-m" "agi_runtime.cli")

    info "Initializing runtime config..."
    "${launcher[@]}" init >/dev/null 2>&1 || true
    ok "Config ready"

    info "Running health check..."
    "${launcher[@]}" doctor || warn "Doctor check reported issues"

    if [[ "$AUTO_ONBOARD" == "1" ]]; then
        echo ""
        info "Launching onboarding wizard..."
        "${launcher[@]}" onboard
        echo ""
    fi

    echo -e "${GREEN}${BOLD}  HelloAGI is installed.${NC}"
    echo ""
    echo -e "  First-run command:"
    echo -e "    ${CYAN}${launcher[*]} run${NC}"
    echo ""
    echo -e "  If your shell already sees the console script, you can also use:"
    echo -e "    ${CYAN}helloagi run${NC}"
    echo ""
}

print_banner

PYTHON_CMD="$(detect_python)"
info "Checking Python..."
check_python_version "$PYTHON_CMD"
ensure_pip "$PYTHON_CMD"
maybe_upgrade_pip "$PYTHON_CMD"

INSTALL_TARGET="$(build_install_target)"
info "Installing HelloAGI from ${INSTALL_SOURCE}..."
"$PYTHON_CMD" -m pip install --user --upgrade "$INSTALL_TARGET"
ok "Package installed"

run_post_install "$PYTHON_CMD"
