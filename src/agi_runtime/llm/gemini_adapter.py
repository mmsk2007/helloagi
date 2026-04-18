"""Convert HelloAGI tool schemas to Gemini and parse generate_content responses."""

from __future__ import annotations

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
