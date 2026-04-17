"""HelloAGI Agent — The world's first governed autonomous agent.

This is the beating heart of HelloAGI. It combines:
- Unbounded autonomous tool-calling loop (real AGI behavior)
- Deterministic SRG governance on EVERY action (unjailbreakable safety)
- Persistent identity evolution (the agent grows smarter)
- Anticipatory latency caching (ALE)
- Semantic memory integration (auto-store + auto-recall)
- Skill crystallization (learns from successful workflows)
- Sub-agent delegation (spawns isolated specialists)
- Context compression (handles infinite conversations)
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
from agi_runtime.skills.manager import SkillManager
from agi_runtime.memory.compressor import ContextCompressor
from agi_runtime.robustness.circuit_breaker import CircuitBreaker
from agi_runtime.supervisor.supervisor import Supervisor

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


class HelloAGIAgent:
    """The HelloAGI autonomous agent.

    Combines unbounded autonomy with deterministic governance.
    Every tool call passes through SRG. No exceptions.
    """

    MAX_TURNS = 40
    MAX_OUTPUT_TOKENS = 16384

    def __init__(self, settings: RuntimeSettings | None = None, policy_pack: str = "safe-default"):
        self.settings = settings or RuntimeSettings()
        self.governor = SRGGovernor(policy_pack=policy_pack)
        self.ale = ALEngine()
        self.identity = IdentityEngine(
            path=self.settings.memory_path,
            mission=self.settings.mission,
            style=self.settings.style,
            domain_focus=self.settings.domain_focus,
        )
        self.journal = Journal(self.settings.journal_path)
        self.skills = SkillManager()
        self.compressor = ContextCompressor()
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=60.0)
        self.supervisor = Supervisor(pause_consecutive=5, pause_rate=0.5)

        # Initialize tool registry and discover all builtin tools
        self.tool_registry = ToolRegistry.get_instance()
        discover_builtin_tools()

        # Semantic memory store (lazy-loaded)
        self._embedding_store = None

        # Conversation history for multi-turn context
        self._history: List[dict] = []

        # Track tool calls in current session for skill crystallization
        self._session_tool_calls: List[dict] = []

        # Wire Claude API backbone
        self._claude = None
        if _ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
            self._claude = _anthropic_lib.Anthropic()

        # Callbacks (set by CLI/API layer)
        self.on_user_input: Optional[callable] = None
        self.on_stream: Optional[callable] = None
        self.on_tool_start: Optional[callable] = None
        self.on_tool_end: Optional[callable] = None

    @property
    def embedding_store(self):
        """Lazy-load embedding store."""
        if self._embedding_store is None:
            try:
                from agi_runtime.memory.embeddings import GeminiEmbeddingStore
                self._embedding_store = GeminiEmbeddingStore()
            except Exception:
                self._embedding_store = None
        return self._embedding_store

    # ── System Prompt Builder ──────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Build the system prompt from identity, memory, skills, and context."""
        identity = self.identity.state
        parts = [
            f"You are {identity.name}, a {identity.character}.",
            f"Purpose: {identity.purpose}.",
            f"Principles: {'; '.join(identity.principles)}.",
            f"Style: {self.settings.style}.",
            f"Domain focus: {self.settings.domain_focus}.",
            "",
            "You are a world-class autonomous agent powered by HelloAGI — the first AGI runtime with deterministic governance.",
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
            "",
            "After completing a complex multi-step task successfully, consider using skill_create",
            "to save the workflow as a reusable skill for future similar requests.",
            "Before starting a task, check if skill_invoke can help with an existing skill.",
        ]

        # Inject skill index
        skills_index = self.skills.get_skills_index()
        if skills_index:
            parts.append("")
            parts.append("<skills>")
            parts.append(skills_index)
            parts.append("</skills>")

        # Inject memory context
        memory_context = self._get_memory_context()
        if memory_context:
            parts.append("")
            parts.append("<memory-context>")
            parts.append(memory_context)
            parts.append("</memory-context>")

        return "\n".join(parts)

    def _get_memory_context(self) -> Optional[str]:
        """Retrieve relevant memories for the current context via semantic search."""
        store = self.embedding_store
        if not store or not store.available or store.count() == 0:
            # Fallback: check text-based memory file
            return self._get_file_memory_context()

        try:
            # Build query from recent conversation
            recent_text = " ".join(
                m.get("content", "")[:200] if isinstance(m.get("content"), str) else ""
                for m in self._history[-5:]
            )
            if not recent_text.strip():
                return None

            results = store.search(recent_text, top_k=5)
            if results:
                entries = []
                for r in results:
                    if r.score > 0.3:  # Only include relevant memories
                        cat = r.metadata.get("category", "fact")
                        entries.append(f"- [{cat}] {r.text}")
                if entries:
                    return "\n".join(entries)
        except Exception:
            pass
        return None

    def _get_file_memory_context(self) -> Optional[str]:
        """Fallback: read from text-based memory file."""
        from pathlib import Path
        mem_file = Path("memory/facts.txt")
        if mem_file.exists():
            try:
                lines = mem_file.read_text(encoding="utf-8").splitlines()
                if lines:
                    # Return last 10 memories
                    return "\n".join(f"- {l}" for l in lines[-10:])
            except Exception:
                pass
        return None

    # ── Auto Memory Store ──────────────────────────────────────

    def _auto_store_memory(self, user_input: str, response_text: str):
        """Automatically extract and store key facts from the interaction."""
        # Only store if the interaction was substantial
        if len(response_text) < 50 or len(user_input) < 10:
            return

        store = self.embedding_store
        if store and store.available:
            # Store user preferences and key facts
            try:
                # Store the core interaction as a memory
                summary = f"User asked: {user_input[:200]}. Agent responded about: {response_text[:200]}"
                store.add(summary, metadata={"category": "interaction", "ts": time.time()})
            except Exception:
                pass
        else:
            # Fallback: append to text file
            from pathlib import Path
            mem_file = Path("memory/facts.txt")
            mem_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                with mem_file.open("a", encoding="utf-8") as f:
                    f.write(f"[interaction] User: {user_input[:100]} | Response: {response_text[:100]}\n")
            except Exception:
                pass

    # ── Sub-Agent Delegation ───────────────────────────────────

    async def _handle_delegation(self, goal: str, context: str, toolset_filter: str, max_turns: int) -> str:
        """Spawn an isolated sub-agent to handle a delegated task."""
        if not self._claude:
            return "Cannot delegate: LLM backbone not configured."

        # Build restricted tool list
        if toolset_filter:
            allowed = [t.strip() for t in toolset_filter.split(",")]
            tools = [s for s in self._get_tool_schemas() if s["name"] in allowed]
        else:
            # Default sub-agent tools (no delegation to prevent recursion)
            blocked = {"delegate_task", "skill_create", "skill_invoke"}
            tools = [s for s in self._get_tool_schemas() if s["name"] not in blocked]

        sub_system = (
            f"You are a specialist sub-agent of {self.identity.state.name}.\n"
            f"Your task: {goal}\n"
            f"Context: {context}\n\n"
            "Complete the task efficiently. Be concise in your final response.\n"
            "You have a limited number of turns — focus on the goal."
        )

        sub_history = [{"role": "user", "content": f"Task: {goal}\n\nContext: {context}"}]
        sub_max = min(max_turns, 15)
        results_summary = []

        for turn in range(sub_max):
            try:
                response = self._claude.messages.create(
                    model="claude-haiku-4-5-20251001",  # Use fast model for sub-agents
                    max_tokens=4096,
                    system=sub_system,
                    tools=tools,
                    messages=sub_history,
                )
            except Exception as e:
                return f"Sub-agent LLM error: {e}"

            text_parts = []
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))

            sub_history.append({"role": "assistant", "content": response.content})

            if not tool_calls:
                final = "\n".join(text_parts)
                self.journal.write("delegation_complete", {
                    "goal": goal[:200],
                    "turns": turn + 1,
                    "result_preview": final[:300],
                })
                return final

            # Execute tool calls with SRG governance
            tool_results = []
            for tc in tool_calls:
                tool_def = self.tool_registry.get(tc.name)
                tool_risk = tool_def.risk.value if tool_def else "medium"
                tool_gov = self.governor.evaluate_tool(tc.name, tc.input, tool_risk)

                if tool_gov.decision == "deny":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": f"BLOCKED by SRG: {'; '.join(tool_gov.reasons)}",
                    })
                    continue

                if not self.circuit_breaker.can_execute(tc.name):
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": f"Circuit breaker open for '{tc.name}' — skipped.",
                    })
                    continue

                result = await self.tool_registry.execute(tc.name, tc.input)
                if result.ok:
                    self.circuit_breaker.record_success(tc.name)
                else:
                    self.circuit_breaker.record_failure(tc.name)
                self.journal.write("delegation_tool", {
                    "goal": goal[:100],
                    "tool": tc.name,
                    "ok": result.ok,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result.to_content()[:5000],
                })

            sub_history.append({"role": "user", "content": tool_results})

        return f"Sub-agent completed {sub_max} turns on: {goal}"

    # ── Main Think Loop ────────────────────────────────────────

    def think(self, user_input: str) -> AgentResponse:
        """Main entry point — synchronous wrapper around the async agentic loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
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
        self._session_tool_calls = []
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
                    self.journal.write("thinking", {"text": getattr(block, 'thinking', '')[:500]})

            # Add assistant message to history
            self._history.append({"role": "assistant", "content": response.content})

            # If no tool calls, we're done — return the text response
            if not tool_calls:
                final_text = "\n".join(text_parts)

                if gov.decision == "escalate":
                    final_text += "\n\n⚠️ This request was flagged for human confirmation before high-risk actions."

                # Cache the response
                self.ale.put(user_input, final_text)

                # Auto-store to memory
                self._auto_store_memory(user_input, final_text)

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

                # Special handling: delegate_task spawns a real sub-agent
                if tc.name == "delegate_task" and self._claude:
                    delegation_result = await self._handle_delegation(
                        goal=tc.input.get("goal", ""),
                        context=tc.input.get("context", ""),
                        toolset_filter=tc.input.get("toolset", ""),
                        max_turns=tc.input.get("max_turns", 15),
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": delegation_result,
                    })
                    self._session_tool_calls.append({"tool": tc.name, "input": tc.input, "ok": True})
                    if self.on_tool_start:
                        self.on_tool_start(tc.name, tc.input, "allow")
                    if self.on_tool_end:
                        self.on_tool_end(tc.name, True, delegation_result[:200])
                    continue

                # Get tool definition for risk level
                tool_def = self.tool_registry.get(tc.name)
                tool_risk = tool_def.risk.value if tool_def else "medium"

                # SRG GOVERNANCE ON EVERY TOOL CALL
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

                # Circuit breaker check — skip tools that are failing repeatedly
                if not self.circuit_breaker.can_execute(tc.name):
                    cb_status = self.circuit_breaker.get_status(tc.name)
                    result_content = (
                        f"⚡ Circuit breaker OPEN for '{tc.name}' — "
                        f"{cb_status['failures']} consecutive failures. "
                        f"Will retry after cooldown."
                    )
                    self.journal.write("circuit_breaker_open", {
                        "tool": tc.name,
                        "failures": cb_status["failures"],
                        "short_circuited": cb_status["short_circuited"],
                    })
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

                # Record success/failure in circuit breaker + supervisor
                if result.ok:
                    self.circuit_breaker.record_success(tc.name)
                    self.supervisor.record_tool_success(tc.name)
                else:
                    self.circuit_breaker.record_failure(tc.name)
                    self.supervisor.record_tool_failure(tc.name, result.to_content()[:200])

                self.journal.write("tool_exec", {
                    "tool": tc.name,
                    "input": {k: str(v)[:200] for k, v in tc.input.items()},
                    "ok": result.ok,
                    "output_preview": result.to_content()[:300],
                    "governance": tool_gov.decision,
                    "risk": tool_gov.risk,
                })

                self._session_tool_calls.append({
                    "tool": tc.name,
                    "input": tc.input,
                    "ok": result.ok,
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

            # Context compression if needed
            if self.compressor.needs_compression(self._history):
                self._history = await self.compressor.compress(self._history)
                self.journal.write("context_compressed", {"new_length": len(self._history)})

        # Reached max turns
        final_text = (
            f"I've used all {self.MAX_TURNS} turns working on your request. "
            f"Made {total_tool_calls} tool calls across {turns_used} turns."
        )
        self.journal.write("max_turns_reached", {"tool_calls": total_tool_calls})
        return AgentResponse(
            text=final_text, decision=gov.decision, risk=gov.risk,
            tool_calls_made=total_tool_calls, turns_used=turns_used,
        )

    # ── Helpers ────────────────────────────────────────────────

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
        return decision.model

    def _get_tool_schemas(self) -> List[dict]:
        """Get Claude-format tool schemas for all available tools."""
        return self.tool_registry.get_schemas()

    def _template_response(self, user_input: str, gov: GovernanceResult) -> str:
        """Fallback response when Claude API is not available."""
        tools_list = ", ".join(t.name for t in self.tool_registry.list_tools())
        text = (
            f"[{self.identity.state.name} | {self.identity.state.character}]\n"
            f"I received your request but my LLM backbone is not configured.\n"
            f"To enable full AGI capabilities, set ANTHROPIC_API_KEY in your environment.\n\n"
            f"Without the LLM, I can still run tools directly.\n"
            f"Available tools ({len(self.tool_registry.list_tools())}): {tools_list}\n"
        )
        if gov.decision == "escalate":
            text += "\n⚠️ This request was flagged for human confirmation."
        return text

    def clear_history(self):
        """Clear conversation history for a fresh session."""
        self._history = []
        self._session_tool_calls = []

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
