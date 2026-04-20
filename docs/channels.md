# Channels and Extensions

HelloAGI treats channels as optional extensions.

## Built-in extensions

- `telegram`
- `discord`
- `voice`
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

## Voice

- Install: `pip install "helloagi[voice]"`
- Secrets: none
- Start: `helloagi serve --voice`
- Monitor: open `http://127.0.0.1:8787/voice/monitor` while the voice channel is running
- Purpose: local wake-word microphone + speaker loop for desktop use
- Windows backend: built-in `System.Speech` via PowerShell, so no `PyAudio` wheel is required
- macOS / Linux backend: `SpeechRecognition` + `pyttsx3`; your OS may still need a local microphone backend
- Provider model: voice routes through the normal HelloAGI provider stack (`anthropic`, `google`, or template fallback) via `agent.think()`
- Gemini Live input option: set `HELLOAGI_VOICE_INPUT_PROVIDER=gemini_live` to transcribe microphone audio with Gemini 3.1 Flash Live
- Fallback input model: set `HELLOAGI_VOICE_GEMINI_INPUT_MODEL` if you want a specific Gemini model for one-shot audio transcription when Live preview is unavailable
- Human-like output option: set `HELLOAGI_VOICE_OUTPUT_PROVIDER=gemini_tts` to synthesize replies with Gemini TTS on Windows
- Busy feedback option: set `HELLOAGI_VOICE_WORK_SOUND=piano` (or `chime`, `pulse`, `off`) to hear the agent while it is thinking or using tools
- Personalization: set `HELLOAGI_OWNER_NAME` so the assistant can address the user directly in voice acknowledgements
- Delivery shaping: use `HELLOAGI_VOICE_GEMINI_TTS_STYLE` and inline audio tags such as `[warmly]`, `[serious]`, or `[whispers]` to steer Gemini TTS delivery
- Local memory continuity: voice now defaults to the shared local principal `local:default`, so CLI and local voice reuse the same memory profile. Set `HELLOAGI_VOICE_PRINCIPAL_ID` if you need voice isolated.
- Core env vars:
  - `HELLOAGI_LOCAL_PRINCIPAL_ID`
  - `HELLOAGI_VOICE_AUDIO_BACKEND`
  - `HELLOAGI_VOICE_WAKE_WORD`
  - `HELLOAGI_OWNER_NAME`
  - `HELLOAGI_VOICE_NAME`
  - `HELLOAGI_VOICE_RATE`
  - `HELLOAGI_VOICE_INPUT_PROVIDER`
  - `HELLOAGI_VOICE_OUTPUT_PROVIDER`
  - `HELLOAGI_VOICE_RECOGNITION_LOCALE`
  - `HELLOAGI_VOICE_STT_BACKEND`
  - `HELLOAGI_VOICE_STOP_WORDS`
  - `HELLOAGI_VOICE_GEMINI_LIVE_MODEL`
  - `HELLOAGI_VOICE_GEMINI_INPUT_MODEL`
  - `HELLOAGI_VOICE_GEMINI_TTS_MODEL`
  - `HELLOAGI_VOICE_GEMINI_TTS_VOICE`
  - `HELLOAGI_VOICE_GEMINI_TTS_STYLE`
  - `HELLOAGI_VOICE_WORK_SOUND`
  - `HELLOAGI_VOICE_PROGRESS_THROTTLE_SECONDS`
  - `HELLOAGI_VOICE_PRINCIPAL_ID`
