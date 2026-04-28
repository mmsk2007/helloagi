# Environment Reference

See also [providers.md](providers.md) for backbone vs tools-only credentials, Telegram admin policy, and model-tier overrides.

## Core providers

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_AUTH_TOKEN`
- `OPENAI_API_KEY`
- `OPENAI_AUTH_TOKEN`
- `GOOGLE_API_KEY`
- `GOOGLE_AUTH_TOKEN`

## Backbone routing

- `HELLOAGI_LLM_PROVIDER` — `auto` \| `anthropic` \| `google` \| `openai`. Overrides `helloagi.json` `llm_provider` for this process.
- `HELLOAGI_OPENAI_MODEL_SPEED`, `HELLOAGI_OPENAI_MODEL_BALANCED`, `HELLOAGI_OPENAI_MODEL_QUALITY` — optional OpenAI model id overrides when the active backbone is OpenAI.

## Channels

- `TELEGRAM_BOT_TOKEN`
- `DISCORD_BOT_TOKEN`

## Service / API

- `HELLOAGI_API_KEY`
  Shared auth token for the local HelloAGI API, dashboard, and service-aware clients.

- `HELLOAGI_CONFIG_PATH`
  Optional; normally set automatically by `helloagi serve` to the `--config` path so Telegram admin commands (`/provider`, `/model`) persist to the same `helloagi.json` the server loaded.

## Telegram behavior

- `HELLOAGI_TELEGRAM_ADMIN_IDS` — comma-separated numeric Telegram user IDs allowed to use `/provider` and `/model`. When empty, those commands reply with “admin-only” for everyone (default deny).
- `HELLOAGI_TELEGRAM_SHOW_GOV=1`
- `HELLOAGI_MEMORY_SCOPE=strict`
- `HELLOAGI_REMINDER_TICK_SECONDS`
- `HELLOAGI_REMINDER_STUCK_SECONDS`
- `HELLOAGI_REMINDER_ONESHOT_GRACE_SECONDS`
- `HELLOAGI_REMINDER_TIMEZONE`

## Typical flow

1. Put secrets in `.env`.
2. Run `helloagi onboard` if you want the guided setup flow.
3. Run `helloagi health`.
4. Run `helloagi extensions doctor`.
5. Start the runtime with `helloagi run`, `helloagi serve`, or `helloagi service start`.
