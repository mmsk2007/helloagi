#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[HelloAGI] Installing local package to ./_local_install ..."
python3 -m pip install . --target ./_local_install >/dev/null

echo "[HelloAGI] Installed."
echo "Run:"
echo "  PYTHONPATH=./_local_install python3 -m agi_runtime.cli onboard"
echo "  PYTHONPATH=./_local_install python3 -m agi_runtime.cli doctor"
echo "  PYTHONPATH=./_local_install python3 -m agi_runtime.cli run --goal 'Build useful intelligence'"
