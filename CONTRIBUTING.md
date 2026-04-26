# Contributing to HelloAGI

Thanks for your interest in contributing to HelloAGI. This guide covers everything you need to get started.

## Never commit local secrets or machine state

These paths are **gitignored** on purpose. Do **not** `git add -f` them into the public repo:

- `.env`, `.env.*` — API keys, bot tokens, service auth
- `helloagi.json` — runtime config (may reference local paths)
- `helloagi.onboard.json` — onboarding metadata (names, timezone, detected environment)
- `memory/` — identity, journal, DB, auth profiles, imports

If you need a config sample for a bug report, use **`helloagi.example.json`** and redact any secrets.

**Pre-push:** run `git status` and skim `git diff --staged` for accidental `.env` or token strings. CI may run secret scanning (see `.github/workflows/gitleaks.yml`).

## Config drift and migrations

HelloAGI does **not** yet ship an OpenClaw-style `doctor --fix` that auto-rewrites config. If keys or schema change between releases, prefer **re-running `helloagi onboard`** (interactive or `--non-interactive`) or editing `helloagi.json` / `.env` manually. A dedicated migrate/fix command is deferred until schema churn justifies it.

## Development Setup

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
pip install -e ".[dev]"
```

## Running Tests

```bash
make test
# Or:
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

All changes must pass the existing test suite before merging.

## Project Structure

- `src/agi_runtime/` — core runtime package (72 modules)
- `tests/` — unit, integration, and end-to-end tests
- `docs/` — architecture, install, and roadmap documentation
- `scripts/` — install and setup scripts
- `examples/` — demo sessions

## How to Contribute

### Bug Fixes

1. Open an issue describing the bug
2. Fork the repo and create a branch: `git checkout -b fix/short-description`
3. Write a test that reproduces the bug
4. Fix the bug
5. Run `make test` to verify
6. Open a pull request

### New Features

1. Open an issue describing the feature and its motivation
2. Fork the repo and create a branch: `git checkout -b feat/short-description`
3. Implement the feature with tests
4. Update relevant documentation if needed
5. Run `make test` to verify
6. Open a pull request

### New Policy Packs

Policy packs live in `src/agi_runtime/policies/packs.py`. To add a new pack:

1. Define a new `PolicyPack` instance with `deny_keywords` and `escalate_keywords`
2. Register it in the `get_pack()` function
3. Add a test in `tests/test_policy_packs.py`
4. Document the pack's use case in your PR

### New Tools

Tools are registered in `src/agi_runtime/tools/registry.py`. To add a new tool:

1. Add a handler function
2. Register it in the `ToolRegistry.__init__` method
3. Add tests in `tests/test_tools.py`
4. If the tool should be available via the Claude Agent SDK, add it in `src/agi_runtime/adapters/openclaw_bridge.py`

## Code Style

- Use type hints for function signatures
- Keep modules focused — one responsibility per file
- Follow existing patterns in the codebase
- No unnecessary abstractions or over-engineering

## Governance-Aware Development

HelloAGI enforces governance on every action. When adding features:

- Any new action that modifies external state should pass through the SRG governor
- Consider whether your feature needs deny/escalate keywords in policy packs
- Journal all significant events via the observability layer
- Test governance behavior (allow/escalate/deny) for your feature
- See [docs/srg-integration.md](docs/srg-integration.md) for the full SRG integration guide

## Questions?

Open an issue or start a discussion. We're happy to help you find the right place to contribute.
