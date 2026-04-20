import os
import time
import unittest
from unittest.mock import Mock, patch

from agi_runtime.channels.voice import (
    VoiceChannel,
    _normalize_audio_backend,
    _normalize_voice_input_provider,
    _normalize_voice_output_provider,
    _resolve_voice_principal_id,
    _split_sentences,
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
            with patch("agi_runtime.channels.voice.resolve_provider_credential") as mocked:
                mocked.return_value.configured = True
                mocked.return_value.secret = "fake"
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

    def test_voice_output_provider_raises_when_gemini_requested_without_google_creds(self):
        with patch("agi_runtime.channels.voice.resolve_provider_credential") as mocked:
            mocked.return_value.configured = False
            with self.assertRaises(RuntimeError) as ctx:
                _normalize_voice_output_provider("gemini_tts")
        self.assertIn("GOOGLE_API_KEY", str(ctx.exception))

    def test_voice_input_provider_raises_when_gemini_requested_without_google_creds(self):
        with patch("agi_runtime.channels.voice.resolve_provider_credential") as mocked:
            mocked.return_value.configured = False
            with self.assertRaises(RuntimeError) as ctx:
                _normalize_voice_input_provider("gemini_live")
        self.assertIn("GOOGLE_API_KEY", str(ctx.exception))

    def test_voice_output_provider_auto_still_falls_back_silently(self):
        with patch("agi_runtime.channels.voice.resolve_provider_credential") as mocked:
            mocked.return_value.configured = False
            provider = _normalize_voice_output_provider("auto")
        self.assertEqual(provider, "local")

    def test_probe_reports_missing_google_creds_without_raising(self):
        with patch.dict(
            os.environ,
            {"HELLOAGI_VOICE_OUTPUT_PROVIDER": "gemini_tts", "HELLOAGI_VOICE_INPUT_PROVIDER": "gemini_live"},
            clear=False,
        ):
            with patch("agi_runtime.channels.voice.resolve_provider_credential") as mocked:
                mocked.return_value.configured = False
                probe = probe_voice_runtime()
        self.assertIn("google_credentials", probe["missing_modules"])
        self.assertFalse(probe["available"])

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

    def test_followup_window_defaults_to_twelve_seconds(self):
        with patch.dict(os.environ, {}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.followup_window_seconds, 12.0)

    def test_followup_window_can_be_disabled(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_FOLLOWUP_SECONDS": "0"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.followup_window_seconds, 0.0)

    def test_conversation_mode_env_on(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_CONVERSATION_MODE": "on"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertTrue(channel.conversation_mode)

    def test_conversation_mode_env_off_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertFalse(channel.conversation_mode)

    def test_ack_style_defaults_to_beep(self):
        with patch.dict(os.environ, {}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.ack_style, "beep")

    def test_ack_style_invalid_falls_back_to_beep(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_ACK_STYLE": "rainbow"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertEqual(channel.ack_style, "beep")

    def test_conversation_mode_disables_spoken_ack_by_default(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_CONVERSATION_MODE": "on"}, clear=False):
            channel = VoiceChannel(_DummyAgent())
        self.assertFalse(channel.speak_ack_enabled)

    def test_self_echo_detection_matches_recent_spoken_text(self):
        channel = VoiceChannel(_DummyAgent())
        channel._last_spoken_texts.append("I'm ready to dive into some deep work now.")
        self.assertTrue(channel._looks_like_self_echo("Ready to dive into deep work now"))
        self.assertFalse(channel._looks_like_self_echo("Open Google and check flights tomorrow"))

    def test_listen_once_filters_self_echo_and_keeps_listening(self):
        channel = VoiceChannel(_DummyAgent())
        channel._last_spoken_texts.append("I'm ready to dive into some deep work now.")
        channel._running = True
        raw = Mock(side_effect=["Ready to dive into deep work now", "Open Google"])
        with patch.object(channel, "_listen_once_raw", raw):
            heard = channel._listen_once(label="follow up", timeout=4.0, phrase_time_limit=2.0)
        self.assertEqual(heard, "Open Google")
        self.assertEqual(raw.call_count, 2)

    def test_gemini_live_failure_enters_cooldown_and_uses_fallback(self):
        with patch.dict(os.environ, {"HELLOAGI_VOICE_INPUT_PROVIDER": "gemini_live"}, clear=False):
            with patch("agi_runtime.channels.voice.resolve_provider_credential") as mocked:
                mocked.return_value.configured = True
                mocked.return_value.secret = "fake"
                channel = VoiceChannel(_DummyAgent())
        future = Mock()
        future.result.side_effect = RuntimeError("received 1011 internal error")
        def _fake_submit(coro, loop):
            coro.close()
            return future
        with patch.object(channel, "_ensure_live_loop", return_value=object()):
            with patch("agi_runtime.channels.voice.asyncio.run_coroutine_threadsafe", side_effect=_fake_submit):
                with patch.object(channel, "_transcribe_pcm_with_gemini_model", return_value="fallback transcript") as fallback:
                    heard = channel._transcribe_pcm_with_gemini_live(b"pcm", sample_rate=16000, timeout=0.1)
        self.assertEqual(heard, "fallback transcript")
        self.assertTrue(channel._gemini_live_cooldown_until > time.monotonic())
        self.assertEqual(fallback.call_count, 1)

        with patch("agi_runtime.channels.voice.asyncio.run_coroutine_threadsafe") as live_call:
            with patch.object(channel, "_transcribe_pcm_with_gemini_model", return_value="fallback again") as fallback:
                heard = channel._transcribe_pcm_with_gemini_live(b"pcm", sample_rate=16000, timeout=0.1)
        self.assertEqual(heard, "fallback again")
        live_call.assert_not_called()
        self.assertEqual(fallback.call_count, 1)

    def test_split_sentences_basic(self):
        chunks = _split_sentences("Hello. How are you?")
        self.assertEqual(chunks, ["Hello.", "How are you?"])

    def test_split_sentences_merges_short_trailing_fragment(self):
        chunks = _split_sentences("The SRG reviewed the call. Now allowing. OK.")
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[-1].endswith("OK."))

    def test_split_sentences_handles_empty(self):
        self.assertEqual(_split_sentences(""), [])
        self.assertEqual(_split_sentences("   "), [])

    def test_split_sentences_collapses_whitespace(self):
        chunks = _split_sentences("Line one.\n\n  Line two!")
        self.assertEqual(chunks, ["Line one.", "Line two!"])
