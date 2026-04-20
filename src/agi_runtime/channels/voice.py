"""Local voice channel for HelloAGI.

Wake-word voice loop for local desktop use:
  - listens for a configurable wake word
  - routes commands through HelloAGIAgent.think()
  - speaks responses with local TTS
  - asks for SRG approvals over voice when needed

The reasoning provider remains the normal HelloAGI provider stack
(Anthropic / Google / template fallback). Voice I/O is kept separate so
open-source users can swap model providers without changing the channel.
"""

from __future__ import annotations

import asyncio
import base64
import collections
import io
from importlib.util import find_spec
import json
import logging
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import wave
import math
from typing import Any, Callable

from agi_runtime.channels.base import BaseChannel
from agi_runtime.channels.voice_presence import voice_presence_store
from agi_runtime.config.providers import resolve_provider_credential
from agi_runtime.config.env import load_local_env
from agi_runtime.core.agent import HelloAGIAgent

logger = logging.getLogger("helloagi.voice")

_SPINNER_FRAMES = ("[=   ]", "[==  ]", "[=== ]", "[ ===]", "[  ==]", "[   =]")
_DEFAULT_STOP_WORDS = ("stop", "exit", "quit", "goodbye", "sleep")
_AUDIO_BACKEND_AUTO = "auto"
_AUDIO_BACKEND_WINDOWS = "windows_native"
_AUDIO_BACKEND_SPEECH_RECOGNITION = "speech_recognition"
_VOICE_INPUT_LOCAL = "local"
_VOICE_INPUT_GEMINI_LIVE = "gemini_live"
_VOICE_OUTPUT_LOCAL = "local"
_VOICE_OUTPUT_GEMINI_TTS = "gemini_tts"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_text(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def _env_words(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    words = [part.strip().lower() for part in raw.split(",")]
    return tuple(word for word in words if word) or default


def _normalize_voice_output_provider(raw: str | None) -> str:
    provider = (raw or "").strip().lower() or "auto"
    if provider == "auto":
        return _VOICE_OUTPUT_LOCAL
    if provider in {"gemini", "gemini_tts", "google", "google_tts"}:
        return _VOICE_OUTPUT_GEMINI_TTS if resolve_provider_credential("google").configured else _VOICE_OUTPUT_LOCAL
    if provider in {"local", "system", "native"}:
        return _VOICE_OUTPUT_LOCAL
    return _VOICE_OUTPUT_LOCAL


def _normalize_voice_input_provider(raw: str | None) -> str:
    provider = (raw or "").strip().lower() or "auto"
    if provider == "auto":
        return _VOICE_INPUT_LOCAL
    if provider in {"gemini", "gemini_live", "google_live", "live"}:
        return _VOICE_INPUT_GEMINI_LIVE
    if provider in {"local", "system", "native"}:
        return _VOICE_INPUT_LOCAL
    return _VOICE_INPUT_LOCAL


def _resolve_voice_principal_id() -> str:
    explicit = _env_text("HELLOAGI_VOICE_PRINCIPAL_ID", "")
    if explicit:
        return explicit
    shared_local = _env_text("HELLOAGI_LOCAL_PRINCIPAL_ID", "")
    if shared_local:
        return shared_local
    return "local:default"


def _is_windows(platform_name: str | None = None) -> bool:
    if platform_name is None:
        platform_name = platform.system()
    return platform_name.strip().lower().startswith("win")


def _powershell_binary() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def _normalize_audio_backend(raw: str | None, *, platform_name: str | None = None) -> str:
    backend = (raw or "").strip().lower() or _AUDIO_BACKEND_AUTO
    if backend == _AUDIO_BACKEND_AUTO:
        return _AUDIO_BACKEND_WINDOWS if _is_windows(platform_name) else _AUDIO_BACKEND_SPEECH_RECOGNITION
    if backend in {"windows", "windows_native", "system_speech"}:
        return _AUDIO_BACKEND_WINDOWS
    if backend in {"speech_recognition", "speechrecognition", "sr"}:
        return _AUDIO_BACKEND_SPEECH_RECOGNITION
    return _AUDIO_BACKEND_WINDOWS if _is_windows(platform_name) else _AUDIO_BACKEND_SPEECH_RECOGNITION


def probe_voice_runtime() -> dict[str, Any]:
    """Report voice backend readiness without importing heavy runtime deps."""
    load_local_env()
    backend = _normalize_audio_backend(os.environ.get("HELLOAGI_VOICE_AUDIO_BACKEND"))
    input_provider = _normalize_voice_input_provider(os.environ.get("HELLOAGI_VOICE_INPUT_PROVIDER"))
    missing_modules: list[str] = []
    notes: list[str] = []
    output_provider = _normalize_voice_output_provider(os.environ.get("HELLOAGI_VOICE_OUTPUT_PROVIDER"))

    if backend == _AUDIO_BACKEND_WINDOWS:
        if not _is_windows():
            missing_modules.append("windows_native_backend")
        elif not _powershell_binary():
            missing_modules.append("powershell")
        else:
            notes.append("Windows voice uses the built-in System.Speech APIs. No PyAudio wheel is required.")
    else:
        for module_name in ("speech_recognition", "pyttsx3"):
            if find_spec(module_name) is None:
                missing_modules.append(module_name)
        if not missing_modules:
            notes.append(
                "Non-Windows voice uses SpeechRecognition + pyttsx3 and may still need a local microphone backend."
            )
    if input_provider == _VOICE_INPUT_GEMINI_LIVE:
        for module_name in ("google.genai", "sounddevice"):
            if find_spec(module_name) is None and module_name not in missing_modules:
                missing_modules.append(module_name)
        if resolve_provider_credential("google").configured:
            notes.append("Voice input uses Gemini Live transcription when Google credentials are configured.")
        else:
            notes.append("Gemini Live input requested but Google credentials are not configured; local input will fail.")
    if output_provider == _VOICE_OUTPUT_GEMINI_TTS:
        if find_spec("google.genai") is None:
            missing_modules.append("google.genai")
        elif not resolve_provider_credential("google").configured:
            notes.append("Gemini TTS requested but Google credentials are not configured; falling back to local voice.")
        else:
            notes.append("Voice output uses Gemini 3.1 Flash TTS when Google credentials are configured.")

    return {
        "backend": backend,
        "input_provider": input_provider,
        "output_provider": output_provider,
        "available": not missing_modules,
        "missing_modules": missing_modules,
        "notes": notes,
    }


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _windows_tts_rate(raw_rate: int) -> int:
    # System.Speech uses -10..10 while pyttsx3-style configs tend to be 120..220.
    scaled = round((raw_rate - 185) / 8)
    return max(-10, min(10, scaled))


def _powershell_error_message(output: str) -> str:
    if "#< CLIXML" in output:
        return "Windows speech services are unavailable in this session."
    cleaned = (
        output.replace("_x000D__x000A_", "\n")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return "PowerShell voice backend failed."
    skip_prefixes = ("At line:", "+ ", "CategoryInfo", "FullyQualifiedErrorId")
    for line in reversed(lines):
        if line.startswith(skip_prefixes):
            continue
        if line.startswith("<Objs "):
            continue
        if line.startswith("</"):
            continue
        return line
    return lines[-1]


class VoiceChannel(BaseChannel):
    """Local microphone + speaker channel."""

    def __init__(self, agent: HelloAGIAgent):
        super().__init__("voice")
        load_local_env()
        self.agent = agent
        self.principal_id = _resolve_voice_principal_id()
        self.wake_word = (
            os.environ.get("HELLOAGI_VOICE_WAKE_WORD", "").strip().lower()
            or getattr(agent.settings, "identity_name", "").strip().lower()
            or "lana"
        )
        self.voice_name_hint = os.environ.get("HELLOAGI_VOICE_NAME", "").strip().lower()
        self.voice_rate = _env_int("HELLOAGI_VOICE_RATE", 185)
        self.audio_backend = _normalize_audio_backend(os.environ.get("HELLOAGI_VOICE_AUDIO_BACKEND"))
        self.voice_input_provider = _normalize_voice_input_provider(os.environ.get("HELLOAGI_VOICE_INPUT_PROVIDER"))
        self.voice_output_provider = _normalize_voice_output_provider(os.environ.get("HELLOAGI_VOICE_OUTPUT_PROVIDER"))
        self.recognition_locale = _env_text("HELLOAGI_VOICE_RECOGNITION_LOCALE", "en-US")
        configured_stt_backend = os.environ.get("HELLOAGI_VOICE_STT_BACKEND", "google").strip().lower() or "google"
        self.stt_backend = configured_stt_backend
        self.gemini_live_model = _env_text("HELLOAGI_VOICE_GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
        self.gemini_input_model = _env_text(
            "HELLOAGI_VOICE_GEMINI_INPUT_MODEL",
            _env_text("HELLOAGI_GOOGLE_MODEL", "gemini-flash-latest"),
        )
        self.gemini_tts_model = _env_text("HELLOAGI_VOICE_GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
        self.gemini_tts_voice = _env_text("HELLOAGI_VOICE_GEMINI_TTS_VOICE", "Kore")
        self.gemini_tts_style = _env_text("HELLOAGI_VOICE_GEMINI_TTS_STYLE", "")
        self.work_sound = _env_text("HELLOAGI_VOICE_WORK_SOUND", "piano").lower()
        self.command_silence_seconds = _env_float("HELLOAGI_VOICE_COMMAND_SILENCE_SECONDS", 1.2)
        self.command_rms_threshold = _env_int("HELLOAGI_VOICE_COMMAND_RMS_THRESHOLD", 220)
        self.command_sample_rate = _env_int("HELLOAGI_VOICE_COMMAND_SAMPLE_RATE", 16000)
        self.stop_words = _env_words("HELLOAGI_VOICE_STOP_WORDS", _DEFAULT_STOP_WORDS)
        self.ambient_seconds = _env_float("HELLOAGI_VOICE_AMBIENT_SECONDS", 0.6)
        self.wake_timeout = _env_float("HELLOAGI_VOICE_WAKE_TIMEOUT", 4.0)
        self.wake_phrase_limit = _env_float("HELLOAGI_VOICE_WAKE_PHRASE_LIMIT", 3.0)
        self.command_timeout = _env_float("HELLOAGI_VOICE_COMMAND_TIMEOUT", 8.0)
        self.command_phrase_limit = _env_float("HELLOAGI_VOICE_COMMAND_PHRASE_LIMIT", 14.0)
        self.approval_timeout = _env_float("HELLOAGI_VOICE_APPROVAL_TIMEOUT", 6.0)
        self.max_reply_chars = _env_int("HELLOAGI_VOICE_MAX_REPLY_CHARS", 700)
        self.progress_throttle_seconds = _env_float("HELLOAGI_VOICE_PROGRESS_THROTTLE_SECONDS", 6.0)
        self.owner_name = self._resolve_owner_name()
        self._engine = None
        self._sr = None
        self._gemini_tts_client = None
        self._gemini_live_client = None
        self._sounddevice = None
        self._powershell = _powershell_binary() if self.audio_backend == _AUDIO_BACKEND_WINDOWS else None
        self._running = False
        self._ambient_ready = False
        self._console_lock = threading.Lock()
        self._speech_lock = threading.Lock()
        self._last_status_length = 0
        self._last_progress_spoken_at = 0.0
        self._presence = voice_presence_store()
        self._work_sound_stop: threading.Event | None = None
        self._work_sound_thread: threading.Thread | None = None
        self._publish_presence("inactive", "waiting to start", active=False)

    async def start(self):
        """Start the local wake-word loop."""
        self._ensure_audio_stack()
        self._running = True
        self._publish_presence("starting", "initializing voice channel", active=True)
        self._print_intro()
        await asyncio.to_thread(
            self.speak,
            f"Voice channel online. Say {self.wake_word} to wake me up.",
            False,
        )

        while self._running:
            try:
                triggered = await asyncio.to_thread(self._listen_for_wake_word)
            except KeyboardInterrupt:
                break
            except Exception as exc:
                logger.exception("Voice wake loop failed: %s", exc)
                self._publish_presence("error", str(exc), active=True, error=str(exc))
                self._println(f"[voice] error | {exc}")
                await asyncio.sleep(1.0)
                continue

            if not self._running:
                break
            if not triggered:
                self._publish_presence("idle", f"say '{self.wake_word}'", active=True)
                continue

            await asyncio.to_thread(self.speak, "I'm listening.", False)
            command = await asyncio.to_thread(self._listen_for_command)
            if not command:
                self._publish_presence("idle", f"say '{self.wake_word}'", active=True)
                self._render_status("idle", f"say '{self.wake_word}'")
                continue

            if self._should_stop(command):
                await asyncio.to_thread(self.speak, "Voice channel sleeping.", False)
                break

            await asyncio.to_thread(self._handle_command, command)

        self._running = False
        self._publish_presence("stopped", "voice channel offline", active=False)
        self._render_status("stopped", "")
        self._clear_status_line()

    async def stop(self):
        """Stop the voice loop."""
        self._running = False
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass

    async def send(self, channel_id: str, text: str, **kwargs):
        """Speak outbound text when invoked as a channel target."""
        del channel_id, kwargs
        await asyncio.to_thread(self.speak, text)

    def speak(self, text: str, announce: bool = True):
        """Speak a response with a small terminal animation."""
        spoken = self._speak_internal(text, announce=announce, style_hint="default", idle_after=True)
        if not spoken:
            return
        self._publish_presence("idle", f"say '{self.wake_word}'", active=True)
        self._render_status("idle", f"say '{self.wake_word}'")

    def _handle_command(self, command: str):
        self._println(f"You: {command}")
        self._publish_presence("thinking", command[:120], active=True, last_heard=command, error="")
        self._last_progress_spoken_at = 0.0
        original_input = self.agent.on_user_input
        original_tool_start = self.agent.on_tool_start
        original_tool_end = self.agent.on_tool_end
        self.agent.on_user_input = self._voice_approval_prompt
        self.agent.on_tool_start = self._voice_tool_start
        self.agent.on_tool_end = self._voice_tool_end
        self._speak_progress(self._compose_acknowledgement(command), style_hint="ack", force=True)
        self._start_work_sound()
        try:
            self.agent.set_principal(self.principal_id)
            response = self._with_spinner("thinking", "working...", lambda: self.agent.think(command))
        finally:
            self.agent.on_user_input = original_input
            self.agent.on_tool_start = original_tool_start
            self.agent.on_tool_end = original_tool_end
            self._stop_work_sound()
        self.speak(response.text)

    def _voice_approval_prompt(self, prompt: str) -> str:
        self._println(prompt)
        self._publish_presence("approval", prompt[:120], active=True, error="")
        resume_work_sound = self._stop_work_sound()
        self._speak_internal(
            "Approval needed. Say approve to continue or deny to cancel.",
            announce=False,
            style_hint="approval",
            idle_after=False,
            state="approval",
            detail="waiting for approval",
        )
        answer = self._listen_once(
            label="approve or deny",
            timeout=self.approval_timeout,
            phrase_time_limit=4.0,
        )
        if answer:
            self._println(f"You: {answer}")
        normalized = (answer or "").strip().lower()
        if any(token in normalized for token in ("approve", "approved", "yes", "continue", "allow")):
            if resume_work_sound:
                self._start_work_sound()
            return "y"
        return "n"

    def _voice_tool_start(self, tool_name: str, tool_input: Any, decision: str):
        del tool_input
        detail = f"{tool_name} ({decision})"
        self._publish_presence("thinking", detail[:120], active=True, error="")
        self._maybe_voice_tool_update(tool_name, decision)

    def _voice_tool_end(self, tool_name: str, ok: bool, detail: str):
        outcome = "done" if ok else "failed"
        rendered = f"{tool_name} {outcome}"
        if detail:
            rendered = f"{rendered}: {detail}"
        self._publish_presence("thinking", rendered[:120], active=True, error="")
        if not ok:
            self._speak_progress("That step failed, but I'm still on it.", style_hint="error", force=True)

    def _listen_for_wake_word(self) -> bool:
        transcript = self._listen_once(
            label=f"say '{self.wake_word}'",
            timeout=self.wake_timeout,
            phrase_time_limit=self.wake_phrase_limit,
        )
        if not transcript:
            return False
        normalized = transcript.lower()
        if self.wake_word in normalized:
            self._publish_presence("triggered", transcript[:120], active=True, last_heard=transcript, error="")
            self._println(f"[voice] wake word heard | {transcript}")
            return True
        return False

    def _listen_for_command(self) -> str | None:
        transcript = self._listen_once(
            label="ask your command",
            timeout=self.command_timeout,
            phrase_time_limit=self.command_phrase_limit,
        )
        return transcript.strip() if transcript else None

    def _listen_once(self, *, label: str, timeout: float, phrase_time_limit: float) -> str | None:
        self._ensure_audio_stack()

        if self.voice_input_provider == _VOICE_INPUT_GEMINI_LIVE:
            try:
                self._publish_presence("listening", label, active=True, error="")
                pcm = self._with_spinner(
                    "listening",
                    label,
                    lambda: self._capture_pcm_command(timeout=timeout, phrase_time_limit=phrase_time_limit),
                )
            except RuntimeError as exc:
                raise RuntimeError(
                    "Voice extension could not access live microphone capture. "
                    "Check microphone permissions and that a default input device is present."
                ) from exc
            if not pcm:
                self._publish_presence("idle", f"say '{self.wake_word}'", active=True)
                return None
            try:
                self._publish_presence("transcribing", "gemini_live", active=True, error="")
                transcript = self._with_spinner(
                    "transcribing",
                    "gemini live",
                    lambda: self._transcribe_pcm_with_gemini_live(
                        pcm,
                        sample_rate=self.command_sample_rate,
                        timeout=max(timeout + phrase_time_limit + 10.0, 20.0),
                    ),
                )
            except Exception as exc:
                logger.warning("Gemini Live transcription failed: %s", exc)
                self._publish_presence("error", str(exc), active=True, error=str(exc))
                self._println(f"[voice] transcription error | {exc}")
                return None
            return transcript.strip() if transcript else None

        if self.audio_backend == _AUDIO_BACKEND_WINDOWS:
            try:
                self._publish_presence("listening", label, active=True, error="")
                transcript = self._with_spinner(
                    "listening",
                    label,
                    lambda: self._listen_windows_native(timeout=timeout, phrase_time_limit=phrase_time_limit),
                )
            except RuntimeError as exc:
                raise RuntimeError(
                    "Voice extension could not access Windows speech input. "
                    "Check microphone permissions, default input device, and installed speech features."
                ) from exc
            return transcript.strip() if transcript else None

        recognizer = self._sr.Recognizer()
        try:
            with self._sr.Microphone() as source:
                if not self._ambient_ready:
                    self._publish_presence("calibrating", "ambient noise", active=True, error="")
                    self._with_spinner(
                        "calibrating",
                        "ambient noise",
                        lambda: recognizer.adjust_for_ambient_noise(source, duration=self.ambient_seconds),
                    )
                    self._ambient_ready = True
                self._publish_presence("listening", label, active=True, error="")
                audio = self._with_spinner(
                    "listening",
                    label,
                    lambda: recognizer.listen(
                        source,
                        timeout=timeout,
                        phrase_time_limit=phrase_time_limit,
                    ),
                )
        except self._sr.WaitTimeoutError:
            self._publish_presence("idle", f"say '{self.wake_word}'", active=True)
            return None
        except OSError as exc:
            raise RuntimeError(
                "Voice extension could not access the microphone. "
                "Check microphone permissions and that a recording device is present."
            ) from exc

        try:
            self._publish_presence("transcribing", self.stt_backend, active=True, error="")
            transcript = self._with_spinner(
                "transcribing",
                self.stt_backend,
                lambda: self._transcribe_audio(recognizer, audio),
            )
        except self._sr.UnknownValueError:
            self._publish_presence("idle", f"say '{self.wake_word}'", active=True)
            return None
        except self._sr.RequestError as exc:
            logger.warning("Voice transcription failed: %s", exc)
            self._publish_presence("error", str(exc), active=True, error=str(exc))
            self._println(f"[voice] transcription error | {exc}")
            return None
        except Exception as exc:
            logger.warning("Voice backend failure (%s): %s", self.stt_backend, exc)
            self._publish_presence("error", str(exc), active=True, error=str(exc))
            self._println(f"[voice] backend error | {exc}")
            return None

        return transcript.strip() if transcript else None

    def _listen_windows_native(self, *, timeout: float, phrase_time_limit: float) -> str | None:
        total_timeout = max(timeout + phrase_time_limit + 1.0, 1.5)
        preferred_locale = self.recognition_locale
        script = textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            $ProgressPreference = 'SilentlyContinue'
            Add-Type -AssemblyName System.Speech
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            $preferredLocale = {_powershell_quote(preferred_locale)}
            $recognizerInfo = $null
            $installed = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
            if (-not $installed -or $installed.Count -eq 0) {{
                throw 'No Windows speech recognizer is installed.'
            }}
            if ($preferredLocale) {{
                foreach ($info in $installed) {{
                    if ($info.Culture.Name -eq $preferredLocale) {{
                        $recognizerInfo = $info
                        break
                    }}
                }}
            }}
            if (-not $recognizerInfo) {{
                $uiLocale = [System.Globalization.CultureInfo]::CurrentUICulture.Name
                foreach ($info in $installed) {{
                    if ($info.Culture.Name -eq $uiLocale) {{
                        $recognizerInfo = $info
                        break
                    }}
                }}
            }}
            if (-not $recognizerInfo) {{
                $recognizerInfo = $installed[0]
            }}
            $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($recognizerInfo.Culture)
            $recognizer.SetInputToDefaultAudioDevice()
            $recognizer.InitialSilenceTimeout = [TimeSpan]::FromSeconds({max(timeout, 0.5):.2f})
            $recognizer.EndSilenceTimeout = [TimeSpan]::FromSeconds(0.6)
            $recognizer.EndSilenceTimeoutAmbiguous = [TimeSpan]::FromSeconds(0.8)
            $grammar = New-Object System.Speech.Recognition.DictationGrammar
            $recognizer.LoadGrammar($grammar)
            $result = $recognizer.Recognize([TimeSpan]::FromSeconds({total_timeout:.2f}))
            if ($result -and $result.Text) {{
                [Console]::WriteLine($result.Text)
            }}
            """
        ).strip()
        return self._run_powershell(script, timeout=max(total_timeout + 2.0, 4.0)).strip() or None

    def _transcribe_audio(self, recognizer, audio) -> str:
        backend = self.stt_backend
        if backend == "sphinx":
            return recognizer.recognize_sphinx(audio)
        if backend == "google_cloud":
            return recognizer.recognize_google_cloud(audio)
        if backend == "google":
            return recognizer.recognize_google(audio)
        raise RuntimeError(
            f"Unsupported STT backend '{backend}'. "
            "Use one of: google, google_cloud, sphinx."
        )

    def _ensure_audio_stack(self):
        if self.voice_output_provider == _VOICE_OUTPUT_GEMINI_TTS:
            self._ensure_gemini_tts()
        if self.voice_input_provider == _VOICE_INPUT_GEMINI_LIVE:
            self._ensure_sounddevice()
            self._ensure_gemini_live()

        local_input = self.voice_input_provider == _VOICE_INPUT_LOCAL
        local_output = self.voice_output_provider == _VOICE_OUTPUT_LOCAL
        if self.audio_backend == _AUDIO_BACKEND_WINDOWS:
            if not _is_windows():
                raise RuntimeError("The windows_native voice backend only works on Windows.")
            if (local_input or local_output) and not self._powershell:
                raise RuntimeError("PowerShell was not found. Voice needs PowerShell for the Windows-native backend.")
            return

        if local_input and self._sr is None:
            try:
                import speech_recognition as sr
            except ImportError as exc:
                raise ImportError(
                    "Voice extension requires SpeechRecognition for local microphone capture. "
                    "Install the voice extra with `pip install \"helloagi[voice]\"`."
                ) from exc
            self._sr = sr

        if local_output and self._engine is None:
            try:
                import pyttsx3
            except ImportError as exc:
                raise ImportError(
                    "Voice extension requires pyttsx3 for local speech output. "
                    "Install the voice extra with `pip install \"helloagi[voice]\"`."
                ) from exc

            engine = pyttsx3.init()
            engine.setProperty("rate", self.voice_rate)

            voices = engine.getProperty("voices") or []
            if self.voice_name_hint:
                for voice in voices:
                    name = getattr(voice, "name", "")
                    if self.voice_name_hint in name.lower():
                        engine.setProperty("voice", voice.id)
                        break
            else:
                for voice in voices:
                    name = getattr(voice, "name", "").lower()
                    if "zira" in name or "hazel" in name:
                        engine.setProperty("voice", voice.id)
                        break

            self._engine = engine

    def _ensure_sounddevice(self):
        if self._sounddevice is not None:
            return
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise ImportError(
                "Gemini Live voice input requires sounddevice. "
                "Install the voice extra with `pip install \"helloagi[voice]\"`."
            ) from exc
        self._sounddevice = sd

    def _ensure_gemini_tts(self):
        if self._gemini_tts_client is not None:
            return
        if find_spec("google.genai") is None:
            raise ImportError("Gemini TTS output requires `google-genai`.")
        credential = resolve_provider_credential("google")
        if not credential.configured:
            raise RuntimeError("Gemini TTS output requires GOOGLE_API_KEY or GOOGLE_AUTH_TOKEN.")
        from google import genai

        self._gemini_tts_client = genai.Client(api_key=credential.secret)

    def _ensure_gemini_live(self):
        if self._gemini_live_client is not None:
            return
        if find_spec("google.genai") is None:
            raise ImportError("Gemini Live input requires `google-genai`.")
        credential = resolve_provider_credential("google")
        if not credential.configured:
            raise RuntimeError("Gemini Live input requires GOOGLE_API_KEY or GOOGLE_AUTH_TOKEN.")
        from google import genai

        self._gemini_live_client = genai.Client(api_key=credential.secret)

    def _run_powershell(self, script: str, *, timeout: float) -> str:
        if not self._powershell:
            raise RuntimeError("PowerShell is not available for the Windows-native voice backend.")
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(
                [self._powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=creationflags,
            )
        except subprocess.TimeoutExpired:
            return ""
        if proc.returncode != 0:
            raise RuntimeError(_powershell_error_message(proc.stderr or proc.stdout))
        return proc.stdout.strip()

    def _speak_blocking(self, text: str, *, style_hint: str = "default"):
        if self.voice_output_provider == _VOICE_OUTPUT_GEMINI_TTS:
            self._speak_gemini_tts(text, style_hint=style_hint)
            return
        if self.audio_backend == _AUDIO_BACKEND_WINDOWS:
            self._speak_windows_native(text)
            return
        self._engine.say(text)
        self._engine.runAndWait()

    def _speak_gemini_tts(self, text: str, *, style_hint: str = "default"):
        self._ensure_gemini_tts()
        from google.genai import types

        prompt = self._build_tts_prompt(text, style_hint=style_hint)
        response = self._gemini_tts_client.models.generate_content(
            model=self.gemini_tts_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self.gemini_tts_voice,
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
        if not parts or getattr(parts[0], "inline_data", None) is None:
            raise RuntimeError("Gemini TTS returned no audio data.")
        data = parts[0].inline_data.data
        if isinstance(data, str):
            pcm = base64.b64decode(data)
        else:
            pcm = bytes(data)
        wav_bytes = self._pcm_to_wav_bytes(pcm)
        self._play_wav_bytes(wav_bytes)

    @staticmethod
    def _pcm_to_wav_bytes(pcm: bytes, *, sample_rate: int = 24000) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        return buf.getvalue()

    def _play_wav_bytes(self, wav_bytes: bytes):
        if _is_windows():
            import winsound

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
                    handle.write(wav_bytes)
                    tmp_path = handle.name
                winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
            return
        raise RuntimeError("Gemini TTS playback is only implemented for Windows in this channel.")

    def _speak_windows_native(self, text: str):
        rate = _windows_tts_rate(self.voice_rate)
        sapi_script = textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            $ProgressPreference = 'SilentlyContinue'
            $voice = New-Object -ComObject SAPI.SpVoice
            try {{
                $voice.Rate = {rate}
            }} catch {{
            }}
            $hint = {_powershell_quote(self.voice_name_hint)}
            if ($hint) {{
                try {{
                    $selected = $null
                    $voices = $voice.GetVoices()
                    for ($index = 0; $index -lt $voices.Count; $index++) {{
                        $token = $voices.Item($index)
                        $name = $token.GetAttribute('Name')
                        if ($name -and $name.ToLower().Contains($hint.ToLower())) {{
                            $selected = $token
                            break
                        }}
                    }}
                    if ($selected) {{
                        $voice.Voice = $selected
                    }}
                }} catch {{
                }}
            }}
            [void]$voice.Speak({_powershell_quote(text)})
            """
        ).strip()
        try:
            self._run_powershell(sapi_script, timeout=max(len(text) * 0.18, 6.0))
            return
        except RuntimeError:
            logger.warning("SAPI voice output failed; retrying with System.Speech synthesizer.")

        synth_script = textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            $ProgressPreference = 'SilentlyContinue'
            Add-Type -AssemblyName System.Speech
            $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
            try {{
                $synth.Rate = {rate}
            }} catch {{
            }}
            $hint = {_powershell_quote(self.voice_name_hint)}
            if ($hint) {{
                try {{
                    $selected = $null
                    foreach ($voice in $synth.GetInstalledVoices()) {{
                        $name = $voice.VoiceInfo.Name
                        if ($name -and $name.ToLower().Contains($hint.ToLower())) {{
                            $selected = $name
                            break
                        }}
                    }}
                    if ($selected) {{
                        $synth.SelectVoice($selected)
                    }}
                }} catch {{
                }}
            }}
            $synth.Speak({_powershell_quote(text)})
            """
        ).strip()
        self._run_powershell(synth_script, timeout=max(len(text) * 0.18, 6.0))

    def _capture_pcm_command(self, *, timeout: float, phrase_time_limit: float) -> bytes | None:
        self._ensure_sounddevice()
        sample_rate = max(self.command_sample_rate, 8000)
        chunk_frames = max(int(sample_rate * 0.1), 1024)
        chunk_seconds = chunk_frames / float(sample_rate)
        pre_roll_chunks = max(int(0.25 / chunk_seconds), 1)
        max_silence_chunks = max(int(self.command_silence_seconds / chunk_seconds), 1)
        pre_roll: collections.deque[bytes] = collections.deque(maxlen=pre_roll_chunks)
        started = False
        silence_chunks = 0
        chunks: list[bytes] = []
        start_deadline = time.monotonic() + max(timeout, 0.5)
        capture_deadline = start_deadline + max(phrase_time_limit, 1.0)

        try:
            with self._sounddevice.RawInputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                blocksize=chunk_frames,
            ) as stream:
                while self._running:
                    data, overflowed = stream.read(chunk_frames)
                    if overflowed:
                        logger.debug("Voice input overflowed while capturing microphone audio.")
                    chunk = bytes(data)
                    now = time.monotonic()
                    rms = self._pcm_rms(chunk)
                    speaking = rms >= self.command_rms_threshold

                    if not started:
                        pre_roll.append(chunk)
                        if speaking:
                            started = True
                            chunks.extend(pre_roll)
                            silence_chunks = 0
                            capture_deadline = now + max(phrase_time_limit, 1.0)
                        elif now >= start_deadline:
                            return None
                        continue

                    chunks.append(chunk)
                    if speaking:
                        silence_chunks = 0
                    else:
                        silence_chunks += 1
                    if now >= capture_deadline:
                        break
                    if silence_chunks >= max_silence_chunks:
                        break
        except Exception as exc:
            raise RuntimeError("Microphone capture failed for Gemini Live input.") from exc

        pcm = b"".join(chunks)
        return pcm or None

    def _pcm_rms(self, pcm: bytes) -> int:
        if not pcm:
            return 0
        samples = memoryview(pcm).cast("h")
        if not samples:
            return 0
        power = sum(sample * sample for sample in samples) / len(samples)
        return int(math.sqrt(power))

    def _transcribe_pcm_with_gemini_live(
        self,
        pcm: bytes,
        *,
        sample_rate: int | None = None,
        timeout: float = 20.0,
    ) -> str:
        if not pcm:
            return ""
        sample_rate = sample_rate or self.command_sample_rate
        try:
            return asyncio.run(
                asyncio.wait_for(
                    self._transcribe_pcm_with_gemini_live_async(pcm, sample_rate=sample_rate),
                    timeout=timeout,
                )
            )
        except Exception as exc:
            logger.warning("Gemini Live input failed; falling back to Gemini audio understanding: %s", exc)
            return self._transcribe_pcm_with_gemini_model(pcm, sample_rate=sample_rate)

    async def _transcribe_pcm_with_gemini_live_async(self, pcm: bytes, *, sample_rate: int) -> str:
        self._ensure_gemini_live()
        from google.genai import types

        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            system_instruction=(
                "Transcribe the user's audio verbatim. "
                "Do not answer the user, summarize, translate, or add commentary."
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
        )
        latest_transcript = ""
        fallback_text = ""
        async with self._gemini_live_client.aio.live.connect(
            model=self.gemini_live_model,
            config=config,
        ) as session:
            await session.send_realtime_input(
                audio=types.Blob(data=pcm, mime_type=f"audio/pcm;rate={sample_rate}")
            )
            await session.send_realtime_input(audio_stream_end=True)
            async for message in session.receive():
                server_content = getattr(message, "server_content", None)
                transcription = getattr(server_content, "input_transcription", None) if server_content else None
                if transcription and transcription.text:
                    latest_transcript = transcription.text.strip()
                text = getattr(message, "text", None)
                if text:
                    fallback_text = text.strip()
        return latest_transcript or fallback_text

    def _transcribe_pcm_with_gemini_model(self, pcm: bytes, *, sample_rate: int) -> str:
        self._ensure_gemini_live()
        from google.genai import types

        wav_bytes = self._pcm_to_wav_bytes(pcm, sample_rate=sample_rate)
        response = self._gemini_live_client.models.generate_content(
            model=self.gemini_input_model,
            contents=[
                "Transcribe this spoken audio verbatim. Return only the words spoken.",
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            ],
            config=types.GenerateContentConfig(temperature=0),
        )
        text = getattr(response, "text", None)
        if text:
            return text.strip()
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    return part_text.strip()
        return ""

    def _start_work_sound(self):
        if self.work_sound in {"", "off", "none", "silent"}:
            return
        self._stop_work_sound()
        stop_event = threading.Event()
        worker = threading.Thread(target=self._work_sound_loop, args=(stop_event,), daemon=True)
        self._work_sound_stop = stop_event
        self._work_sound_thread = worker
        worker.start()

    def _stop_work_sound(self) -> bool:
        stop_event = self._work_sound_stop
        worker = self._work_sound_thread
        was_active = bool(worker and worker.is_alive())
        if stop_event:
            stop_event.set()
        if worker:
            worker.join(timeout=0.4)
        self._work_sound_stop = None
        self._work_sound_thread = None
        return was_active

    def _work_sound_loop(self, stop_event: threading.Event):
        if not _is_windows():
            stop_event.wait()
            return
        try:
            import winsound
        except ImportError:
            stop_event.wait()
            return

        if self.work_sound == "chime":
            pattern = [(784, 90), (988, 90), (1175, 130)]
            gap = 0.45
        elif self.work_sound == "pulse":
            pattern = [(660, 70), (0, 60), (660, 70), (0, 180)]
            gap = 0.25
        else:
            pattern = [(523, 70), (659, 70), (784, 95), (659, 70)]
            gap = 0.55

        while not stop_event.is_set():
            for frequency, duration_ms in pattern:
                if stop_event.is_set():
                    return
                if frequency <= 0:
                    if stop_event.wait(duration_ms / 1000.0):
                        return
                    continue
                try:
                    winsound.Beep(frequency, duration_ms)
                except RuntimeError:
                    if stop_event.wait(duration_ms / 1000.0):
                        return
                if stop_event.wait(0.04):
                    return
            if stop_event.wait(gap):
                return

    def _truncate_for_voice(self, text: str) -> str:
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return ""
        if len(cleaned) <= self.max_reply_chars:
            return cleaned
        return cleaned[: self.max_reply_chars - 3].rstrip() + "..."

    def _should_stop(self, command: str) -> bool:
        normalized = command.strip().lower()
        return any(word in normalized for word in self.stop_words)

    def _with_spinner(self, state: str, detail: str, fn: Callable[[], object]):
        stop_event = threading.Event()
        spinner = threading.Thread(
            target=self._spinner_loop,
            args=(state, detail, stop_event),
            daemon=True,
        )
        spinner.start()
        try:
            return fn()
        finally:
            stop_event.set()
            spinner.join(timeout=0.3)

    def _spinner_loop(self, state: str, detail: str, stop_event: threading.Event):
        index = 0
        while not stop_event.wait(0.14):
            frame = _SPINNER_FRAMES[index % len(_SPINNER_FRAMES)]
            self._render_status(state, f"{frame} {detail}")
            index += 1

    def _render_status(self, state: str, detail: str):
        line = f"[voice] {state}"
        if detail:
            line += f" | {detail}"
        with self._console_lock:
            padding = max(self._last_status_length - len(line), 0)
            try:
                sys.stdout.write("\r" + line + (" " * padding))
                sys.stdout.flush()
                self._last_status_length = len(line)
            except OSError:
                self._last_status_length = 0

    def _clear_status_line(self):
        with self._console_lock:
            if not self._last_status_length:
                return
            try:
                sys.stdout.write("\r" + (" " * self._last_status_length) + "\r")
                sys.stdout.flush()
            except OSError:
                pass
            self._last_status_length = 0

    def _println(self, message: str):
        self._clear_status_line()
        with self._console_lock:
            print(message, flush=True)

    def _print_intro(self):
        self._println("[voice] local voice channel ready")
        self._println(f"[voice] wake word: {self.wake_word}")
        if self.owner_name:
            self._println(f"[voice] owner: {self.owner_name}")
        self._println(f"[voice] audio backend: {self.audio_backend}")
        self._println(f"[voice] input provider: {self.voice_input_provider}")
        if self.voice_input_provider == _VOICE_INPUT_GEMINI_LIVE:
            self._println(f"[voice] live model: {self.gemini_live_model}")
            self._println(f"[voice] input fallback model: {self.gemini_input_model}")
        self._println(f"[voice] output provider: {self.voice_output_provider}")
        if self.audio_backend == _AUDIO_BACKEND_WINDOWS:
            self._println(f"[voice] recognition locale: {self.recognition_locale}")
        else:
            self._println(f"[voice] stt backend: {self.stt_backend}")
        self._publish_presence("idle", f"say '{self.wake_word}'", active=True, error="")
        self._render_status("idle", f"say '{self.wake_word}'")

    def _publish_presence(self, state: str, detail: str, **fields):
        self._presence.update(
            state=state,
            detail=detail,
            wake_word=self.wake_word,
            backend=self.audio_backend,
            **fields,
        )

    def _resolve_owner_name(self) -> str:
        explicit = _env_text("HELLOAGI_OWNER_NAME", "")
        if explicit:
            return explicit
        onboard = Path("helloagi.onboard.json")
        if onboard.exists():
            try:
                raw = json.loads(onboard.read_text(encoding="utf-8"))
            except Exception:
                raw = {}
            if isinstance(raw, dict):
                owner = str(raw.get("owner_name", "")).strip()
                if owner:
                    return owner
        mission = getattr(self.agent.settings, "mission", "")
        match = re.search(r"\bfor\s+([A-Z][a-zA-Z]+)\b", mission or "")
        return match.group(1).strip() if match else ""

    def _person_prefix(self) -> str:
        if not self.owner_name:
            return ""
        return f"{self.owner_name}, "

    def _compose_acknowledgement(self, command: str) -> str:
        lowered = command.lower()
        prefix = self._person_prefix()
        if any(word in lowered for word in ("open", "go to", "search", "check", "find", "look up")):
            return f"Sure {prefix}I'm on it. Stay with me.".replace("  ", " ").strip()
        if any(word in lowered for word in ("post", "send", "message", "reply")):
            return f"Sure {prefix}I'll handle that now.".replace("  ", " ").strip()
        return f"Sure {prefix}let me check that for you.".replace("  ", " ").strip()

    def _tool_progress_message(self, tool_name: str, decision: str) -> str:
        if decision != "allow":
            return ""
        lowered = tool_name.lower()
        if "browser" in lowered or "openclaw" in lowered or "computer" in lowered:
            return "I'm on the browser now."
        if "search" in lowered or "google" in lowered:
            return "I'm checking that now."
        if "telegram" in lowered or "discord" in lowered or "post" in lowered:
            return "I'm sending that now."
        if "file" in lowered or "read" in lowered or "write" in lowered:
            return "I'm checking the files now."
        if "bash" in lowered or "shell" in lowered or "exec" in lowered or "command" in lowered:
            return "I'm running that now."
        return "I'm working on it now."

    def _maybe_voice_tool_update(self, tool_name: str, decision: str):
        message = self._tool_progress_message(tool_name, decision)
        if message:
            self._speak_progress(message, style_hint="progress")

    def _speak_progress(self, text: str, *, style_hint: str = "progress", force: bool = False):
        if not text:
            return
        now = time.monotonic()
        if not force and (now - self._last_progress_spoken_at) < self.progress_throttle_seconds:
            return
        resume_work_sound = self._stop_work_sound()
        spoken = self._speak_internal(
            text,
            announce=False,
            style_hint=style_hint,
            idle_after=False,
            state="thinking",
            detail="working...",
        )
        if spoken:
            self._last_progress_spoken_at = time.monotonic()
        if resume_work_sound:
            self._start_work_sound()

    def _speak_internal(
        self,
        text: str,
        *,
        announce: bool,
        style_hint: str,
        idle_after: bool,
        state: str = "speaking",
        detail: str = "",
    ) -> str:
        self._ensure_audio_stack()
        spoken = self._truncate_for_voice(text)
        if not spoken:
            return ""
        if announce:
            self._println(f"{self.agent.identity.state.name}: {spoken}")
        self._publish_presence(state, spoken[:120], active=True, last_spoken=spoken, error="")
        with self._speech_lock:
            try:
                self._with_spinner("speaking", spoken[:32], lambda: self._speak_blocking(spoken, style_hint=style_hint))
            except Exception as exc:
                logger.warning("Voice output failed: %s", exc)
                self._publish_presence("error", str(exc), active=True, last_spoken=spoken, error=str(exc))
                self._println(f"[voice] speaker unavailable | {exc}")
                return ""
        if not idle_after:
            next_detail = detail or "working..."
            self._publish_presence(state, next_detail, active=True, last_spoken=spoken, error="")
            self._render_status(state, next_detail)
        return spoken

    def _build_tts_prompt(self, text: str, *, style_hint: str) -> str:
        base_style = self.gemini_tts_style.strip() or (
            "Speak naturally, warm, responsive, and human. Keep it concise and avoid sounding robotic."
        )
        transcript = text
        if style_hint == "ack":
            transcript = f"[warmly] {text}"
        elif style_hint == "progress":
            transcript = f"[warmly] {text}"
        elif style_hint == "approval":
            transcript = f"[serious] {text}"
        elif style_hint == "error":
            transcript = f"[serious] {text}"
        return f"{base_style}\n\nTranscript:\n{transcript}"


def run_voice_session(config_path: str = "helloagi.json", policy_pack: str = "safe-default"):
    """Convenience entrypoint for local voice-only runs."""
    from agi_runtime.config.settings import load_settings

    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings, policy_pack=policy_pack)
    channel = VoiceChannel(agent)
    asyncio.run(channel.start())
