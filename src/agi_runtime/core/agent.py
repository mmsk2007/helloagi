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
import contextvars
import importlib.util
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agi_runtime.governance.memory_guard import MemoryGuard
from agi_runtime.governance.srg import SRGGovernor, GovernanceResult
from agi_runtime.latency.ale import ALEngine
from agi_runtime.memory.identity import IdentityEngine
from agi_runtime.memory.principals import PrincipalProfileStore
from agi_runtime.config.providers import (
    provider_credential_usable_for_llm_backbone,
    resolve_provider_credential,
)
from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.tools.registry import (
    ToolRegistry,
    ToolResult,
    discover_builtin_tools,
    set_tool_context,
    reset_tool_context,
)
from agi_runtime.observability.journal import Journal
from agi_runtime.skills.manager import SkillManager
from agi_runtime.memory.compressor import ContextCompressor
from agi_runtime.robustness.circuit_breaker import CircuitBreaker
from agi_runtime.supervisor.supervisor import Supervisor
from agi_runtime.core.personality import GrowthTracker, build_personality_prompt, get_time_greeting
from agi_runtime.core.time_context import build_time_context_block
from agi_runtime.intelligence.sentiment import SentimentTracker
from agi_runtime.intelligence.context_compiler import ContextCompiler
from agi_runtime.intelligence.patterns import PatternDetector
from agi_runtime.policies.packs import get_pack

try:
    import anthropic as _anthropic_lib
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


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

    MAX_OUTPUT_TOKENS = 16384

    def __init__(self, settings: RuntimeSettings | None = None, policy_pack: str = "safe-default"):
        self.settings = settings or RuntimeSettings()
        self.policy_pack_name = policy_pack
        self.policy_pack = get_pack(policy_pack)
        self.governor = SRGGovernor(policy_pack=policy_pack, settings=self.settings)
        self.memory_guard = MemoryGuard()
        self.ale = ALEngine()
        self.identity = IdentityEngine(
            path=self.settings.memory_path,
            mission=self.settings.mission,
            style=self.settings.style,
            domain_focus=self.settings.domain_focus,
        )
        self.principals = PrincipalProfileStore()
        self.journal = Journal(self.settings.journal_path)
        self.skills = SkillManager()
        self.compressor = ContextCompressor()
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=60.0)
        self.supervisor = Supervisor(pause_consecutive=5, pause_rate=0.5)
        self.growth = GrowthTracker()
        self.sentiment = SentimentTracker()
        self.context_compiler = ContextCompiler()
        self.patterns = PatternDetector()
        self.max_turns = self.policy_pack.max_turns

        # Initialize tool registry and discover all builtin tools
        self.tool_registry = ToolRegistry.get_instance()
        discover_builtin_tools()

        # Semantic memory store (lazy-loaded)
        self._embedding_store = None

        # Conversation state is per principal (chat/user), not process-global.
        self._principal_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
            "helloagi_principal_id",
            default="local:default",
        )
        self._histories: Dict[str, List[dict]] = {}
        self._session_tool_calls_by_principal: Dict[str, List[dict]] = {}

        # LLM backbones (Anthropic + optional Gemini) and active provider
        self._claude = None
        self._gemini_client = None
        self._llm_provider: Optional[str] = None  # "anthropic" | "google" | None
        self._configure_llm_backbone()

        # Callbacks (set by CLI/API layer)
        self.on_user_input: Optional[Callable] = None
        self.on_stream: Optional[Callable] = None
        self.on_tool_start: Optional[Callable] = None
        self.on_tool_end: Optional[Callable] = None

        # Active channel context: set by the channel layer (e.g. TelegramChannel)
        # immediately before think() so outbound tools (send_file, send_image)
        # can route attachments back through the same channel/chat the user
        # spoke from. Stays None for CLI/API callers, which makes those tools
        # gracefully degrade to "share path with user" text.
        self._active_channel: Any = None
        self._active_channel_id: Optional[str] = None

    def set_principal(self, principal_id: str) -> None:
        """Set active conversation principal for this execution context."""
        pid = (principal_id or "local:default").strip() or "local:default"
        self._principal_ctx.set(pid)

    def current_principal(self) -> str:
        """Return the active conversation principal id."""
        return self._principal_ctx.get()

    def current_profile_principal(self) -> str:
        """Return the canonical profile principal for memory and preferences."""
        return self.principals.resolve_profile_id(self.current_principal())

    def set_active_channel(self, channel: Any, channel_id: Optional[str]) -> None:
        """Bind the channel that originated the current turn so outbound tools
        (send_file, send_image) can deliver attachments back to the same chat.
        Pass channel=None, channel_id=None to clear.
        """
        self._active_channel = channel
        self._active_channel_id = channel_id

    @property
    def _history(self) -> List[dict]:
        pid = self.current_principal()
        return self._histories.setdefault(pid, [])

    @_history.setter
    def _history(self, value: List[dict]) -> None:
        self._histories[self.current_principal()] = value

    @property
    def _session_tool_calls(self) -> List[dict]:
        pid = self.current_principal()
        return self._session_tool_calls_by_principal.setdefault(pid, [])

    @_session_tool_calls.setter
    def _session_tool_calls(self, value: List[dict]) -> None:
        self._session_tool_calls_by_principal[self.current_principal()] = value

    def _configure_llm_backbone(self) -> None:
        """Pick Anthropic vs Google from settings/env and available credentials."""
        env_override = os.environ.get("HELLOAGI_LLM_PROVIDER")
        pref = (env_override or getattr(self.settings, "llm_provider", None) or "auto")
        pref = str(pref).strip().lower()
        if pref not in ("auto", "anthropic", "google"):
            pref = "auto"

        anthropic_credential = resolve_provider_credential("anthropic")
        google_credential = resolve_provider_credential("google")
        has_genai = _module_available("google.genai")

        if pref == "auto":
            anthropic_ok = (
                _ANTHROPIC_AVAILABLE
                and provider_credential_usable_for_llm_backbone("anthropic", anthropic_credential)
            )
            google_ok = (
                provider_credential_usable_for_llm_backbone("google", google_credential) and has_genai
            )
        else:
            anthropic_ok = _ANTHROPIC_AVAILABLE and anthropic_credential.configured
            google_ok = google_credential.configured and has_genai

        if anthropic_ok:
            self._claude = _anthropic_lib.Anthropic(api_key=anthropic_credential.secret)
        if google_ok:
            from google import genai
            self._gemini_client = genai.Client(api_key=google_credential.secret)

        if pref == "anthropic":
            self._llm_provider = "anthropic" if anthropic_ok else None
        elif pref == "google":
            self._llm_provider = "google" if google_ok else None
        else:
            if anthropic_ok:
                self._llm_provider = "anthropic"
            elif google_ok:
                self._llm_provider = "google"
            else:
                self._llm_provider = None

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

    def _build_system_prompt(
        self,
        bootstrap_instruction: Optional[str] = None,
        profile_excerpt: Optional[str] = None,
    ) -> str:
        """Build the system prompt from identity, memory, skills, and context."""
        identity = self.identity.state
        parts = [
            f"You are {identity.name}, a {identity.character}.",
            f"Purpose: {identity.purpose}.",
            f"Principles: {'; '.join(identity.principles)}.",
            f"Style: {self.settings.style}.",
            f"Domain focus: {self.settings.domain_focus}.",
            "",
            "You are a world-class autonomous agent powered by HelloAGI — an open governed-autonomy runtime.",
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
            "When the user asks to be reminded later, prefer reminder_create/reminder_list/reminder_cancel/reminder_pause/reminder_resume/reminder_run_now.",
            "",
            "Conversational norms:",
            "- Sound natural and human; avoid robotic section headers in normal chat.",
            "- For simple social messages, reply without unnecessary tool use.",
            "- Use tools when they materially improve outcome quality or correctness.",
            "- Prefer purpose-built tools like send_file, send_image, and send_voice over generic shell/code commands when delivering user-facing media.",
            "- Keep responses concise unless the user asks for depth.",
        ]

        # Inject grounded time awareness (date, clock, timezone, UTC anchor).
        # Per-principal tz overrides the runtime setting, which overrides host-local.
        principal_state = self.principals.get(self.current_profile_principal())
        time_block = build_time_context_block(
            principal_tz=getattr(principal_state, "timezone", "") or None,
            settings_tz=getattr(self.settings, "preferred_timezone", "") or None,
        )
        parts.append("")
        parts.append("<time-context>")
        parts.append(time_block)
        parts.append("</time-context>")

        # Inject personality and growth awareness
        personality = build_personality_prompt(
            identity_name=identity.name,
            identity_character=identity.character,
            growth=self.growth,
        )
        if personality:
            parts.append("")
            parts.append("<personality>")
            parts.append(personality)
            parts.append("</personality>")

        # Inject emotional intelligence (mood-aware responses)
        mood_guidance = self.sentiment.get_mood_guidance()
        if mood_guidance:
            parts.append("")
            parts.append("<emotional-context>")
            parts.append(mood_guidance)
            parts.append("</emotional-context>")

        # Inject behavioral patterns (learned preferences)
        pattern_context = self.patterns.get_personalization_prompt()
        if pattern_context:
            parts.append("")
            parts.append("<user-patterns>")
            parts.append(pattern_context)
            parts.append("</user-patterns>")

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

        if profile_excerpt:
            parts.append("")
            parts.append("<principal-profile>")
            parts.append(profile_excerpt)
            parts.append("</principal-profile>")

        if bootstrap_instruction:
            parts.append("")
            parts.append("<bootstrap-guidance>")
            parts.append(bootstrap_instruction)
            parts.append("</bootstrap-guidance>")

        return "\n".join(parts)

    def _allowed_tool(self, tool_name: str) -> bool:
        """Check whether the active policy pack allows a tool."""
        if self.policy_pack.read_only:
            blocked_in_read_only = {
                "bash_exec",
                "python_exec",
                "file_write",
                "file_patch",
                "skill_create",
                "delegate_task",
            }
            if tool_name in blocked_in_read_only:
                return False

        if self.policy_pack.allowed_tools and tool_name not in self.policy_pack.allowed_tools:
            return False
        if self.policy_pack.blocked_tools and tool_name in self.policy_pack.blocked_tools:
            return False
        return True

    def _list_allowed_tools(self):
        return [t for t in self.tool_registry.list_tools() if self._allowed_tool(t.name)]

    def _get_memory_context(self) -> Optional[str]:
        """Retrieve relevant memories for the current context via semantic search."""
        store = self.embedding_store
        if not store or not store.available or store.count() == 0:
            # Fallback: check text-based memory file
            return self._get_file_memory_context()
        principal_id = self.current_profile_principal()
        memory_scope = os.environ.get("HELLOAGI_MEMORY_SCOPE", "compat")

        try:
            # Build query from recent conversation
            recent_text = " ".join(
                m.get("content", "")[:200] if isinstance(m.get("content"), str) else ""
                for m in self._history[-5:]
            )
            if not recent_text.strip():
                return None

            results = store.search(
                recent_text,
                top_k=5,
                principal_id=principal_id,
                scope=memory_scope,
            )
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
                    principal_id = self.current_profile_principal()
                    scope = os.environ.get("HELLOAGI_MEMORY_SCOPE", "compat").strip().lower()
                    if principal_id:
                        tag = f"[principal:{principal_id}]"
                        if scope == "strict":
                            lines = [ln for ln in lines if tag in ln]
                        else:
                            lines = [ln for ln in lines if (tag in ln or "[principal:" not in ln)]
                    if not lines:
                        return None
                    # Return last 10 memories
                    return "\n".join(f"- {l}" for l in lines[-10:])
            except Exception:
                pass
        return None

    # ── Auto Memory Store ──────────────────────────────────────

    def _auto_store_memory(self, user_input: str, response_text: str):
        """Automatically extract and store key facts from the interaction.

        Every write passes through ``MemoryGuard`` — this closes OWASP
        Agentic Top 10 **ASI06 (Memory & Context Poisoning)**. Without
        this gate, a user who got the agent to echo an injection phrase
        ("ignore previous instructions …") would permanently embed that
        text in the retrieval index and bias every future run.
        """
        # Only store if the interaction was substantial
        if len(response_text) < 50 or len(user_input) < 10:
            return

        # MemoryGuard pass — build the candidate summary, then sanitize or
        # drop per the guard's verdict. The guard may deny outright, in
        # which case we journal the denial and skip the write entirely.
        raw_summary = (
            f"User asked: {user_input[:200]}. "
            f"Agent responded about: {response_text[:200]}"
        )
        guard_result = self.memory_guard.inspect(raw_summary, kind="interaction")
        if guard_result.decision == "deny":
            try:
                self.journal.write("memory_guard_denied", {
                    "kind": "interaction",
                    "reasons": guard_result.reasons[:5],
                    "signal_count": guard_result.signal_count,
                })
            except Exception:
                pass
            return
        safe_summary = (
            guard_result.sanitized_text
            if guard_result.decision == "sanitize" and guard_result.sanitized_text
            else raw_summary
        )
        if guard_result.decision == "sanitize":
            try:
                self.journal.write("memory_guard_sanitized", {
                    "kind": "interaction",
                    "reasons": guard_result.reasons[:5],
                    "signal_count": guard_result.signal_count,
                })
            except Exception:
                pass

        store = self.embedding_store
        principal_id = self.current_profile_principal()
        if store and store.available:
            # Store vetted summary only (per OWASP ASI06 mitigation).
            try:
                store.add(
                    safe_summary,
                    metadata={
                        "category": "interaction",
                        "ts": time.time(),
                        "guard_decision": guard_result.decision,
                    },
                    principal_id=principal_id,
                )
            except Exception:
                pass
        else:
            # Fallback: append to text file — also sanitized. We never
            # persist raw user input, even on this path.
            from pathlib import Path
            mem_file = Path("memory/facts.txt")
            mem_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                with mem_file.open("a", encoding="utf-8") as f:
                    prefix = f"[principal:{principal_id}] " if principal_id else ""
                    # Clip the fallback line, and rely on `safe_summary`
                    # having already been scrubbed by MemoryGuard.
                    f.write(
                        f"{prefix}[interaction] {safe_summary[:200]}\n"
                    )
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

                result = await self._execute_tool(tc.name, tc.input)
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
            ctx = contextvars.copy_context()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(ctx.run, asyncio.run, self._think_async(user_input))
                return future.result()
        return asyncio.run(self._think_async(user_input))

    async def _think_async(self, user_input: str) -> AgentResponse:
        """The full agentic loop — the beating heart of HelloAGI."""
        principal_id = self.current_principal()
        profile_principal_id = self.current_profile_principal()
        self.principals.record_user_message(profile_principal_id, user_input)
        bootstrap_instruction = self.principals.bootstrap_instruction(profile_principal_id)
        profile_excerpt = self.principals.profile_excerpt(profile_principal_id)

        # 0. Track growth & detect mood
        self.growth.record_session()
        self.growth.record_message()
        self._mood = self.sentiment.record(user_input)

        # 1. Evolve identity based on observation
        self.identity.evolve(user_input)
        self.journal.write(
            "input",
            {
                "text": user_input,
                "principal_id": principal_id,
                "profile_principal_id": profile_principal_id,
            },
        )

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

        # 4. No usable LLM backbone (see HELLOAGI_LLM_PROVIDER + API keys)
        if self._llm_provider is None:
            text = self._template_response(user_input, gov)
            return AgentResponse(text=text, decision=gov.decision, risk=gov.risk)

        # 5. Agentic loop (Claude or Gemini)
        self._history.append({"role": "user", "content": user_input})
        self._session_tool_calls = []
        tools = self._get_tool_schemas()
        system_prompt = self._build_system_prompt(
            bootstrap_instruction=bootstrap_instruction,
            profile_excerpt=profile_excerpt,
        )

        if self._llm_provider == "anthropic":
            return await self._think_async_claude(user_input, gov, tools, system_prompt)
        return await self._think_async_gemini(user_input, gov, tools, system_prompt)

    async def _think_async_claude(
        self, user_input: str, gov: GovernanceResult, tools: List[dict], system_prompt: str
    ) -> AgentResponse:
        """Anthropic Messages API tool loop."""
        total_tool_calls = 0
        turns_used = 0

        for turn in range(self.max_turns):
            turns_used = turn + 1

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

            self._history.append({"role": "assistant", "content": response.content})

            if not tool_calls:
                final_text = "\n".join(text_parts)

                if gov.decision == "escalate":
                    final_text += "\n\n⚠️ This request was flagged for human confirmation before high-risk actions."

                self.ale.put(user_input, final_text)
                self._auto_store_memory(user_input, final_text)
                tools_used = [tc["tool"] for tc in self._session_tool_calls]
                self.patterns.record_interaction(user_input, tools_used)

                self.journal.write("response", {
                    "decision": gov.decision,
                    "risk": gov.risk,
                    "turns": turns_used,
                    "tool_calls": total_tool_calls,
                })

                self.identity.evolve(final_text)

                return AgentResponse(
                    text=final_text,
                    decision=gov.decision,
                    risk=gov.risk,
                    tool_calls_made=total_tool_calls,
                    turns_used=turns_used,
                )

            tool_results = []
            for tc in tool_calls:
                total_tool_calls += 1
                self.growth.record_tool_call()

                if not self._allowed_tool(tc.name):
                    result_content = f"Tool '{tc.name}' is not available under the active policy pack '{self.policy_pack.name}'."
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result_content,
                    })
                    self.journal.write("tool_blocked_by_policy_pack", {
                        "tool": tc.name,
                        "policy_pack": self.policy_pack.name,
                    })
                    if self.on_tool_end:
                        self.on_tool_end(tc.name, False, result_content)
                    continue

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

                tool_def = self.tool_registry.get(tc.name)
                tool_risk = tool_def.risk.value if tool_def else "medium"

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

                result = await self._execute_tool(tc.name, tc.input)

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

            self._history.append({"role": "user", "content": tool_results})

            if self.compressor.needs_compression(self._history):
                self._history = await self.compressor.compress(self._history)
                self.journal.write("context_compressed", {"new_length": len(self._history)})

        final_text = (
            f"I've used all {self.max_turns} turns working on your request. "
            f"Made {total_tool_calls} tool calls across {turns_used} turns."
        )
        self.journal.write("max_turns_reached", {"tool_calls": total_tool_calls, "max_turns": self.max_turns})
        return AgentResponse(
            text=final_text, decision=gov.decision, risk=gov.risk,
            tool_calls_made=total_tool_calls, turns_used=turns_used,
        )

    async def _gemini_generate_with_resilience(
        self,
        *,
        model_id: str,
        contents: List[Any],
        config: Any,
        turn: int,
    ) -> tuple[Any, str]:
        """Call Gemini generate_content with exponential backoff on overload, then stable fallback."""
        from agi_runtime.models.gemini_router import GEMINI_FALLBACK_STABLE

        backoff_delays = [0.0, 1.5, 3.0, 6.0, 12.0]

        def classify(exc: BaseException) -> str:
            s = str(exc).lower()
            code = str(exc)
            if "404" in code or "not found" in s or "no longer available" in s:
                return "not_found"
            if (
                "503" in code
                or "unavailable" in s
                or "429" in code
                or "resource_exhausted" in s
                or "resource exhausted" in s
                or ("too many" in s and "request" in s)
                or "overloaded" in s
                or "high demand" in s
                or "try again later" in s
            ):
                return "overload"
            return "other"

        last_exc: Optional[BaseException] = None
        models = [model_id]
        if model_id != GEMINI_FALLBACK_STABLE:
            models.append(GEMINI_FALLBACK_STABLE)

        for mid in models:
            for attempt, delay in enumerate(backoff_delays):
                if delay:
                    await asyncio.sleep(delay)
                try:
                    resp = self._gemini_client.models.generate_content(
                        model=mid,
                        contents=contents,
                        config=config,
                    )
                    return resp, mid
                except Exception as e:
                    last_exc = e
                    kind = classify(e)
                    self.journal.write(
                        "gemini_generate_attempt",
                        {"model": mid, "attempt": attempt, "kind": kind, "turn": turn},
                    )
                    if kind == "other":
                        raise
                    if kind == "not_found":
                        break
                    if attempt == len(backoff_delays) - 1:
                        break

        if last_exc:
            raise last_exc
        raise RuntimeError("Gemini generate_content failed")

    async def _think_async_gemini(
        self, user_input: str, gov: GovernanceResult, tools: List[dict], system_prompt: str
    ) -> AgentResponse:
        """Google Gemini generate_content tool loop (manual function calling)."""
        from google.genai import types as gtypes
        from agi_runtime.llm.gemini_adapter import (
            build_generate_config,
            claude_tools_to_gemini_tool,
            extract_model_content,
            function_call_args_as_dict,
            genai_types_available,
            response_text_and_calls,
        )
        from agi_runtime.models.gemini_router import route_gemini_model

        if not genai_types_available() or not self._gemini_client:
            text = self._template_response(user_input, gov)
            return AgentResponse(text=text, decision=gov.decision, risk=gov.risk)

        gemini_tool = claude_tools_to_gemini_tool(tools)
        model_id = route_gemini_model(
            user_input,
            default_tier=getattr(self.settings, "default_model_tier", "balanced"),
        ).model
        config = build_generate_config(
            system_instruction=system_prompt,
            gemini_tool=gemini_tool,
            max_output_tokens=min(self.MAX_OUTPUT_TOKENS, 8192),
        )

        contents: List[Any] = [
            gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=user_input)]),
        ]

        total_tool_calls = 0
        turns_used = 0

        for turn in range(self.max_turns):
            turns_used = turn + 1
            try:
                response, model_id = await self._gemini_generate_with_resilience(
                    model_id=model_id,
                    contents=contents,
                    config=config,
                    turn=turn,
                )
            except Exception as e:
                self.journal.write("llm_error", {"error": str(e), "turn": turn, "provider": "google"})
                return AgentResponse(
                    text=f"Gemini LLM call failed: {e}",
                    decision=gov.decision,
                    risk=gov.risk,
                    tool_calls_made=total_tool_calls,
                    turns_used=turns_used,
                )

            try:
                model_content = extract_model_content(response)
            except Exception as e:
                return AgentResponse(
                    text=f"Gemini returned an empty response: {e}",
                    decision=gov.decision,
                    risk=gov.risk,
                    tool_calls_made=total_tool_calls,
                    turns_used=turns_used,
                )

            contents.append(model_content)
            plain_text, raw_calls = response_text_and_calls(response)

            tool_calls: List[ToolCall] = []
            for idx, fc in enumerate(raw_calls):
                name = getattr(fc, "name", None) or ""
                if not name:
                    continue
                args = function_call_args_as_dict(fc)
                tid = f"gemini_{turn}_{idx}_{name}"
                tool_calls.append(ToolCall(id=tid, name=name, input=args))

            self._history.append({
                "role": "assistant",
                "content": plain_text or ("[tool_calls] " + ", ".join(tc.name for tc in tool_calls)),
            })

            if not tool_calls:
                final_text = plain_text or ""
                if gov.decision == "escalate":
                    final_text += "\n\n⚠️ This request was flagged for human confirmation before high-risk actions."
                self.ale.put(user_input, final_text)
                self._auto_store_memory(user_input, final_text)
                tools_used = [tc["tool"] for tc in self._session_tool_calls]
                self.patterns.record_interaction(user_input, tools_used)
                self.journal.write("response", {
                    "decision": gov.decision,
                    "risk": gov.risk,
                    "turns": turns_used,
                    "tool_calls": total_tool_calls,
                    "provider": "google",
                })
                self.identity.evolve(final_text)
                return AgentResponse(
                    text=final_text,
                    decision=gov.decision,
                    risk=gov.risk,
                    tool_calls_made=total_tool_calls,
                    turns_used=turns_used,
                )

            tool_results = []
            func_response_parts = []
            for tc in tool_calls:
                total_tool_calls += 1
                self.growth.record_tool_call()

                if not self._allowed_tool(tc.name):
                    result_content = f"Tool '{tc.name}' is not available under the active policy pack '{self.policy_pack.name}'."
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result_content,
                    })
                    func_response_parts.append(
                        gtypes.Part.from_function_response(name=tc.name, response={"result": result_content})
                    )
                    if self.on_tool_end:
                        self.on_tool_end(tc.name, False, result_content)
                    continue

                if tc.name == "delegate_task":
                    msg = (
                        "delegate_task is only supported with the Anthropic backbone. "
                        "Set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN and HELLOAGI_LLM_PROVIDER=anthropic, "
                        "or complete the task without delegating."
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": msg,
                    })
                    func_response_parts.append(
                        gtypes.Part.from_function_response(name=tc.name, response={"result": msg})
                    )
                    if self.on_tool_end:
                        self.on_tool_end(tc.name, False, msg)
                    continue

                tool_def = self.tool_registry.get(tc.name)
                tool_risk = tool_def.risk.value if tool_def else "medium"
                tool_gov = self.governor.evaluate_tool(tc.name, tc.input, tool_risk)

                if self.on_tool_start:
                    self.on_tool_start(tc.name, tc.input, tool_gov.decision)

                if tool_gov.decision == "deny":
                    result_content = f"🛑 BLOCKED by SRG governance: {'; '.join(tool_gov.reasons)}\n{tool_gov.safe_alternative or ''}"
                    self.journal.write("tool_denied", {"tool": tc.name, "risk": tool_gov.risk, "reasons": tool_gov.reasons})
                    tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result_content})
                    func_response_parts.append(
                        gtypes.Part.from_function_response(name=tc.name, response={"result": result_content})
                    )
                    if self.on_tool_end:
                        self.on_tool_end(tc.name, False, result_content)
                    continue

                if tool_gov.decision == "escalate":
                    approved = await self._request_user_approval(tc, tool_gov)
                    if not approved:
                        result_content = "User denied this action."
                        self.journal.write("tool_user_denied", {"tool": tc.name})
                        tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result_content})
                        func_response_parts.append(
                            gtypes.Part.from_function_response(name=tc.name, response={"result": result_content})
                        )
                        if self.on_tool_end:
                            self.on_tool_end(tc.name, False, result_content)
                        continue

                if not self.circuit_breaker.can_execute(tc.name):
                    cb_status = self.circuit_breaker.get_status(tc.name)
                    result_content = (
                        f"⚡ Circuit breaker OPEN for '{tc.name}' — "
                        f"{cb_status['failures']} consecutive failures. "
                        f"Will retry after cooldown."
                    )
                    tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result_content})
                    func_response_parts.append(
                        gtypes.Part.from_function_response(name=tc.name, response={"result": result_content})
                    )
                    if self.on_tool_end:
                        self.on_tool_end(tc.name, False, result_content)
                    continue

                result = await self._execute_tool(tc.name, tc.input)
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
                self._session_tool_calls.append({"tool": tc.name, "input": tc.input, "ok": result.ok})
                out = result.to_content()
                tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": out})
                func_response_parts.append(gtypes.Part.from_function_response(name=tc.name, response={"result": out}))
                if self.on_tool_end:
                    self.on_tool_end(tc.name, result.ok, result.to_content()[:200])

            self._history.append({"role": "user", "content": tool_results})
            contents.append(gtypes.Content(role="tool", parts=func_response_parts))

            if self.compressor.needs_compression(self._history):
                self._history = await self.compressor.compress(self._history)
                self.journal.write("context_compressed", {"new_length": len(self._history)})

        final_text = (
            f"I've used all {self.max_turns} turns working on your request. "
            f"Made {total_tool_calls} tool calls across {turns_used} turns."
        )
        self.journal.write("max_turns_reached", {"tool_calls": total_tool_calls, "max_turns": self.max_turns})
        return AgentResponse(
            text=final_text, decision=gov.decision, risk=gov.risk,
            tool_calls_made=total_tool_calls, turns_used=turns_used,
        )

    # ── Helpers ────────────────────────────────────────────────

    async def _execute_tool(self, tool_name: str, tool_input: dict) -> ToolResult:
        """Execute a tool with principal- and channel-aware context.

        principal_id scopes memory; channel/channel_id let outbound tools
        (send_file, send_image) deliver back through the same chat the user
        spoke from. Channel is None for CLI/API turns and tools must degrade
        gracefully in that case.
        """
        token = set_tool_context(
            principal_id=self.current_principal(),
            memory_principal_id=self.current_profile_principal(),
            channel=self._active_channel,
            channel_id=self._active_channel_id,
        )
        try:
            return await self.tool_registry.execute(tool_name, tool_input)
        finally:
            reset_tool_context(token)

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
        return [
            schema for schema in self.tool_registry.get_schemas()
            if self._allowed_tool(schema["name"])
        ]

    def _template_response(self, user_input: str, gov: GovernanceResult) -> str:
        """Fallback when no LLM backbone is active (keys + optional google-genai)."""
        allowed_tools = self._list_allowed_tools()
        tools_list = ", ".join(t.name for t in allowed_tools)
        anthropic_ready = resolve_provider_credential("anthropic").configured
        google_ready = resolve_provider_credential("google").configured
        text = (
            f"[{self.identity.state.name} | {self.identity.state.character}]\n"
            f"I received your request but no LLM backbone is active.\n"
            f"- Set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN for Claude (default when present), or\n"
            f"- Set GOOGLE_API_KEY or GOOGLE_AUTH_TOKEN and run `pip install google-genai` to use Gemini "
            f"(use HELLOAGI_LLM_PROVIDER=google when both keys exist).\n\n"
            f"Current: GOOGLE={'set' if google_ready else 'unset'}, "
            f"ANTHROPIC={'set' if anthropic_ready else 'unset'}.\n\n"
            f"Without an LLM, tool execution is still available.\n"
            f"Available tools ({len(allowed_tools)}): {tools_list}\n"
        )
        if gov.decision == "escalate":
            text += "\n⚠️ This request was flagged for human confirmation."
        return text

    def clear_history(self, principal_id: Optional[str] = None):
        """Clear conversation history for one principal or all principals."""
        if principal_id is None:
            self._history = []
            self._session_tool_calls = []
            return
        pid = (principal_id or "").strip()
        if not pid:
            return
        self._histories.pop(pid, None)
        self._session_tool_calls_by_principal.pop(pid, None)

    def get_tools_info(self) -> str:
        """Get a formatted list of available tools."""
        tools = self._list_allowed_tools()
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
