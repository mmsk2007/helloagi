# Privacy and Data Handling

HelloAGI stores runtime state locally unless you explicitly connect external providers or channels.

## Local files

- `.env`: local secrets and tokens
- `helloagi.onboard.json`: onboarding metadata only
- `helloagi.json`: runtime config
- `memory/`: journals, imported artifacts, skills, and runtime state

## What is not stored in onboarding JSON

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `DISCORD_BOT_TOKEN`
- `HELLOAGI_API_KEY`

## External services

If you enable a provider or channel, data will flow to that provider or platform according to their policies. Typical examples:

- Anthropic / OpenAI / Google for model inference
- Telegram or Discord for message delivery

## Operational guidance

- Keep `.env` and `memory/` out of source control.
- Rotate tokens after sharing a machine or repository snapshot.
- Prefer a dedicated machine account for always-on service installs.
