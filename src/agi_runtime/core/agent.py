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
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agi_runtime.governance.memory_guard import MemoryGuard
from agi_runtime.governance.output_guard import OutputGuard
from agi_runtime.governance.srg import SRGGovernor, GovernanceResult
from agi_runtime.governance.srg_adapter import SRGAdapter
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
from agi_runtime.reliability import CompletionVerifier, LoopBreaker, RecoveryManager, StopValidator
from agi_runtime.context.context_manager import ContextManager
from agi_runtime.context.context_segment import ContextSegment
from agi_runtime.core.personality import GrowthTracker, build_personality_prompt, get_time_greeting
from agi_runtime.core.time_context import build_time_context_block
from agi_runtime.intelligence.sentiment import SentimentTracker
from agi_runtime.intelligence.context_compiler import ContextCompiler
from agi_runtime.intelligence.patterns import PatternDetector
from agi_runtime.policies.packs import get_pack
from agi_runtime.cognition.router import CognitiveRouter
from agi_runtime.cognition.risk import RiskScorer
from agi_runtime.cognition.system1 import (
    ExpertOverrides,
    prepare_expert_overrides,
)
from agi_runtime.cognition.feedback import OutcomeRecorder
from agi_runtime.cognition.stall import (
    StallDetector,
    build_reminder as build_stall_reminder,
    detector_from_config as stall_detector_from_config,
)

try:
    import anthropic as _anthropic_lib
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


def _posture_name_from_risk(risk: float) -> str:
    """Mirror governance.posture._posture_from_risk without re-running SRG.

    Avoids a second governor.evaluate() call inside _think_async — the agent
    already has gov.risk in hand at the routing point.
    """
    if risk >= 0.35:
        return "conservative"
    if risk >= 0.15:
        return "balanced"
    return "aggressive"


@dataclass
class AgentResponse:
    """Response from the agent."""
    text: str
    decision: str
    risk: float
    tool_calls_made: int = 0
    turns_used: int = 0
    # Whether the underlying think loop completed cleanly. Outcome reporting
    # (e.g. cognition.feedback.OutcomeRecorder) reads this to decide whether
    # to credit or debit the matched skill. Failure paths (LLM error, soft
    # timeout, recovery exhausted) flip this to False.
    success: bool = True
    failure_reason: str = ""


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
        self.output_guard = OutputGuard()
        self.ale = ALEngine()
        self.identity = IdentityEngine(
            path=self.settings.memory_path,
            mission=self.settings.mission,
            style=self.settings.style,
            domain_focus=self.settings.domain_focus,
        )
        self.principals = PrincipalProfileStore()
        self.journal = Journal(self.settings.journal_path)
        self.srg_adapter = SRGAdapter(
            governor=self.governor,
            output_guard=self.output_guard,
            memory_guard=self.memory_guard,
            journal=self.journal,
        )
        self.skills = SkillManager(skill_bank_settings=self.settings.skill_bank)
        self.context_manager = ContextManager(self.settings.context)
        self.compressor = ContextCompressor()
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=60.0)
        self.supervisor = Supervisor(pause_consecutive=5, pause_rate=0.5)

        # Reliability Layer (Milestone 3)
        reliability_cfg = self.settings.reliability if isinstance(self.settings.reliability, dict) else {}
        self.reliability_enabled = bool(reliability_cfg.get("enabled", True))
        loop_thresh = int(reliability_cfg.get("loop_threshold", 3))
        self.completion_verifier = CompletionVerifier()
        self.loop_breaker = LoopBreaker(repetition_threshold=loop_thresh)
        self.recovery_manager = RecoveryManager()
        self.stop_validator = StopValidator()

        self.growth = GrowthTracker()
        self.sentiment = SentimentTracker()
        self.context_compiler = ContextCompiler()
        self.patterns = PatternDetector()
        self.max_turns = self.policy_pack.max_turns

        # Cognitive runtime — dual-system router. Defaults to observe-only,
        # so behavior is unchanged unless cognitive_runtime.enabled=True.
        cog_cfg = self.settings.cognitive_runtime if isinstance(
            self.settings.cognitive_runtime, dict
        ) else {}
        self.cognitive_router = CognitiveRouter(
            skills=self.skills,
            journal=self.journal,
            risk_scorer=RiskScorer(circuit_breaker=self.circuit_breaker),
            config=cog_cfg,
        )
        # System 2 trace store + per-agent weights are cheap to allocate
        # even when the council never fires — they own filesystem state
        # callers (e.g. tests, dashboards) may want to inspect.
        from agi_runtime.cognition.trace import ThinkingTraceStore as _TraceStore
        from agi_runtime.cognition.system2.voting import VoteWeights as _VoteWeights
        from agi_runtime.cognition.crystallize import SkillCrystallizer as _Crystallizer
        self.thinking_trace_store = _TraceStore(journal=self.journal)
        self.vote_weights = _VoteWeights()
        # Crystallization gate values come from the same config block the
        # router reads — keeps a single source of truth for thresholds.
        cryst_cfg = (
            cog_cfg.get("crystallization", {}) if isinstance(cog_cfg, dict) else {}
        )
        skill_bank = getattr(self.skills, "skill_bank", None) or getattr(
            self.skills, "bank", None
        )
        self.skill_crystallizer = _Crystallizer(
            trace_store=self.thinking_trace_store,
            skill_bank=skill_bank,
            journal=self.journal,
            min_council_successes=int(
                cryst_cfg.get("min_council_successes", 3) if isinstance(cryst_cfg, dict) else 3
            ),
            min_agent_agreement=float(
                cryst_cfg.get("min_agent_agreement", 0.66) if isinstance(cryst_cfg, dict) else 0.66
            ),
        )
        self.outcome_recorder = OutcomeRecorder(
            skills=self.skills,
            journal=self.journal,
            trace_store=self.thinking_trace_store,
            vote_weights=self.vote_weights,
            crystallizer=self.skill_crystallizer,
        )
        # Lazy — built only on the first System 2 dispatch, since it needs
        # the Anthropic client which is set later in __init__.
        self._cognitive_council = None
        # Most recent routing decision, exposed for diagnostics.
        self._last_routing_decision = None
        # Active System 1 override for the duration of one think() call.
        # Set in _think_async, cleared in the finally block.
        self._active_expert_overrides: Optional[ExpertOverrides] = None
        # Active System 2 trace for the duration of one think() call.
        self._active_council_trace = None

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
        # Set for the duration of _think_async when reliability.soft_timeout_sec > 0
        self._think_soft_deadline: Optional[float] = None

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

    def _active_channel_name(self) -> str:
        """Return a compact channel name for prompt shaping."""
        if self._active_channel is None:
            return "local"
        channel_class_name = getattr(self._active_channel.__class__, "__name__", "") or "local"
        if channel_class_name.endswith("Channel"):
            channel_class_name = channel_class_name[:-7]
        return channel_class_name.strip().lower() or "local"

    def _recent_user_messages(self, limit: int = 4) -> List[str]:
        """Return recent plain-text user messages from the current history."""
        messages: List[str] = []
        for message in self._history:
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                messages.append(content.strip())
        return messages[-limit:]

    def _is_continuation_message(self, text: str) -> bool:
        """Heuristic for short approval/continuation replies."""
        normalized = " ".join((text or "").strip().lower().split())
        if not normalized:
            return False
        exact_matches = {
            "continue",
            "go on",
            "carry on",
            "proceed",
            "do it",
            "yes",
            "yep",
            "yeah",
            "ok",
            "okay",
            "sure",
            "sounds good",
            "keep going",
        }
        if normalized in exact_matches:
            return True
        tokens = normalized.split()
        continuation_tokens = {
            "continue",
            "go",
            "on",
            "carry",
            "proceed",
            "do",
            "it",
            "yes",
            "yep",
            "yeah",
            "ok",
            "okay",
            "sure",
            "keep",
            "going",
        }
        return len(tokens) <= 3 and all(token in continuation_tokens for token in tokens)

    def _truncate_prompt_text(self, text: str, limit: int = 220) -> str:
        """Clip prompt context lines to keep the system prompt focused."""
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3] + "..."

    def _build_policy_pack_section(self) -> Optional[str]:
        """Describe the current operating posture for the model."""
        traits = ", ".join(self.policy_pack.identity_traits) if self.policy_pack.identity_traits else "none"
        lines = [
            f"Active pack: {self.policy_pack.name}.",
            f"Model tier bias: {self.policy_pack.model_tier}.",
            f"Traits to embody: {traits}.",
            f"Autonomy budget: up to {self.max_turns} turns.",
        ]
        return "\n".join(lines)

    def _build_operating_rules_section(self) -> str:
        """Core task-control rules inspired by stronger coding-agent prompts."""
        lines = [
            "- Prioritize the latest concrete user objective over adjacent ideas.",
            "- Short replies like 'continue', 'yes', or 'do it' usually mean continue the active task, not start a new one.",
            "- Before pivoting topics, verify that the new work is explicitly requested or required to finish the current task.",
            "- For non-trivial work, internally break the task into a few concrete steps and execute them in order.",
            "- Use tools to gather evidence, make progress, and verify outcomes instead of narrating hypotheticals.",
            "- If blocked, ask one focused question or report the blocker plainly rather than drifting.",
        ]
        return "\n".join(lines)

    def _build_response_contract_section(self) -> str:
        """How the assistant should behave while work is in progress."""
        channel_name = self._active_channel_name()
        lines = [
            "- Acknowledge the user's intent quickly before long-running work.",
            "- During long tasks, provide brief progress updates about the current action or blocker instead of going silent.",
            "- Keep progress updates tied to the active task; do not improvise new objectives in those updates.",
            "- Separate visible status updates from hidden reasoning; never expose chain-of-thought.",
            "- Final answers should state what was completed, what is still blocked, and what happens next.",
        ]
        if channel_name in {"voice", "telegram", "discord"}:
            lines.insert(
                1,
                f"- This turn originates from the {channel_name} channel, so latency is user-visible: keep acknowledgements and progress updates short and timely.",
            )
        return "\n".join(lines)

    def _build_active_task_section(self) -> Optional[str]:
        """Summarize the live objective so the model stays on the same task."""
        recent_user_messages = self._recent_user_messages(limit=5)
        if not recent_user_messages:
            return None

        latest_message = recent_user_messages[-1]
        anchored_objective = latest_message
        continuation_note = ""
        if self._is_continuation_message(latest_message):
            for candidate in reversed(recent_user_messages[:-1]):
                if not self._is_continuation_message(candidate):
                    anchored_objective = candidate
                    continuation_note = (
                        "Latest user message is a continuation or approval. Treat the current objective as the anchored request below unless the user explicitly changes topic."
                    )
                    break

        recent_requests = " | ".join(self._truncate_prompt_text(message, limit=120) for message in recent_user_messages)
        lines = [
            f"Principal: {self.current_profile_principal()}.",
            f"Channel: {self._active_channel_name()}.",
            f"Current objective: {self._truncate_prompt_text(anchored_objective)}",
            f"Latest user message: {self._truncate_prompt_text(latest_message)}",
            f"Recent user requests: {recent_requests}",
            "Stay on this objective until it is complete, blocked, or explicitly superseded.",
        ]
        if continuation_note:
            lines.append(continuation_note)
        return "\n".join(lines)

    def _build_sub_agent_system_prompt(self, goal: str, context: str, max_turns: int) -> str:
        """Prompt for delegated/background execution work."""
        lines = [
            f"You are an execution sub-agent working for {self.identity.state.name}.",
            "You are not the primary conversational assistant.",
            "Complete exactly the delegated goal and return a compact execution summary.",
            "",
            "<execution-contract>",
            "- Stay narrowly focused on the delegated goal.",
            "- Do not start adjacent work or reframe the task.",
            "- Use tools when needed, but keep the path efficient and evidence-based.",
            "- If blocked, state the blocker clearly and stop instead of improvising.",
            "- Do not add personality filler, onboarding, or general chat.",
            "- Final output format: status, concrete result, blockers (if any), next recommended step.",
            f"- Turn budget: at most {min(max_turns, 15)} turns.",
            "</execution-contract>",
            "",
            "<delegated-task>",
            f"Goal: {self._truncate_prompt_text(goal or 'Complete the delegated task.', limit=300)}",
        ]
        if context.strip():
            lines.append(f"Context: {self._truncate_prompt_text(context, limit=500)}")
        lines.append("</delegated-task>")
        return "\n".join(lines)

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
        import importlib.util

        try:
            has_genai = importlib.util.find_spec("google.genai") is not None
        except ModuleNotFoundError:
            has_genai = False

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

        policy_pack_section = self._build_policy_pack_section()
        if policy_pack_section:
            parts.append("")
            parts.append("<policy-pack>")
            parts.append(policy_pack_section)
            parts.append("</policy-pack>")

        parts.append("")
        parts.append("<operating-rules>")
        parts.append(self._build_operating_rules_section())
        parts.append("</operating-rules>")

        parts.append("")
        parts.append("<response-contract>")
        parts.append(self._build_response_contract_section())
        parts.append("</response-contract>")

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

        # Grounded location — populated by the onboarding wizard. When the
        # user has set a city, weather / "near me" / local-services queries
        # should not need a clarifying web_search loop.
        principal_city = (getattr(principal_state, "city", "") or "").strip()
        if principal_city:
            parts.append("")
            parts.append("<location-context>")
            parts.append(
                f"User's reported city: {principal_city}. Treat this as the "
                "default location for weather, local time, 'near me', and "
                "place-based queries unless the user names a different place."
            )
            parts.append("</location-context>")

        active_task = self._build_active_task_section()
        if active_task:
            parts.append("")
            parts.append("<active-task>")
            parts.append(active_task)
            parts.append("</active-task>")

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

        sb_cfg = self.settings.skill_bank if isinstance(self.settings.skill_bank, dict) else {}
        if sb_cfg.get("enabled", True):
            recent = self._recent_user_messages(1)
            if recent:
                hints = self.skills.find_matching_skill_semantic(recent[-1], top_k=3)
                if hints:
                    lines = ["Semantic skill hints (use skill_invoke when appropriate):"]
                    for h in hints:
                        lines.append(
                            f"  - {h.skill.name} (relevance {h.relevance:.2f}): "
                            f"{h.skill.description[:160]}"
                        )
                    parts.append("")
                    parts.append("<skill-hints>")
                    parts.append("\n".join(lines))
                    parts.append("</skill-hints>")

        # Inject memory context (optionally rolled / budgeted)
        memory_context = self._get_memory_context()
        if memory_context:
            parts.append("")
            parts.append("<memory-context>")
            if self._context_managed():
                qh = " ".join(self._recent_user_messages(3)) or "memory"
                ctx_cfg = self.settings.context if isinstance(self.settings.context, dict) else {}
                mem_budget = min(6000, max(500, int(ctx_cfg.get("max_budget_tokens", 120000)) // 24))
                rolled = self.context_manager.build_supplement(
                    query_hint=qh,
                    segments=[
                        ContextSegment(
                            "memory",
                            9,
                            memory_context,
                            max_tokens=mem_budget,
                            relevance_score=0.75,
                        ),
                    ],
                )
                parts.append(rolled or memory_context)
            else:
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
        if tool_name.startswith("browser_") and not self._browser_tools_allowed():
            return False
        return True

    def _browser_tools_allowed(self) -> bool:
        cfg = self.settings.browser if isinstance(self.settings.browser, dict) else {}
        if not cfg.get("enabled", True):
            return False
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    def _context_managed(self) -> bool:
        cfg = self.settings.context if isinstance(self.settings.context, dict) else {}
        return bool(cfg.get("managed", True))

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

        sub_system = self._build_sub_agent_system_prompt(
            goal=goal,
            context=context,
            max_turns=max_turns,
        )

        sub_history = [{"role": "user", "content": f"Task: {goal}\n\nContext: {context}"}]
        sub_max = min(max_turns, 15)
        results_summary = []

        for turn in range(sub_max):
            try:
                on_stream = self.on_stream
                with self._claude.messages.stream(
                    model="claude-haiku-4-5-20251001",  # Use fast model for sub-agents
                    max_tokens=4096,
                    system=sub_system,
                    tools=tools,
                    messages=sub_history,
                ) as stream:
                    response = self._drain_anthropic_stream(stream, on_stream)
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

    # ── Anthropic streaming helper ─────────────────────────────

    def _drain_anthropic_stream(self, stream, on_stream):
        """Drain a ``messages.stream()`` context, emitting deltas via ``on_stream``.

        ``on_stream`` is invoked with each text delta string as it arrives.
        It is also called with ``None`` at the start of every tool_use block to
        signal a segment break (so channels can finalize the in-flight message
        and start a fresh one for the next reasoning chunk). All callback
        exceptions are journaled and swallowed so they can never break the
        underlying SDK stream.

        Returns the final ``Message`` (same shape as ``messages.create()``).
        """
        for event in stream:
            try:
                etype = getattr(event, "type", "")
                if etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta is not None and getattr(delta, "type", "") == "text_delta":
                        txt = getattr(delta, "text", "") or ""
                        if on_stream and txt:
                            try:
                                on_stream(txt)
                            except Exception as exc:
                                self.journal.write(
                                    "on_stream_error", {"error": str(exc)[:300]}
                                )
                elif etype == "content_block_start":
                    blk = getattr(event, "content_block", None)
                    if blk is not None and getattr(blk, "type", "") == "tool_use":
                        if on_stream:
                            try:
                                on_stream(None)
                            except Exception as exc:
                                self.journal.write(
                                    "on_stream_error", {"error": str(exc)[:300]}
                                )
            except Exception as exc:
                # Never let event parsing kill the stream loop.
                self.journal.write("stream_event_error", {"error": str(exc)[:300]})
        return stream.get_final_message()

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

        # 3b. Cognitive routing.
        # Observe-only by default; once cognitive_runtime.enabled=True and
        # mode is "system1_only" or "dual", an enforced System 1 verdict
        # routes through Haiku via _active_expert_overrides. In "dual" mode
        # an enforced System 2 verdict invokes the AgentCouncil before the
        # main loop runs.
        try:
            posture_name = _posture_name_from_risk(float(gov.risk or 0.0))
            self._last_routing_decision = self.cognitive_router.decide(
                user_input, gov, posture_name=posture_name,
            )
            self._active_expert_overrides = prepare_expert_overrides(
                self._last_routing_decision
            )
        except Exception:
            # Routing must never break the agent.
            self._last_routing_decision = None
            self._active_expert_overrides = None
        self._active_council_trace = None
        council_outcome = await self._maybe_run_council(user_input, gov)

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
        if self._active_expert_overrides is not None:
            system_prompt = (
                system_prompt + "\n\n" + self._active_expert_overrides.prompt_addendum
            )

        if council_outcome is not None:
            addendum = self._council_addendum(council_outcome)
            if addendum:
                system_prompt = system_prompt + addendum

        # Surface task-scoped tool hints from PatternDetector so the agent
        # sees "last time you asked about Instagram followers you used the
        # browser" before it grinds through ad-hoc tool calls. Cheap signal,
        # high payoff for the floundering-on-familiar-topic failure mode.
        try:
            scoped = self.patterns.get_tools_for_topic(user_input, top_n=3, min_uses=2)
        except Exception:
            scoped = []
        if scoped:
            hint_lines = ", ".join(f"{t} ({c}×)" for t, c in scoped)
            system_prompt = (
                system_prompt
                + "\n\n<task-pattern-hint>\n"
                + f"Past tasks with overlapping topics most often used: {hint_lines}.\n"
                + "Reach for these tools first if they fit the goal — don't reinvent the path.\n"
                + "</task-pattern-hint>"
            )

        rel_cfg = self.settings.reliability if isinstance(self.settings.reliability, dict) else {}
        to_sec = int(rel_cfg.get("soft_timeout_sec", 0) or 0)
        self._think_soft_deadline = (time.time() + float(to_sec)) if to_sec > 0 else None
        expert = self._active_expert_overrides
        council_trace = self._active_council_trace
        try:
            if self._llm_provider == "anthropic":
                response = await self._think_async_claude(user_input, gov, tools, system_prompt, principal_id)
            else:
                response = await self._think_async_gemini(user_input, gov, tools, system_prompt, principal_id)
            if expert is not None:
                self.outcome_recorder.record_system1(
                    expert,
                    success=response.success,
                    failure_reason=response.failure_reason,
                )
                self.cognitive_router.observe_outcome(expert.fingerprint)
            if council_trace is not None:
                self.outcome_recorder.record_system2(
                    council_trace,
                    success=response.success,
                    failure_reason=response.failure_reason,
                )
                self.cognitive_router.observe_outcome(council_trace.fingerprint)
            return response
        finally:
            self._think_soft_deadline = None
            self._active_expert_overrides = None
            self._active_council_trace = None

    def _tail_history_for_synthesis(self, max_messages: int = 48) -> List[dict]:
        """Last N history entries to stay within model limits while keeping recent tool context."""
        h = self._history
        if not h:
            return []
        if len(h) <= max_messages:
            return list(h)
        return list(h[-max_messages:])

    def _synthesis_nudge_user_content(self, user_input: str) -> str:
        return (
            "[Tool budget exhausted — you must not use tools.]\n"
            "Answer the user in clear prose only, using information already present in this "
            "conversation (search results, fetches, prior reasoning). Be concise. If the thread does "
            "not contain enough reliable information, say so honestly in one or two sentences.\n\n"
            f"User's request:\n{user_input}"
        )

    async def _synthesize_claude_text_only(self, user_input: str, system_prompt: str) -> str:
        """One non-tool call to produce a user-visible answer when the main loop hit max turns."""
        if not self._claude:
            return ""
        messages = self._tail_history_for_synthesis(48)
        messages = messages + [
            {"role": "user", "content": self._synthesis_nudge_user_content(user_input)},
        ]
        try:
            on_stream = self.on_stream
            with self._claude.messages.stream(
                model=self._select_model(user_input),
                max_tokens=min(8192, self.MAX_OUTPUT_TOKENS),
                system=system_prompt,
                messages=messages,
            ) as stream:
                response = self._drain_anthropic_stream(stream, on_stream)
        except Exception as e:
            self.journal.write("synthesis_after_max_turns", {"ok": False, "provider": "anthropic", "error": str(e)[:500]})
            return ""

        text_parts: List[str] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        out = "\n".join(text_parts).strip()
        self.journal.write("synthesis_after_max_turns", {"ok": bool(out), "provider": "anthropic", "chars": len(out)})
        return out

    def _history_plaintext_for_gemini_synthesis(self, max_total: int = 200_000) -> str:
        """Flatten Claude-style _history into plain text for a no-tools Gemini call.

        Re-using native Gemini ``contents`` with function_call / function_response parts
        alongside a config without tools causes 400 Bad Request; a single user blob avoids that.
        """
        chunks: List[str] = []
        for m in self._history:
            role = (m.get("role") or "?").strip().upper()
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                chunks.append(f"=== {role} ===\n{c.strip()}\n")
                continue
            if isinstance(c, list):
                segs: List[str] = []
                for item in c:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") != "tool_result":
                        continue
                    tid = item.get("tool_use_id", "")
                    body = item.get("content", "")
                    if not isinstance(body, str):
                        body = str(body)
                    cap = 12_000
                    if len(body) > cap:
                        body = body[:cap] + "\n…(tool output truncated)"
                    segs.append(f"[tool_result {tid}]\n{body}")
                if segs:
                    chunks.append(f"=== {role} (TOOL OUTPUTS) ===\n" + "\n\n".join(segs) + "\n")
        blob = "\n".join(chunks).strip()
        if len(blob) <= max_total:
            return blob
        marker = "\n…[earlier session transcript omitted; tail follows]\n"
        tail_len = max_total - len(marker)
        if tail_len < 1000:
            return blob[-max_total:]
        return marker + blob[-tail_len:]

    async def _synthesize_gemini_text_only(self, user_input: str, system_prompt: str, model_id: str) -> str:
        """One generate_content call without function-calling when the main loop hit max turns."""
        if not self._gemini_client:
            return ""
        from google.genai import types as gtypes
        from agi_runtime.llm.gemini_adapter import response_text_and_calls, genai_types_available
        from agi_runtime.models.gemini_router import GEMINI_FALLBACK_STABLE

        if not genai_types_available():
            return ""

        transcript = self._history_plaintext_for_gemini_synthesis()
        if not transcript.strip():
            transcript = "(No transcript text captured in this session.)"
        preamble = (
            "The following is a plain-text transcript of an assistant session that reached its "
            "tool-call turn limit. Answer the user's request using only this material; do not "
            "invent tool runs. If the transcript lacks enough to answer, say so briefly.\n\n"
        )
        package = preamble + transcript + "\n\n---\n" + self._synthesis_nudge_user_content(user_input)
        if len(package) > 900_000:
            package = package[:900_000] + "\n…(package truncated)"

        sys_inst = system_prompt if len(system_prompt) <= 32000 else system_prompt[:32000] + "\n…(truncated)"
        contents_syn = [
            gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=package)]),
        ]
        try:
            config = gtypes.GenerateContentConfig(
                system_instruction=sys_inst,
                max_output_tokens=min(8192, self.MAX_OUTPUT_TOKENS),
                automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True),
            )
        except Exception:
            try:
                config = gtypes.GenerateContentConfig(
                    system_instruction=sys_inst,
                    max_output_tokens=min(8192, self.MAX_OUTPUT_TOKENS),
                )
            except Exception:
                return ""

        async def _one(mid: str):
            return await self._gemini_client.models.generate_content(
                model=mid,
                contents=contents_syn,
                config=config,
            )

        response = None
        models_to_try: List[str] = []
        for m in (model_id, GEMINI_FALLBACK_STABLE):
            if m and m not in models_to_try:
                models_to_try.append(m)
        for mid in models_to_try:
            try:
                response = await _one(mid)
                break
            except Exception as e:
                self.journal.write(
                    "synthesis_after_max_turns",
                    {"ok": False, "provider": "google", "model": mid, "error": str(e)[:500]},
                )
        if response is None:
            return ""

        plain, raw_calls = response_text_and_calls(response)
        if raw_calls:
            self.journal.write("synthesis_after_max_turns", {"ok": False, "provider": "google", "error": "unexpected_function_calls"})
            return (plain or "").strip()
        out = (plain or "").strip()
        self.journal.write("synthesis_after_max_turns", {"ok": bool(out), "provider": "google", "chars": len(out)})
        return out

    def _message_after_max_turns(self, user_input: str, total_tool_calls: int, turns_used: int) -> str:
        return (
            f"I've used all {self.max_turns} turns working on your request. "
            f"Made {total_tool_calls} tool call(s) across {turns_used} turn(s), so I could not finish "
            f"in the normal loop. Your question was: {user_input[:200]!r}."
        )

    async def _think_async_claude(
        self, user_input: str, gov: GovernanceResult, tools: List[dict], system_prompt: str, principal_id: str
    ) -> AgentResponse:
        """Anthropic Messages API tool loop."""
        total_tool_calls = 0
        turns_used = 0

        if self.reliability_enabled:
            self.loop_breaker.reset(principal_id)
            self.recovery_manager.reset(principal_id)

        # Per-call stall detector. Catches "N silent tool-only turns" so we
        # don't burn 40 turns on the kind of floundering that triggered
        # this whole effort.
        cog_cfg = (
            self.settings.cognitive_runtime
            if isinstance(self.settings.cognitive_runtime, dict)
            else {}
        )
        stall_cfg = cog_cfg.get("stall") if isinstance(cog_cfg, dict) else None
        stall_enabled = bool((stall_cfg or {}).get("enabled", True))
        stall_detector = stall_detector_from_config(cog_cfg)

        for turn in range(self.max_turns):
            turns_used = turn + 1

            if self._think_soft_deadline is not None and time.time() >= self._think_soft_deadline:
                msg = (
                    "Stopped: reached the configured think-time limit "
                    "(set `reliability.soft_timeout_sec` in helloagi.json; use 0 to disable)."
                )
                self.journal.write(
                    "think_soft_timeout",
                    {"turns": turns_used, "tool_calls": total_tool_calls},
                )
                return AgentResponse(
                    text=msg,
                    decision=gov.decision,
                    risk=gov.risk,
                    tool_calls_made=total_tool_calls,
                    turns_used=turns_used,
                    success=False,
                    failure_reason="soft_timeout",
                )

            if self.reliability_enabled:
                signal = self.loop_breaker.check(principal_id)
                if signal.detected:
                    if signal.loop_type == "recovery-exhausted":
                        self.journal.write("recovery_exhausted_loop_breaker", {"principal_id": principal_id})
                        return AgentResponse(
                            text=self.recovery_manager.exhausted_user_message(),
                            decision=gov.decision,
                            risk=gov.risk,
                            tool_calls_made=total_tool_calls,
                            turns_used=turns_used,
                            success=False,
                            failure_reason="recovery_exhausted",
                        )
                    action = self.recovery_manager.suggest(
                        loop_type=signal.loop_type, session_id=principal_id
                    )
                    if action.exhausted:
                        self.journal.write("recovery_exhausted", {})
                        return AgentResponse(
                            text=self.recovery_manager.exhausted_user_message(),
                            decision=gov.decision, risk=gov.risk,
                            tool_calls_made=total_tool_calls, turns_used=turns_used,
                            success=False, failure_reason="recovery_exhausted",
                        )
                    else:
                        self._history.append({"role": "user", "content": action.instruction})
                        self.journal.write("loop_broken", {"strategy": action.strategy})

            try:
                on_stream = self.on_stream
                with self._claude.messages.stream(
                    model=self._select_model(user_input),
                    max_tokens=self.MAX_OUTPUT_TOKENS,
                    system=system_prompt,
                    tools=tools,
                    messages=self._history,
                ) as stream:
                    response = self._drain_anthropic_stream(stream, on_stream)
            except Exception as e:
                error_msg = f"LLM call failed: {e}"
                self.journal.write("llm_error", {"error": str(e), "turn": turn})
                return AgentResponse(
                    text=error_msg, decision=gov.decision, risk=gov.risk,
                    tool_calls_made=total_tool_calls, turns_used=turns_used,
                    success=False, failure_reason=f"llm_error:{type(e).__name__}",
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

            # Stall observation — record this turn's narration vs. tool-call
            # ratio so we can detect "the agent is just spamming tools."
            stall_detector.observe(
                text_chars=len("\n".join(text_parts)),
                tool_call_count=len(tool_calls),
            )

            if not tool_calls:
                final_text = "\n".join(text_parts)

                if self.reliability_enabled:
                    tools_used_names = [tc["tool"] for tc in self._session_tool_calls]
                    comp_check = self.completion_verifier.verify(
                        final_text, tool_calls_made=total_tool_calls, tools_used=tools_used_names
                    )
                    if comp_check.status == "phantom":
                        self.journal.write("phantom_completion", {"reasons": comp_check.reasons})
                        try:
                            self.srg_adapter.logger.log_generic(
                                gate="completion",
                                decision="require_more_evidence",
                                reasons=list(comp_check.reasons),
                                principal_id=principal_id,
                                action_summary="phantom_completion",
                            )
                        except Exception:
                            pass
                        self._history.append({"role": "user", "content": comp_check.suggestion})
                        continue

                    stop_check = self.stop_validator.validate(
                        final_text, tool_calls_made=total_tool_calls,
                        tools_used=tools_used_names, is_multi_step=(total_tool_calls > 1)
                    )
                    if stop_check.decision == "continue":
                        self.journal.write("stop_validation_failed", {"reasons": stop_check.reasons})
                        try:
                            self.srg_adapter.logger.log_generic(
                                gate="completion",
                                decision="require_more_evidence",
                                reasons=list(stop_check.reasons),
                                principal_id=principal_id,
                                action_summary="stop_validation_continue",
                            )
                        except Exception:
                            pass
                        self._history.append({"role": "user", "content": stop_check.disclaimer})
                        continue
                    elif stop_check.decision == "disclaim" and stop_check.disclaimer:
                        final_text += stop_check.disclaimer

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

                if self.reliability_enabled:
                    self.loop_breaker.record_call(
                        tool=tc.name,
                        args=tc.input,
                        error=result.to_content()[:200] if not result.ok else "",
                        response="",
                        session_id=principal_id
                    )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result.to_content(),
                })

                if self.on_tool_end:
                    self.on_tool_end(tc.name, result.ok, result.to_content()[:200])

            self._history.append({"role": "user", "content": tool_results})

            # Stall escalation — if we've had N silent tool-only turns in a
            # row, inject a warning user message asking the LLM to summarize
            # what it's tried and consider switching approach. Fire-once per
            # streak; resets when the agent narrates again.
            if stall_enabled:
                stall_signal = stall_detector.check()
                if stall_signal.detected:
                    self.journal.write("system.stall_detected", {
                        "tool_calls": stall_signal.total_tool_calls,
                        "silent_turns": stall_signal.consecutive_silent_turns,
                        "turn": turns_used,
                        "reason": stall_signal.reason,
                    })
                    self._history.append({
                        "role": "user",
                        "content": build_stall_reminder(stall_signal),
                    })
                    stall_detector.acknowledge()

            if self.compressor.needs_compression(self._history):
                self._history = await self.compressor.compress(self._history)
                self.journal.write("context_compressed", {"new_length": len(self._history)})

        self.journal.write("max_turns_reached", {"tool_calls": total_tool_calls, "max_turns": self.max_turns})
        backup = self._message_after_max_turns(user_input, total_tool_calls, turns_used)
        summary = await self._synthesize_claude_text_only(user_input, system_prompt)
        if summary:
            final_text = (
                f"{summary}\n\n"
                f"(Note: this answer was synthesized after reaching the {self.max_turns}-turn tool budget.)"
            )
        else:
            final_text = (
                f"{backup}\n\n"
                f"I could not generate a final summary. Try a narrower question, or rephrase and ask again."
            )
        # Reaching max_turns without a tool-free synthesis turn is a failure
        # signal even if we managed to stitch together a summary. The user's
        # follower-count complaint is the canonical example: 40 turns spent
        # floundering instead of "this is browser work — open the profile."
        return AgentResponse(
            text=final_text, decision=gov.decision, risk=gov.risk,
            tool_calls_made=total_tool_calls, turns_used=turns_used,
            success=bool(summary),
            failure_reason="max_turns_reached" if not summary else "",
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
        self, user_input: str, gov: GovernanceResult, tools: List[dict], system_prompt: str, principal_id: str
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

        if self.reliability_enabled:
            self.loop_breaker.reset(principal_id)
            self.recovery_manager.reset(principal_id)

        for turn in range(self.max_turns):
            turns_used = turn + 1

            if self._think_soft_deadline is not None and time.time() >= self._think_soft_deadline:
                msg = (
                    "Stopped: reached the configured think-time limit "
                    "(set `reliability.soft_timeout_sec` in helloagi.json; use 0 to disable)."
                )
                self.journal.write(
                    "think_soft_timeout",
                    {"turns": turns_used, "tool_calls": total_tool_calls, "provider": "google"},
                )
                return AgentResponse(
                    text=msg,
                    decision=gov.decision,
                    risk=gov.risk,
                    tool_calls_made=total_tool_calls,
                    turns_used=turns_used,
                )

            if self.reliability_enabled:
                signal = self.loop_breaker.check(principal_id)
                if signal.detected:
                    if signal.loop_type == "recovery-exhausted":
                        self.journal.write("recovery_exhausted_loop_breaker", {"principal_id": principal_id})
                        return AgentResponse(
                            text=self.recovery_manager.exhausted_user_message(),
                            decision=gov.decision,
                            risk=gov.risk,
                            tool_calls_made=total_tool_calls,
                            turns_used=turns_used,
                            success=False,
                            failure_reason="recovery_exhausted",
                        )
                    action = self.recovery_manager.suggest(
                        loop_type=signal.loop_type, session_id=principal_id
                    )
                    if action.exhausted:
                        self.journal.write("recovery_exhausted", {})
                        return AgentResponse(
                            text=self.recovery_manager.exhausted_user_message(),
                            decision=gov.decision, risk=gov.risk,
                            tool_calls_made=total_tool_calls, turns_used=turns_used,
                            success=False, failure_reason="recovery_exhausted",
                        )
                    else:
                        self._history.append({"role": "user", "content": action.instruction})
                        self.journal.write("loop_broken", {"strategy": action.strategy})
                        
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

                if self.reliability_enabled:
                    tools_used_names = [tc["tool"] for tc in self._session_tool_calls]
                    comp_check = self.completion_verifier.verify(
                        final_text, tool_calls_made=total_tool_calls, tools_used=tools_used_names
                    )
                    if comp_check.status == "phantom":
                        self.journal.write("phantom_completion", {"reasons": comp_check.reasons})
                        try:
                            self.srg_adapter.logger.log_generic(
                                gate="completion",
                                decision="require_more_evidence",
                                reasons=list(comp_check.reasons),
                                principal_id=principal_id,
                                action_summary="phantom_completion",
                            )
                        except Exception:
                            pass
                        self._history.append({"role": "user", "content": comp_check.suggestion})
                        continue

                    stop_check = self.stop_validator.validate(
                        final_text, tool_calls_made=total_tool_calls,
                        tools_used=tools_used_names, is_multi_step=(total_tool_calls > 1)
                    )
                    if stop_check.decision == "continue":
                        self.journal.write("stop_validation_failed", {"reasons": stop_check.reasons})
                        try:
                            self.srg_adapter.logger.log_generic(
                                gate="completion",
                                decision="require_more_evidence",
                                reasons=list(stop_check.reasons),
                                principal_id=principal_id,
                                action_summary="stop_validation_continue",
                            )
                        except Exception:
                            pass
                        self._history.append({"role": "user", "content": stop_check.disclaimer})
                        continue
                    elif stop_check.decision == "disclaim" and stop_check.disclaimer:
                        final_text += stop_check.disclaimer

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

                if self.reliability_enabled:
                    self.loop_breaker.record_call(
                        tool=tc.name,
                        args=tc.input,
                        error=out[:200] if not result.ok else "",
                        response="",
                        session_id=principal_id
                    )
                tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": out})
                func_response_parts.append(gtypes.Part.from_function_response(name=tc.name, response={"result": out}))
                if self.on_tool_end:
                    self.on_tool_end(tc.name, result.ok, result.to_content()[:200])

            self._history.append({"role": "user", "content": tool_results})
            contents.append(gtypes.Content(role="tool", parts=func_response_parts))

            if self.compressor.needs_compression(self._history):
                self._history = await self.compressor.compress(self._history)
                self.journal.write("context_compressed", {"new_length": len(self._history)})

        self.journal.write("max_turns_reached", {"tool_calls": total_tool_calls, "max_turns": self.max_turns})
        backup = self._message_after_max_turns(user_input, total_tool_calls, turns_used)
        summary = await self._synthesize_gemini_text_only(user_input, system_prompt, model_id)
        if summary:
            final_text = (
                f"{summary}\n\n"
                f"(Note: this answer was synthesized after reaching the {self.max_turns}-turn tool budget.)"
            )
        else:
            final_text = (
                f"{backup}\n\n"
                f"I could not generate a final summary. Try a narrower question, or rephrase and ask again."
            )
        return AgentResponse(
            text=final_text, decision=gov.decision, risk=gov.risk,
            tool_calls_made=total_tool_calls, turns_used=turns_used,
        )

    # ── Helpers ────────────────────────────────────────────────

    def create_tri_loop(self):
        """SRG-governed TriLoop sharing this agent's policy, journal, and skill bank."""
        from agi_runtime.autonomy.tri_loop import TriLoop

        sb = self.settings.skill_bank if isinstance(self.settings.skill_bank, dict) else {}
        auto = bool(sb.get("auto_extract", True)) and bool(sb.get("enabled", True))
        return TriLoop(
            self,
            governor=self.governor,
            output_guard=self.output_guard,
            journal=self.journal,
            skill_bank=self.skills.skill_bank,
            skill_governance_adapter=self.srg_adapter,
            skill_auto_extract=auto,
        )

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
            browser_enabled=self._browser_tools_allowed(),
            browser_settings=dict(self.settings.browser)
            if isinstance(self.settings.browser, dict)
            else {},
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
        """Select the appropriate Claude model based on task complexity.

        When an enforced System 1 override is active for this think(), force
        Haiku regardless of keyword heuristics — that's the whole point of
        Expert Mode.
        """
        if self._active_expert_overrides is not None:
            return self._active_expert_overrides.model_id
        from agi_runtime.models.router import ModelRouter
        router = ModelRouter()
        decision = router.route(user_input)
        return decision.model

    def _ensure_cognitive_council(self):
        """Build the Agent Council on first use.

        Returns the council or None if it can't be built (no Claude client,
        configuration disabled, instantiation failed). Callers must handle
        ``None`` — the agent must keep working when the council can't run.
        """
        if self._cognitive_council is not None:
            return self._cognitive_council
        if self._claude is None:
            return None
        try:
            from agi_runtime.cognition.system2 import (
                AgentCouncil,
                make_default_roster,
            )
            cog_cfg = (
                self.settings.cognitive_runtime
                if isinstance(self.settings.cognitive_runtime, dict)
                else {}
            )
            council_cfg = cog_cfg.get("council") if isinstance(cog_cfg, dict) else None
            council_cfg = council_cfg or {}
            agents = make_default_roster(client=self._claude)
            self._cognitive_council = AgentCouncil(
                agents=agents,
                weights=self.vote_weights,
                trace_store=self.thinking_trace_store,
                max_rounds=int(council_cfg.get("max_rounds", 2) or 2),
                journal=self.journal,
            )
            return self._cognitive_council
        except Exception as e:
            self.journal.write("council.build_failed", {"error": str(e)[:200]})
            return None

    async def _maybe_run_council(
        self, user_input: str, gov: GovernanceResult
    ):
        """If routing says System 2 in dual mode, run the council.

        Returns the ``CouncilOutcome`` or None. Stores the trace on
        ``self._active_council_trace`` so the post-loop hook can record
        the verified outcome.
        """
        decision = self._last_routing_decision
        if decision is None or not getattr(decision, "enforced", False):
            return None
        if getattr(decision, "system", "") != "system2":
            return None
        # Council only fires in dual mode — system1_only routes system2
        # decisions back through the default loop without deliberation.
        if getattr(decision, "mode", "") != "dual":
            return None
        council = self._ensure_cognitive_council()
        if council is None:
            return None
        try:
            outcome = council.deliberate(
                user_input=user_input,
                fingerprint=getattr(decision, "fingerprint", "") or "",
                srg_decision={
                    "decision": gov.decision,
                    "risk": gov.risk,
                    "reasons": list(getattr(gov, "reasons", []) or []),
                },
            )
        except Exception as e:
            self.journal.write("council.deliberate_failed", {"error": str(e)[:200]})
            return None
        self._active_council_trace = outcome.trace
        return outcome

    def _council_addendum(self, outcome) -> str:
        """Format the council's decision as a system-prompt block."""
        decision = (outcome.final_decision or "").strip()
        summary = (outcome.reasoning_summary or "").strip()
        if not decision or decision == "no_decision":
            return ""
        return (
            "\n\n<council-decision>\n"
            "A reasoning council deliberated on this task. Their conclusion:\n"
            f"  Decision: {decision}\n"
            f"  Reasoning: {summary}\n"
            "Treat this as senior guidance — execute it with the available tools "
            "unless you have a strong, specific reason to deviate. Do not "
            "re-debate the choice; the council already did.\n"
            "</council-decision>"
        )

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
