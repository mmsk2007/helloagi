# Migration Guide

HelloAGI can import selected state from OpenClaw and Hermes.

## Supported sources

- `openclaw`
- `hermes`

## What gets imported

- Secrets from `.env` and supported JSON config surfaces
- Workspace memory files like `AGENTS.md`, `SOUL.md`, `USER.md`, `MEMORY.md`
- Approval/auth artifacts such as `exec-approvals.json` and `auth-profiles.json`
- Skills from common `skills/` directories

## Preview

```bash
helloagi migrate --source openclaw
helloagi migrate --source hermes
```

## Apply

```bash
helloagi migrate --source openclaw --apply
helloagi migrate --source openclaw --apply --rename-imports
helloagi migrate --source openclaw --apply --overwrite
```

## Destination layout

- Secrets go into local `.env`
- Imported workspace and approval artifacts go under `memory/imports/<source>/`
- Imported skills go into `memory/skills/` with a `<source>-` prefix

## Notes

- Preview output redacts secrets.
- Default conflict policy is skip.
- Use `--rename-imports` to keep both old and new artifacts.
