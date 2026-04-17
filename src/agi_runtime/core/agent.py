"""HelloAGI Agent — The world's first governed autonomous agent.

This is the beating heart of HelloAGI. It combines:
- Unbounded autonomous tool-calling loop (real AGI behavior)
- Deterministic SRG governance on EVERY action (unjailbreakable safety)
- Persistent identity evolution (the agent grows smarter)
- Anticipatory latency caching (ALE)
- Semantic memory integration
- Full observability via JSONL journal
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agi_runtime.governance.srg import SRGGovernor, GovernanceResult
from agi_runtime.latency.ale import ALEngine
from agi_runtime.memory.identity import IdentityEngine
from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.tools.registry import ToolRegistry, ToolResult, discover_builtin_tools
from agi_runtime.observability.journal import Journal

try:
    import anthropic as _anthropic_lib
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


@dataclass
class AgentResponse:
    """Response from the agent."""
    text: str
    decision: str
    risk: float
    tool_calls_made: int = 0
    turns_used: int = 0


@dataclass
class ToolCall:
    """A tool call from the LLM."""
    id: str
    name: str
    input: dict


@dataclass
class ConversationMessage:
    """A message in the conversation history."""
    role: str  # "user", "assistant", "tool_result"
    content: Any


class HelloAGIAgent:
    """The HelloAGI autonomous agent.

    Combines unbounded autonomy with deterministic governance.
    Every tool call passes through SRG. No exceptions.
    """

    MAX_TURNS = 40
    MAX_OUTPUT_TOKENS = 16384

    def __init__(self, settings: RuntimeSettings | None = None):
        self.settings = settings or RuntimeSettings()
        self.governor = SRGGovernor()
        self.ale = ALEngine()
        self.identity = IdentityEngine(
            path=self.settings.memory_path,
            mission=self.settings.mission,
            style=self.settings.style,
            domain_focus=self.settings.domain_focus,
        )
        self.journal = Journal(self.settings.journal_path)

        # Initialize tool registry and discover all builtin tools
        self.tool_registry = ToolRegistry.get_instance()
        discover_builtin_tools()

        # Conversation history for multi-turn context
        self._history: List[dict] = []

        # Wire Claude API backbone
        self._claude = None
        if _ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
            self._claude = _anthropic_lib.Anthropic()

        # Callback for user input (set by CLI/API layer)
        self.on_user_input: Optional[callable] = None
        # Callback for streaming output (set by CLI/API layer)
        self.on_stream: Optional[callable] = None
        # Callback for tool execution display (set by CLI/API layer)
        self.on_tool_start: Optional[callable] = None
        self.on_tool_end: Optional[callable] = None

    def _build_system_prompt(self) -> str:
        """Build the system prompt from identity, memory, and skills."""
        identity = self.identity.state
        parts = [
            f"You are {identity.name}, a {identity.character}.",
            f"Purpose: {identity.purpose}.",
            f"Principles: {'; '.join(identity.principles)}.",
            f"Style: {self.settings.style}.",
            f"Domain focus: {self.settings.domain_focus}.",
            "",
            "You are a world-class autonomous agent powered by HelloAGI.",
            "You have tools to interact with the real world: execute commands, read/write files, search the web, run code, and more.",
            "You MUST use tools to accomplish tasks — don't just describe what to do, actually DO it.",
            "",
            "When given a complex task:",
            "1. Break it down into concrete steps",
            "2. Use tools to execute each step",
            "3. Verify results after each step",
            "4. Report back with what you accomplished",
            "",
            "Be direct, practical, and action-oriented. Show results, not plans.",
            "If you need clarification, use the ask_user tool.",
            "If a tool call fails, analyze the error and try a different approach.",
        ]

        # Inject memory context if available
        memory_context = self._get_memory_context()
        if memory_context:
            parts.append("")
            parts.append("<memory-context>")
            parts.append(memory_context)
            parts.append("</memory-context>")

        return "\n".join(parts)

    def _get_memory_context(self) -> Optional[str]:
        """Retrieve relevant memories for the current context."""
        try:
            from agi_runtime.memory.embeddings import GeminiEmbeddingStore
            store = GeminiEmbeddingStore()
            if store.available and store.count() > 0:
                # Search for relevant memories based on recent conversation
                recent_text = " ".join(
                    m.get("content", "")[:100] if isinstance(m.get("content"), str) else ""
                    for m in self._history[-3:]
                )
                if recent_text.strip():
                    results = store.search(recent_text, top_k=3)
                    if results:
                        return "\n".join(f"- [{r.metadata.get('category', 'fact')}] {r.text}" for r in results)
        except Exception:
            pass
        return None

    def _get_tool_schemas(self) -> List[dict]:
        """Get Claude-format tool schemas for all available tools."""
        return self.tool_registry.get_schemas()

    def think(self, user_input: str) -> AgentResponse:
        """Main entry point — synchronous wrapper around the async agentic loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in an async context — run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._think_async(user_input))
                return future.result()
        return asyncio.run(self._think_async(user_input))

    async def _think_async(self, user_input: str) -> AgentResponse:
        """The full agentic loop — the beating heart of HelloAGI."""

        # 1. Evolve identity based on observation
        self.identity.evolve(user_input)
        self.journal.write("input", {"text": user_input})

        # 2. SRG governance gate on user input
        gov = self.governor.evaluate(user_input)
        if gov.decision == "deny":
            msg = gov.safe_alternative or "I can't help with unsafe or boundary-violating requests."
            self.journal.write("deny", {"risk": gov.risk, "reasons": gov.reasons})
            return AgentResponse(text=msg, decision=gov.decision, risk=gov.risk)

        # 3. Check ALE cache for known intent
        cached = self.ale.get(user_input)
        if cached:
            self.journal.write("cache_hit", {"text": cached[:200]})
            return AgentResponse(text=cached, decision=gov.decision, risk=gov.risk)

        # 4. If no Claude API, fall back to template response
        if not self._claude:
            text = self._template_response(user_input, gov)
            return AgentResponse(text=text, decision=gov.decision, risk=gov.risk)

        # 5. THE AGENTIC LOOP — real AGI behavior
        self._history.append({"role": "user", "content": user_input})
        tools = self._get_tool_schemas()
        system_prompt = self._build_system_prompt()

        total_tool_calls = 0
        turns_used = 0

        for turn in range(self.MAX_TURNS):
            turns_used = turn + 1

            # Call Claude with tools
            try:
                response = self._claude.messages.create(
                    model=self._select_model(user_input),
                    max_tokens=self.MAX_OUTPUT_TOKENS,
                    system=system_prompt,
                    tools=tools,
                    messages=self._history,
                )
            except Exception as e:
                error_msg = f"LLM call failed: {e}"
                self.journal.write("llm_error", {"error": str(e), "turn": turn})
                return AgentResponse(
                    text=error_msg, decision=gov.decision, risk=gov.risk,
                    tool_calls_made=total_tool_calls, turns_used=turns_used,
                )

            # Process response content blocks
            text_parts = []
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    ))
                elif block.type == "thinking":
                    # Log thinking but don't expose to user
                    self.journal.write("thinking", {"text": getattr(block, 'thinking', '')[:500]})

            # Add assistant message to history
            self._history.append({"role": "assistant", "content": response.content})

            # If no tool calls, we're done — return the text response
            if not tool_calls:
                final_text = "\n".join(text_parts)

                # Add escalation warning if needed
                if gov.decision == "escalate":
                    final_text += "\n\n⚠️ This request was flagged for human confirmation before high-risk actions."

                # Cache the response
                self.ale.put(user_input, final_text)
                self.journal.write("response", {
                    "decision": gov.decision,
                    "risk": gov.risk,
                    "turns": turns_used,
                    "tool_calls": total_tool_calls,
                })

                # Evolve identity based on successful interaction
                self.identity.evolve(final_text)

                return AgentResponse(
                    text=final_text,
                    decision=gov.decision,
                    risk=gov.risk,
                    tool_calls_made=total_tool_calls,
                    turns_used=turns_used,
                )

            # Execute tool calls — SRG GATE ON EVERY CALL
            tool_results = []
            for tc in tool_calls:
                total_tool_calls += 1

                # Get tool definition for risk level
                tool_def = self.tool_registry.get(tc.name)
                tool_risk = tool_def.risk.value if tool_def else "medium"

                # SRG GOVERNANCE ON EVERY TOOL CALL — HelloAGI's killer feature
                tool_gov = self.governor.evaluate_tool(tc.name, tc.input, tool_risk)

                if self.on_tool_start:
                    self.on_tool_start(tc.name, tc.input, tool_gov.decision)

                if tool_gov.decision == "deny":
                    result_content = f"🛑 BLOCKED by SRG governance: {'; '.join(tool_gov.reasons)}\n{tool_gov.safe_alternative or ''}"
                    self.journal.write("tool_denied", {
                        "tool": tc.name,
                        "risk": tool_gov.risk,
                        "reasons": tool_gov.reasons,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result_content,
                    })
                    if self.on_tool_end:
                        self.on_tool_end(tc.name, False, result_content)
                    continue

                if tool_gov.decision == "escalate":
                    # Ask user for approval
                    approved = await self._request_user_approval(tc, tool_gov)
                    if not approved:
                        result_content = "User denied this action."
                        self.journal.write("tool_user_denied", {"tool": tc.name})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tc.id,
                            "content": result_content,
                        })
                        if self.on_tool_end:
                            self.on_tool_end(tc.name, False, result_content)
                        continue

                # Execute the tool
                result = await self.tool_registry.execute(tc.name, tc.input)

                self.journal.write("tool_exec", {
                    "tool": tc.name,
                    "input": {k: str(v)[:200] for k, v in tc.input.items()},
                    "ok": result.ok,
                    "output_preview": result.to_content()[:300],
                    "governance": tool_gov.decision,
                    "risk": tool_gov.risk,
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result.to_content(),
                })

                if self.on_tool_end:
                    self.on_tool_end(tc.name, result.ok, result.to_content()[:200])

            # Add tool results to history
            self._history.append({"role": "user", "content": tool_results})

            # Context management — trim if too large
            self._maybe_trim_history()

        # Reached max turns
        final_text = f"I've used all {self.MAX_TURNS} turns working on your request. Here's what I accomplished with {total_tool_calls} tool calls across {turns_used} turns."
        self.journal.write("max_turns_reached", {"tool_calls": total_tool_calls})
        return AgentResponse(
            text=final_text, decision=gov.decision, risk=gov.risk,
            tool_calls_made=total_tool_calls, turns_used=turns_used,
        )

    async def _request_user_approval(self, tool_call: ToolCall, gov: GovernanceResult) -> bool:
        """Request user approval for an escalated tool call."""
        prompt = (
            f"\n⚠️  SRG ESCALATION — Tool '{tool_call.name}' requires approval.\n"
            f"   Risk: {gov.risk:.2f} | Reasons: {', '.join(gov.reasons)}\n"
            f"   Input: {json.dumps(tool_call.input, indent=2)[:500]}\n"
            f"   Approve? (y/n): "
        )

        if self.on_user_input:
            response = self.on_user_input(prompt)
        else:
            # Fallback to stdin
            try:
                response = input(prompt).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return False

        return response in ("y", "yes", "approve", "ok")

    def _select_model(self, user_input: str) -> str:
        """Select the appropriate Claude model based on task complexity."""
        from agi_runtime.models.router import ModelRouter
        router = ModelRouter()
        decision = router.route(user_input)

        model_map = {
            "speed": "claude-haiku-4-5-20251001",
            "balanced": "claude-sonnet-4-6-20250514",
            "quality": "claude-sonnet-4-6-20250514",
        }
        return model_map.get(decision.tier, "claude-sonnet-4-6-20250514")

    def _template_response(self, user_input: str, gov: GovernanceResult) -> str:
        """Fallback response when Claude API is not available."""
        text = (
            f"[{self.identity.state.name} | {self.identity.state.character}]\n"
            f"I received your request but my LLM backbone is not configured.\n"
            f"To enable full AGI capabilities, set ANTHROPIC_API_KEY in your environment.\n\n"
            f"Without the LLM, I can still run tools via /tool commands:\n"
            f"  Available tools: {', '.join(t.name for t in self.tool_registry.list_tools())}\n"
        )
        if gov.decision == "escalate":
            text += "\n⚠️ This request was flagged for human confirmation."
        return text

    def _maybe_trim_history(self):
        """Trim conversation history if it's getting too long."""
        # Keep last 30 messages to stay within context limits
        if len(self._history) > 40:
            # Keep first message (original user input) + last 30
            self._history = self._history[:1] + self._history[-30:]

    def clear_history(self):
        """Clear conversation history for a fresh session."""
        self._history = []

    def get_tools_info(self) -> str:
        """Get a formatted list of available tools."""
        tools = self.tool_registry.list_tools()
        if not tools:
            return "No tools available."

        lines = []
        current_toolset = None
        for t in sorted(tools, key=lambda x: (x.toolset.value, x.name)):
            if t.toolset != current_toolset:
                current_toolset = t.toolset
                lines.append(f"\n[{current_toolset.value.upper()}]")
            risk_icon = {"none": "⬜", "low": "🟢", "medium": "🟡", "high": "🔴"}.get(t.risk.value, "⬜")
            lines.append(f"  {risk_icon} {t.name}: {t.description}")

        return "\n".join(lines)


# Backward compatibility
AGIRuntimeAgent = HelloAGIAgent
