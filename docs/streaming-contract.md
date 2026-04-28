# Streaming and step hooks (channel contract)

HelloAGI mirrors the **Hermes-style** split between token deltas and tool progress:

## `agent.on_stream`

- **Type:** `Optional[Callable[[Optional[str]], None]]` (synchronous callback; may be invoked from a worker thread).
- **Text:** each non-empty `str` is an incremental **text delta** (append to the in-flight UI buffer).
- **Segment break:** `None` signals a boundary before **tool use** (Anthropic `tool_use` block start, or the first **Gemini `function_call`** in a streamed turn). Channels such as [`TelegramStreamConsumer`](../src/agi_runtime/channels/telegram_stream.py) finalize the current preview message and start a fresh segment so tool lines and answer text do not fight the same edit cursor.
- **Errors:** callbacks must not raise; failures are journaled as `on_stream_error` and ignored so the LLM drain cannot abort.

**Anthropic:** `_drain_anthropic_stream` implements the above from `messages.stream()` events.

**Google Gemini:** when `on_stream` is set and `google.genai.Client().aio` is available, each think-turn uses `generate_content_stream`, merged by [`GeminiStreamAccumulator`](../src/agi_runtime/llm/gemini_adapter.py). If streaming fails (SDK/network), the runtime **falls back once** to non-streaming `generate_content` for that turn (`journal`: `gemini_stream_fallback`).

**Telegram:** with live preview + `TelegramStreamConsumer`, **tool progress** is injected via `on_tool_start` / `on_tool_end` into the **same** `consumer.on_delta` queue as tokens, so you do not get a second parallel preview path (OpenClaw-style “no double streaming” for the same bubble).

## `agent.step_callback`

- **Type:** `Optional[Callable[[int, list[dict]], None]]`.
- **When:** after each LLM response is parsed into `tool_calls`, **before** tools execute.
- **Arguments:** `(turn_index, planned_tools)` where `planned_tools` is `[{"name": str, "input": dict}, ...]` (empty list when the model returns final text only).

Gateways can use this for telemetry parity with Hermes `step_callback` without scraping the JSONL journal.

## Related

- [`telegram_stream.py`](../src/agi_runtime/channels/telegram_stream.py) — queue + edit cadence.
- [`test_agent_streaming.py`](../tests/core/test_agent_streaming.py) — Anthropic drain contract.
- [`test_gemini_stream_accumulator.py`](../tests/llm/test_gemini_stream_accumulator.py) — Gemini merge contract.
