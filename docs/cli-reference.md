# CLI Reference

## Runtime

- `helloagi run --policy <pack>`
- `helloagi oneshot --message "..."`
- `helloagi auto --goal "..." --steps <n>`
- `helloagi tri-loop --goal "..."`
- `helloagi openclaw --prompt "..."`

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
- `helloagi replay-failure`
- `helloagi dashboard`
