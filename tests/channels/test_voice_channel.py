import os
import unittest
from unittest.mock import patch

from agi_runtime.channels.voice import (
    VoiceChannel,
    _normalize_audio_backend,
    _normalize_voice_input_provider,
    _normalize_voice_output_provider,
    _resolve_voice_principal_id,
    probe_voice_runtime,
)


class _DummyState:
    name = "Lana"


class _DummyIdentity:
    state = _DummyState()


class _DummySettings:
    identity_name = "Lana"


class _DummyAgent:
    settings = _DummySettings()
    identity = _DummyIdentity()


class TestVoiceChannel(unittest.TestCase):
    def test_windows_prefers_native_audio_backend_by_default(self):
        backend = _normalize_audio_backend("", platform_name="Windows")
        self.assertEqual(backend, "windows_native")

    def test_backend_can_be_forced_to_speech_recognition(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_AUDIO_BACKEND": "speech_recognition"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.audio_backend, "speech_recognition")

    def test_voice_output_provider_can_be_forced_local(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_OUTPUT_PROVIDER": "local"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.voice_output_provider, "local")

    def test_voice_input_provider_can_be_forced_gemini_live(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_INPUT_PROVIDER": "gemini_live"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.voice_input_provider, "gemini_live")

    def test_voice_input_provider_defaults_to_local(self):
        provider = _normalize_voice_input_provider("")
        self.assertEqual(provider, "local")

    def test_voice_principal_defaults_to_shared_local(self):
        with patch.dict(os.environ, {}, clear=False):
            provider = _resolve_voice_principal_id()
        self.assertEqual(provider, "local:default")

    def test_voice_principal_can_be_overridden(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_PRINCIPAL_ID": "voice:alex"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.principal_id, "voice:alex")

    def test_voice_output_provider_defaults_to_local_without_google_creds(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_OUTPUT_PROVIDER": "gemini_tts"}, clear=False):
            with patch("agi_runtime.channels.voice.resolve_provider_credential") as mocked:
                mocked.return_value.configured = False
                provider = _normalize_voice_output_provider("gemini_tts")
        self.assertEqual(provider, "local")

    def test_wake_word_comes_from_env(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_WAKE_WORD": "hey atlas"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.wake_word, "hey atlas")

    def test_owner_name_can_come_from_env(self):
        with patch.dict(os.environ, {"HELLOAGI_OWNER_NAME": "Alex"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.owner_name, "Alex")
        self.assertIn("Alex", channel._compose_acknowledgement("check flights"))

    def test_stop_words_are_configurable(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_STOP_WORDS": "sleep,shutdown"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertTrue(channel._should_stop("please sleep now"))
        self.assertFalse(channel._should_stop("keep going"))

    def test_voice_response_is_truncated_for_speech(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_MAX_REPLY_CHARS": "20"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        rendered = channel._truncate_for_voice("one two three four five six seven")
        self.assertLessEqual(len(rendered), 20)
        self.assertTrue(rendered.endswith("..."))

    def test_voice_probe_reports_backend(self):
        probe = probe_voice_runtime()
        self.assertIn("backend", probe)
        self.assertIn("available", probe)

    def test_gemini_tts_prompt_uses_tags_for_ack(self):
        with patch.dict(os.environ, {"HELLOAGI_OWNER_NAME": "Alex"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        prompt = channel._build_tts_prompt("Sure Alex, I'm on it.", style_hint="ack")
        self.assertIn("[warmly]", prompt)
        self.assertIn("Transcript:", prompt)
