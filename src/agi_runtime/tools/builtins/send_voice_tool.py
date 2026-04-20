"""Synthesize and send a spoken voice note through the active channel."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import shutil
import subprocess
import tempfile
import time
import wave
from io import BytesIO
from pathlib import Path

from agi_runtime.config.env import load_local_env
from agi_runtime.config.providers import resolve_provider_credential
from agi_runtime.tools.registry import (
    ToolParam,
    ToolResult,
    get_tool_context_value,
    tool,
)

logger = logging.getLogger("helloagi.tools.send_voice")

_DEFAULT_STYLE = (
    "Speak like a nearby high-end executive assistant: warm, quick, natural, "
    "lightly expressive, and never robotic. Keep acknowledgements short and confident."
)
_STYLE_TAGS = {
    "default": "[warmly]",
    "ack": "[warmly]",
    "calm": "[calmly]",
    "serious": "[serious]",
}


def _voice_tool_available() -> bool:
    load_local_env()
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return resolve_provider_credential("google").configured


def _ffmpeg_binary() -> str | None:
    return shutil.which("ffmpeg")


def _pcm_to_wav_bytes(pcm: bytes, *, sample_rate: int = 24000) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _build_tts_prompt(text: str, *, style_hint: str) -> str:
    load_local_env()
    style = os.environ.get("HELLOAGI_VOICE_GEMINI_TTS_STYLE", "").strip() or _DEFAULT_STYLE
    tag = _STYLE_TAGS.get(style_hint.strip().lower(), _STYLE_TAGS["default"])
    return (
        f"{style}\n"
        "Keep the wording exact, with natural pauses and human cadence.\n"
        f"{tag} {text.strip()}"
    ).strip()


def _synthesize_wav_bytes(text: str, *, style_hint: str) -> bytes:
    load_local_env()
    credential = resolve_provider_credential("google")
    if not credential.configured:
        raise RuntimeError("Google credentials are required for Gemini voice synthesis.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Gemini voice synthesis requires the `google-genai` package.") from exc

    model = os.environ.get("HELLOAGI_VOICE_GEMINI_TTS_MODEL", "").strip() or "gemini-3.1-flash-tts-preview"
    voice_name = os.environ.get("HELLOAGI_VOICE_GEMINI_TTS_VOICE", "").strip() or "Kore"
    prompt = _build_tts_prompt(text, style_hint=style_hint)
    client = genai.Client(api_key=credential.secret)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
        ),
    )
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise RuntimeError("Gemini TTS returned no candidates.")
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    audio_part = next((part for part in parts if getattr(part, "inline_data", None) is not None), None)
    if audio_part is None:
        raise RuntimeError("Gemini TTS returned no audio data.")
    data = audio_part.inline_data.data
    pcm = base64.b64decode(data) if isinstance(data, str) else bytes(data)
    return _pcm_to_wav_bytes(pcm)


def _write_temp_voice_file(audio_bytes: bytes, *, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(prefix="helloagi-voice-", suffix=suffix, delete=False) as handle:
        handle.write(audio_bytes)
        return Path(handle.name)


def _transcode_wav_to_ogg_opus(wav_path: Path) -> Path:
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to create Telegram voice notes.")
    ogg_path = wav_path.with_suffix(".ogg")
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(wav_path),
            "-vn",
            "-c:a",
            "libopus",
            "-b:a",
            "48k",
            str(ogg_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not ogg_path.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg voice transcode failed: {detail or 'unknown error'}")
    return ogg_path


def _prepare_voice_asset(channel, wav_bytes: bytes) -> tuple[Path, bool]:
    wav_path = _write_temp_voice_file(wav_bytes, suffix=".wav")
    if getattr(channel, "name", "") != "telegram":
        return wav_path, False
    try:
        ogg_path = _transcode_wav_to_ogg_opus(wav_path)
    except Exception as exc:
        logger.warning("Telegram voice note packaging fell back to WAV: %s", exc)
        return wav_path, False
    try:
        wav_path.unlink(missing_ok=True)
    except Exception:
        pass
    return ogg_path, True


@tool(
    name="send_voice",
    description=(
        "Generate a spoken voice note using Gemini TTS and deliver it through the active channel. "
        "Use this when the user explicitly asks to hear your voice or wants an audio reply. "
        "Prefer this over ad hoc shell scripts or local TTS commands."
    ),
    toolset="user",
    risk="medium",
    check_fn=_voice_tool_available,
    parameters=[
        ToolParam("text", "string", "Exact text to synthesize into spoken audio."),
        ToolParam("caption", "string", "Optional caption to accompany the voice note.", required=False, default=""),
        ToolParam(
            "style_hint",
            "string",
            "Delivery style hint for the voice note.",
            required=False,
            default="default",
            enum=["default", "ack", "calm", "serious"],
        ),
    ],
)
def send_voice(text: str, caption: str = "", style_hint: str = "default") -> ToolResult:
    spoken_text = (text or "").strip()
    if not spoken_text:
        return ToolResult(ok=False, output="", error="text is required")

    channel = get_tool_context_value("channel")
    channel_id = get_tool_context_value("channel_id")
    if channel is None:
        return ToolResult(ok=False, output="", error="no active channel; cannot deliver voice")
    if not channel_id:
        return ToolResult(ok=False, output="", error="no active channel_id; cannot route the voice note")

    loop = getattr(channel, "_loop", None)
    if loop is None or not loop.is_running():
        return ToolResult(ok=False, output="", error="channel event loop is not running")

    wav_bytes = _synthesize_wav_bytes(spoken_text, style_hint=style_hint)
    voice_path = None
    telegram_native = False
    t0 = time.monotonic()
    try:
        voice_path, telegram_native = _prepare_voice_asset(channel, wav_bytes)

        if "voice" in getattr(channel, "capabilities", frozenset()):
            try:
                result = asyncio.run_coroutine_threadsafe(
                    channel.send_voice(channel_id, str(voice_path), caption=caption),
                    loop,
                ).result(timeout=60.0)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            if result.get("ok"):
                dur_ms = (time.monotonic() - t0) * 1000.0
                logger.info(
                    "voice out tool=send_voice channel=%s path=%s ms=%.1f ok=%s native=%s",
                    type(channel).__name__, voice_path, dur_ms, True, telegram_native,
                )
                return ToolResult(ok=True, output=f"delivered voice note to {channel.name}")

        if "file" not in getattr(channel, "capabilities", frozenset()):
            return ToolResult(ok=False, output="", error="current channel cannot deliver voice attachments")

        result = asyncio.run_coroutine_threadsafe(
            channel.send_file(
                channel_id,
                str(voice_path),
                caption=caption,
                filename=f"helloagi-voice{voice_path.suffix}",
            ),
            loop,
        ).result(timeout=60.0)
        dur_ms = (time.monotonic() - t0) * 1000.0
        logger.info(
            "voice out tool=send_voice channel=%s path=%s ms=%.1f ok=%s native=%s",
            type(channel).__name__, voice_path, dur_ms, result.get("ok"), telegram_native,
        )
        if result.get("ok"):
            return ToolResult(ok=True, output=f"delivered voice note to {channel.name}")
        return ToolResult(ok=False, output="", error=str(result.get("error") or "unknown send error"))
    finally:
        if voice_path is not None:
            try:
                voice_path.unlink(missing_ok=True)
            except Exception:
                pass
