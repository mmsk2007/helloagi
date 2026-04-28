"""Tests for Gemini streaming chunk merge (peer parity with Anthropic on_stream)."""

from types import SimpleNamespace

import pytest


def _chunk_with_parts(parts):
    content = SimpleNamespace(parts=parts)
    cand = SimpleNamespace(content=content)
    return SimpleNamespace(candidates=[cand])


def test_reduce_text_only_chunks():
    pytest.importorskip("google.genai")
    from google.genai import types as gtypes

    from agi_runtime.llm.gemini_adapter import reduce_gemini_stream_chunks, response_text_and_calls

    chunks = [
        _chunk_with_parts([gtypes.Part.from_text(text="a")]),
        _chunk_with_parts([gtypes.Part.from_text(text="b")]),
    ]
    r = reduce_gemini_stream_chunks(chunks, on_stream=None)
    text, calls = response_text_and_calls(r)
    assert "ab" in text.replace("\n", "") or text.strip() == "ab"
    assert calls == []


def test_accumulator_on_stream_text_and_fc_boundary():
    pytest.importorskip("google.genai")
    from google.genai import types as gtypes

    from agi_runtime.llm.gemini_adapter import (
        GeminiStreamAccumulator,
        response_text_and_calls,
    )

    received = []

    def on_stream(x):
        received.append(x)

    acc = GeminiStreamAccumulator(on_stream=on_stream)
    acc.apply_chunk(_chunk_with_parts([gtypes.Part.from_text(text="Hello ")]))
    acc.apply_chunk(_chunk_with_parts([gtypes.Part.from_text(text="world")]))
    fc = gtypes.FunctionCall(name="web_search", args={"q": "x"})
    acc.apply_chunk(_chunk_with_parts([gtypes.Part(function_call=fc)]))
    resp = acc.finish()

    assert received[0] == "Hello "
    assert received[1] == "world"
    assert received[2] is None
    text, calls = response_text_and_calls(resp)
    assert "Hello world" in text.replace("\n", " ")
    assert len(calls) == 1
    assert calls[0].name == "web_search"


def test_genai_types_available():
    from agi_runtime.llm.gemini_adapter import genai_types_available

    # May be False in minimal CI without google-genai
    assert isinstance(genai_types_available(), bool)
