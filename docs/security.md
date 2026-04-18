# Security Model

HelloAGI is local-first by default.

## Core rules

- SRG evaluates every tool call before execution.
- The HTTP API binds to `127.0.0.1` by default.
- API access is protected by `HELLOAGI_API_KEY` when the service layer provisions it.
- Secrets are loaded from process environment first, then local `.env`.
- `helloagi.onboard.json` stores non-secret onboarding state only.

## Channel safety

- Telegram and Discord are optional extensions.
- Missing tokens or missing libraries are surfaced through `helloagi extensions doctor` and `helloagi health`.
- Multi-user memory is scoped by principal identifiers per channel.

## Runtime safety

- Use `helloagi doctor` to inspect local runtime readiness.
- Use `helloagi health` to inspect config, storage, providers, service state, and extension readiness.
- Use reviewer-safe policy packs for read-only workflows: `helloagi run --policy reviewer`.

## Native service defaults

- `helloagi service install` keeps the service local and authenticated.
- Linux uses `systemd --user`.
- macOS uses `launchd`.
- Windows uses a user-level Scheduled Task strategy.

Before exposing HelloAGI remotely, add a reverse proxy, TLS, and explicit network policy.
