# Channels and Extensions

HelloAGI treats channels as optional extensions.

## Built-in extensions

- `telegram`
- `discord`
- `embeddings`

## Inspect readiness

```bash
helloagi extensions list
helloagi extensions doctor
helloagi extensions info telegram
```

## Persistently enable a channel

```bash
helloagi extensions enable telegram
helloagi serve
```

Enabled channel extensions are picked up automatically by `helloagi serve` and `helloagi service install`.

## Ad hoc enablement

```bash
helloagi serve --extension telegram
helloagi service install --extension telegram
```

## Telegram

- Install: `pip install "helloagi[telegram]"`
- Secret: `TELEGRAM_BOT_TOKEN`
- Start: `helloagi serve --telegram`

## Discord

- Install: `pip install "helloagi[discord]"`
- Secret: `DISCORD_BOT_TOKEN`
- Start: `helloagi serve --discord`
