# Troubleshooting

## Install issues

- Broken conda base on Windows: create a new venv and install there.
- `helloagi` not on PATH: use `python -m agi_runtime.cli ...` in the active environment.

## Service issues

- `helloagi service status`
- `helloagi health`
- Check that `.env` and `helloagi.json` exist in the configured `--workdir`.

## Channel issues

- `helloagi extensions doctor`
- Missing Telegram support: install `helloagi[telegram]`
- Missing Discord support: install `helloagi[discord]`

## Migration issues

- Start with preview: `helloagi migrate --source openclaw`
- Use `--rename-imports` if imported files would collide
- Check imported artifacts under `memory/imports/`

## Workflow run issues

- `helloagi runs list`
- `helloagi runs show <run-id>`
- `helloagi runs resume <run-id>`
- `helloagi runs cancel <run-id>`
