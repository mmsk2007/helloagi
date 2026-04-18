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
- `helloagi service install [--telegram] [--discord] [--extension <name>] [--workdir <path>]`
- `helloagi service start`
- `helloagi service stop`
- `helloagi service status`
- `helloagi service uninstall`

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
- `helloagi runs resume <run-id>`
- `helloagi runs cancel <run-id>`

## Storage and diagnostics

- `helloagi db-init`
- `helloagi db-demo`
- `helloagi doctor-score`
- `helloagi replay-failure`
- `helloagi dashboard`
