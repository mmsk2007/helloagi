# Environment Reference

## Core providers

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`

## Channels

- `TELEGRAM_BOT_TOKEN`
- `DISCORD_BOT_TOKEN`

## Service / API

- `HELLOAGI_API_KEY`

## Telegram behavior

- `HELLOAGI_TELEGRAM_SHOW_GOV=1`
- `HELLOAGI_MEMORY_SCOPE=strict`
- `HELLOAGI_REMINDER_TICK_SECONDS`
- `HELLOAGI_REMINDER_STUCK_SECONDS`
- `HELLOAGI_REMINDER_ONESHOT_GRACE_SECONDS`
- `HELLOAGI_REMINDER_TIMEZONE`

## Typical flow

1. Put secrets in `.env`.
2. Run `helloagi health`.
3. Run `helloagi extensions doctor`.
4. Start the runtime with `helloagi run` or `helloagi serve`.
