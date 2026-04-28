"""Convert HelloAGI tool schemas to Gemini and parse generate_content responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from google.genai import types as genai_types
    _GENAI_TYPES = True
except ImportError:
    genai_types = None  # type: ignore
    _GENAI_TYPES = False


def genai_types_available() -> bool:
    return _GENAI_TYPES


def claude_tools_to_gemini_tool(claude_schemas: List[dict]) -> Any:
    """Build a single types.Tool with FunctionDeclarations from Claude-format registry schemas."""
    if not _GENAI_TYPES:
        raise ImportError("google-genai is required for the Gemini backbone. pip install google-genai")

    decls = []
    for s in claude_schemas:
        name = s.get("name") or "tool"
        desc = (s.get("description") or "")[:4096]
        schema = s.get("input_schema") or {"type": "object", "properties": {}}
        decls.append(
            genai_types.FunctionDeclaration(
                name=name,
                description=desc,
                parameters_json_schema=schema,
            )
        )
    return genai_types.Tool(function_declarations=decls)


def extract_model_content(response: Any) -> Any:
    if not response.candidates:
        raise RuntimeError("Gemini returned no candidates")
    return response.candidates[0].content


def response_text_and_calls(response: Any) -> Tuple[str, List[Any]]:
    """Plain text (if any) plus function_call parts from the first candidate."""
    text_parts: List[str] = []
    calls: List[Any] = []
    if not response.candidates:
        return "", []
    parts = getattr(response.candidates[0].content, "parts", None) or []
    for part in parts:
        t = getattr(part, "text", None)
        if t:
            text_parts.append(t)
        fc = getattr(part, "function_call", None)
        if fc is not None:
            calls.append(fc)
    return "\n".join(text_parts).strip(), calls


def function_call_args_as_dict(fc: Any) -> Dict[str, Any]:
    args = getattr(fc, "args", None)
    if args is None:
        return {}
    if isinstance(args, dict):
        return dict(args)
    if hasattr(args, "items"):
        return dict(args.items())
    try:
        return dict(args)
    except Exception:
        return {}


@dataclass
class GeminiStreamAccumulator:
    """Incremental merge of ``generate_content_stream`` chunks (testable, reusable)."""

    on_stream: Optional[Any] = None
    segments: List[Any] = field(default_factory=list)  # ("text", str) or ("fc", Any)
    emitted_fc_boundary: bool = False

    def _emit_stream_text(self, delta: str) -> None:
        if not self.on_stream or not delta:
            return
        try:
            self.on_stream(delta)
        except Exception:
            pass

    def _emit_fc_boundary(self) -> None:
        if not self.on_stream or self.emitted_fc_boundary:
            return
        try:
            self.on_stream(None)
        except Exception:
            pass
        self.emitted_fc_boundary = True

    def apply_chunk(self, chunk: Any) -> None:
        if not _GENAI_TYPES:
            raise ImportError("google-genai is required")
        if not getattr(chunk, "candidates", None):
            return
        cand0 = chunk.candidates[0]
        content = getattr(cand0, "content", None)
        if not content:
            return
        parts = getattr(content, "parts", None) or []
        for part in parts:
            t = getattr(part, "text", None)
            if t:
                if self.segments and self.segments[-1][0] == "text":
                    self.segments[-1] = ("text", self.segments[-1][1] + t)
                else:
                    self.segments.append(("text", t))
                self._emit_stream_text(t)
            fc = getattr(part, "function_call", None)
            if fc is not None:
                self._emit_fc_boundary()
                self.segments.append(("fc", fc))

    def finish(self) -> Any:
        from types import SimpleNamespace

        if not _GENAI_TYPES:
            raise ImportError("google-genai is required")
        parts_out: List[Any] = []
        if not self.segments:
            parts_out.append(genai_types.Part.from_text(text=""))
        else:
            for kind, payload in self.segments:
                if kind == "text":
                    parts_out.append(genai_types.Part.from_text(text=payload))
                else:
                    parts_out.append(genai_types.Part(function_call=payload))

        model_content = genai_types.Content(role="model", parts=parts_out)
        return SimpleNamespace(candidates=[SimpleNamespace(content=model_content)])


def reduce_gemini_stream_chunks(
    chunks: List[Any],
    on_stream: Optional[Any] = None,
) -> Any:
    """Merge streamed chunks into one synthetic response (see :class:`GeminiStreamAccumulator`)."""
    acc = GeminiStreamAccumulator(on_stream=on_stream)
    for chunk in chunks:
        acc.apply_chunk(chunk)
    return acc.finish()


def build_generate_config(
    *,
    system_instruction: str,
    gemini_tool: Any,
    max_output_tokens: int,
) -> Any:
    if not _GENAI_TYPES:
        raise ImportError("google-genai is required. pip install google-genai")

    return genai_types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=[gemini_tool],
        tool_config=genai_types.ToolConfig(
            function_calling_config=genai_types.FunctionCallingConfig(mode="AUTO")
        ),
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=max_output_tokens,
    )
