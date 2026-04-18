# Environment Reference

## Core providers

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_AUTH_TOKEN`
- `OPENAI_API_KEY`
- `OPENAI_AUTH_TOKEN`
- `GOOGLE_API_KEY`
- `GOOGLE_AUTH_TOKEN`

## Channels

- `TELEGRAM_BOT_TOKEN`
- `DISCORD_BOT_TOKEN`

## Service / API

- `HELLOAGI_API_KEY`
  Shared auth token for the local HelloAGI API, dashboard, and service-aware clients.

## Telegram behavior

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
