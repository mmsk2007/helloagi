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
| **OpenAI** | Yes | Requires `pip install openai` and **either** `OPENAI_API_KEY` / `OPENAI_AUTH_TOKEN` **or** tokens from **`helloagi auth login-openai`** (ChatGPT/Codex OAuth file). Use `llm_provider: "openai"` or `HELLOAGI_LLM_PROVIDER=openai`. |
| **Template** | N/A | No keys: templated replies only. |

### OpenAI auth options (open source parity)

1. **API key** — set `OPENAI_API_KEY` in `.env` (platform billing).
2. **Static bearer** — set `OPENAI_AUTH_TOKEN` for a token you manage yourself (export, script, etc.).
3. **ChatGPT / Codex OAuth (browser + PKCE)** — run:

   ```bash
   helloagi auth login-openai
   ```

   This opens `https://auth.openai.com/oauth/authorize` (or prints the URL with `--no-browser`), captures the redirect on `http://127.0.0.1:<port>/auth/callback`, and if localhost is unreachable (SSH, blocked port) lets you **paste the full redirect URL** from the browser. Tokens are stored in **`memory/openai_codex_oauth.json`** (password-equivalent; never commit). The runtime **refreshes** the access token using the saved refresh token when it is near expiry.

   **Unofficial / community OAuth client:** HelloAGI defaults to the same public **client id** documented by the community [`openai-oauth`](https://github.com/EvanZhouDev/openai-oauth) project (`app_EMoamEEZ73f0CkXaXp7hrann`). Override with `HELLOAGI_OPENAI_OAUTH_CLIENT_ID` if you register your own OAuth client with OpenAI. You must comply with OpenAI’s terms and regional restrictions; failures at `/oauth/token` (e.g. unsupported region) are between you and OpenAI’s policy.

4. **Ignore OAuth file** — set `HELLOAGI_OPENAI_OAUTH_DISABLE=1` to force API key / `.env` bearer only.

5. **Custom API base** — set `HELLOAGI_OPENAI_BASE_URL` if your token targets a non-default host (for example a local [openai-oauth](https://github.com/EvanZhouDev/openai-oauth) proxy at `http://127.0.0.1:10531/v1` when using ChatGPT-scoped tokens).

**Precedence:** process environment `OPENAI_*` wins; then OAuth file (if present and not disabled); then auth profiles; then `.env` file.

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
| `HELLOAGI_OPENAI_OAUTH_CLIENT_ID` | Override OAuth client id (default matches community Codex-style login). |
| `HELLOAGI_OPENAI_OAUTH_SCOPE` | Override authorize scope string. |
| `HELLOAGI_OPENAI_OAUTH_PORT` | First localhost port to try for callback (default `1455`). |
| `HELLOAGI_OPENAI_OAUTH_BIND` | Bind host for callback server (default `127.0.0.1`). |
| `HELLOAGI_OPENAI_OAUTH_STORE` | Path to JSON token store (default `memory/openai_codex_oauth.json`). |
| `HELLOAGI_OPENAI_OAUTH_DISABLE` | `1` to skip OAuth file and use env/profile keys only. |
| `HELLOAGI_OPENAI_BASE_URL` | Optional OpenAI-compatible API root (e.g. local Codex proxy + `/v1`). Passed to the OpenAI SDK as `base_url`. |

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
