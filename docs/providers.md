# Providers, credentials, and operator controls

This document is the **provider matrix** for HelloAGI: who powers the main agent loop, how secrets are stored, how to switch models, and how Telegram admin commands are gated.

## Comparison: HelloAGI vs OpenClaw vs Hermes

| Topic | HelloAGI | OpenClaw | Hermes |
|--------|-----------|-----------|--------|
| Primary config | `helloagi.json` + `.env` in the working directory | `~/.openclaw/openclaw.json` + gateway config | `~/.hermes/config.yaml` + `~/.hermes/.env` |
| Backbone LLM | Anthropic, Google Gemini, or **OpenAI** (when `openai` package + credentials present) | Gateway-driven model catalog | Nous stack + multi-provider via config |
| API keys / tokens | Env vars and optional `memory/auth_profiles.json` | Gateway + dashboard + skill entries | Credential pools + `.env` |
| Operator model switch | `helloagi models …` CLI; optional Telegram `/model` / `/provider` (admins only) | Control UI (browser) + gateway | TUI `/model` modal |
| Local dashboard | `helloagi serve` → **`/dashboard`** (browser) + `/journal` API; Rich `helloagi dashboard` | Gateway Control UI at `/` | TUI + gateway server |

## Backbone vs optional credentials

| Provider | Backbone (main `think()` loop) | Notes |
|----------|----------------------------------|--------|
| **Anthropic** | Yes | Default when usable keys exist and `llm_provider` is `auto` or `anthropic`. |
| **Google** | Yes | Requires `google-genai`; `llm_provider` `google` or `auto` when Gemini is the only usable backbone. |
| **OpenAI** | Yes | Requires `pip install openai` and `OPENAI_API_KEY` or `OPENAI_AUTH_TOKEN` (bearer). Use `llm_provider: "openai"` or `HELLOAGI_LLM_PROVIDER=openai`. |
| **Template** | N/A | No keys: templated replies only. |

`OPENAI_AUTH_TOKEN` is for **long-lived bearer-style** tokens (e.g. some ChatGPT/Codex exports). It is **not** a full OAuth device-flow UI in the runtime; use env or your shell profile to supply refreshed tokens if your flow rotates them.

## Environment variables (quick reference)

| Variable | Purpose |
|----------|---------|
| `HELLOAGI_LLM_PROVIDER` | `auto` \| `anthropic` \| `google` \| `openai` — overrides `helloagi.json` `llm_provider`. |
| `OPENAI_API_KEY` | OpenAI API key (standard). |
| `OPENAI_AUTH_TOKEN` | Bearer token for OpenAI-compatible auth. |
| `HELLOAGI_OPENAI_MODEL_SPEED` | Override speed-tier model (default `gpt-4o-mini`). |
| `HELLOAGI_OPENAI_MODEL_BALANCED` | Override balanced tier (default `gpt-4o`). |
| `HELLOAGI_OPENAI_MODEL_QUALITY` | Override quality tier (default `gpt-4o`). |
| `HELLOAGI_TELEGRAM_ADMIN_IDS` | Comma-separated **numeric** Telegram user IDs allowed to run `/provider` and `/model`. Empty = commands disabled. |
| `HELLOAGI_CONFIG_PATH` | Set by `helloagi serve` to the `--config` file so Telegram admin commands update the same `helloagi.json`. You may set it manually if you run a custom launcher. |

## Telegram admin policy

`/provider` and `/model` change runtime behavior and must **not** be available to arbitrary chat members.

1. **Default deny:** If `HELLOAGI_TELEGRAM_ADMIN_IDS` is unset or empty, `/provider` and `/model` reply with a short “not enabled” message.
2. **Allowlist:** Only user IDs listed in `HELLOAGI_TELEGRAM_ADMIN_IDS` may use these commands (compare `message.from_user.id` as integer).
3. **Audit:** Each successful provider or model change is appended to the JSONL journal as `telegram.admin_config` with redacted fields (no secrets).

For **group chats**, the same user ID check applies; optionally restrict to specific chats later via a separate env if needed.

## Auto vs pinned provider

- **`auto`:** Prefers Anthropic when its credential passes the “usable for backbone” heuristics, then Google, then OpenAI (all must pass the same heuristics and package checks).
- **Pinned** (`anthropic`, `google`, `openai`): Uses only that provider if credentials and dependencies are available; otherwise the agent may fall back to template mode with a clear message.

See [environment.md](environment.md) for the full list of env vars.
