# CLI Reference

## Runtime

- `helloagi run --policy <pack>`
- `helloagi oneshot --message "..."`
- `helloagi auto --goal "..." --steps <n>`
- `helloagi tri-loop --goal "..."`
- `helloagi openclaw --prompt "..."`
- `helloagi context-plan --goal "Fix tests/test_cli_contract.py::TestCLIContract::test_context_plan and src/agi_runtime/cli.py" --task-type coding` — show a Context Unrolling plan: selected task-relevant primitives, typed workspace summary with provenance/confidence/observed/generated/verified state, observed file/test artifact references, and high-risk action gate
- `helloagi context-plan --goal "Delete temp build artifacts after confirming scope" --task-type operations` — show risk-identification and scope-verification primitives before high-risk operational actions

## Service and health

- `helloagi doctor`
- `helloagi health`
- `helloagi serve --require-auth`
- `helloagi service install [--telegram] [--discord] [--extension <name>] [--workdir <path>]`
- `helloagi service start`
- `helloagi service stop`
- `helloagi service status`
- `helloagi service uninstall`

## Onboarding and auth

- `helloagi onboard`
- `helloagi onboard --non-interactive --provider anthropic --auth-mode auth_token`
- `helloagi onboard --non-interactive --runtime-mode service --enable-extension telegram`
- `helloagi onboard-status`
- `helloagi auth list`
- `helloagi auth show <profile>`
- `helloagi auth activate <profile>`
- `helloagi auth deactivate <profile>`
- `helloagi auth doctor`

## Extensions

- `helloagi extensions list`
- `helloagi extensions info <name>`
- `helloagi extensions enable <name>`
- `helloagi extensions disable <name>`
- `helloagi extensions doctor`

## Migration

- `helloagi migrate --source openclaw`
- `helloagi migrate --source hermes`
- `helloagi migrate --source openclaw --apply`
- `helloagi migrate --source openclaw --apply --rename-imports`
- `helloagi migrate --source openclaw --apply --overwrite`

## Workflow runs

- `helloagi runs list`
- `helloagi runs show <run-id>`
- `helloagi runs export <run-id>`
- `helloagi runs resume <run-id>`
- `helloagi runs cancel <run-id>`

## Storage and diagnostics

- `helloagi db-init`
- `helloagi db-demo`
- `helloagi doctor-score`
- `helloagi readiness` — audit a clean checkout for public/open-source release hygiene: required docs, ignored private runtime artifacts, obvious secret/private-value leaks, install entrypoints, tests, and user-facing runtime feature discoverability
- `helloagi readiness --allow-dirty` — run the same audit while local intentional changes are still staged/unstaged
- `helloagi readiness --json` — machine-readable readiness report for CI or release gates
- `helloagi replay-failure` — render the last deny/failure with nearby journal context and the latest context-workspace evidence summary, including observed/generated/verified counts and action readiness
- `helloagi dashboard`
