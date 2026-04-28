"""Skill Extractor — extracts SkillContracts from successful TriLoop traces.

When a TriLoop run completes with status="passed", the extractor analyzes
the successful plan and builds a SkillContract candidate.  The candidate
is SRG-governed before being stored.
"""

from __future__ import annotations

import time
from typing import Optional

from agi_runtime.skills.skill_schema import SkillContract


class SkillExtractor:
    """Extracts reusable skills from successful autonomous task completions."""

    # Minimum steps to consider a task worth extracting as a skill
    MIN_STEPS = 2
    # Maximum steps — overly complex skills are fragile
    MAX_STEPS = 15

    def extract_from_trace(
        self,
        goal: str,
        plan_steps: list,
        plan_reasoning: str = "",
        task_id: str = "",
        verify_summary: str = "",
    ) -> Optional[SkillContract]:
        """Build a SkillContract candidate from a successful task trace.

        Parameters
        ----------
        goal : str
            The original task goal.
        plan_steps : list
            PlanStep-like objects with .action, .tool, .tool_input, .result, .status.
        plan_reasoning : str
            The planner's reasoning for the approach.
        task_id : str
            ID of the source task (for provenance).
        verify_summary : str
            Verifier's summary of the outcome.

        Returns
        -------
        SkillContract or None
            A candidate skill, or None if the trace isn't suitable.
        """
        if not plan_steps:
            return None
        if len(plan_steps) < self.MIN_STEPS:
            return None
        if len(plan_steps) > self.MAX_STEPS:
            return None

        # Only extract from fully-completed steps
        done_steps = [s for s in plan_steps if getattr(s, "status", "") == "done"]
        if len(done_steps) < self.MIN_STEPS:
            return None

        # Derive skill name from goal
        name = self._derive_name(goal)

        # Collect tools used
        tools = list(dict.fromkeys(
            getattr(s, "tool", "") for s in done_steps if getattr(s, "tool", "")
        ))

        # Build execution steps
        execution_steps = [
            getattr(s, "action", str(s)) for s in done_steps
        ]

        # Build success criteria from verifier
        success_criteria = []
        if verify_summary:
            success_criteria.append(verify_summary)
        success_criteria.append(f"All {len(done_steps)} steps complete successfully")

        # Derive task type from tools
        task_type = self._infer_task_type(tools)

        skill = SkillContract(
            name=name,
            description=f"Learned skill for: {goal[:200]}",
            task_type=task_type,
            preconditions=[f"Task matches: {goal[:100]}"],
            execution_steps=execution_steps,
            tools_required=tools,
            success_criteria=success_criteria,
            triggers=self._extract_triggers(goal),
            tags=self._extract_tags(goal, tools),
            created_from_task_id=task_id,
            status="candidate",
            confidence_score=0.6,  # Initial confidence for extracted skills
        )
        skill.compute_risk_level()
        return skill

    def extract_from_council_trace(
        self,
        trace,
        *,
        agreement: Optional[float] = None,
    ) -> Optional[SkillContract]:
        """Build a SkillContract candidate from a successful council trace.

        Phase 4 promotion path — System 2 trains System 1. We pull:
          - the synthesizer's ``final_decision`` as the canonical
            execution recipe
          - the union of all agents' ``suggested_tools`` as
            ``tools_required``
          - the council's ``reasoning_summary`` as the success criterion
          - the trace's ``fingerprint`` so the next router lookup hits
            this skill in O(1)
          - ``council_origin_trace_id`` as provenance

        ``agreement`` (0-1) seeds the initial confidence score: a 100%
        consensus run gets a higher floor than a tie-broken one. Falls
        back to a default if not provided.

        Returns None if the trace is empty or the decision is not usable
        (no rounds, ``no_decision``, or no recovered tool list).
        """
        if trace is None:
            return None
        rounds = list(getattr(trace, "rounds", []) or [])
        decision = (getattr(trace, "final_decision", "") or "").strip()
        if not rounds or not decision or decision == "no_decision":
            return None

        # Pull tool hints from every agent in every round; dedupe in order.
        tools = self._council_tools(rounds)

        execution_steps = self._council_steps(decision)
        if len(execution_steps) < 1:
            return None

        goal = (getattr(trace, "user_input", "") or "").strip() or decision
        name = self._derive_name(goal)
        success_criteria = []
        summary = (getattr(trace, "reasoning_summary", "") or "").strip()
        if summary:
            success_criteria.append(summary)
        success_criteria.append("Council deliberation produced a verified pass.")

        seed_conf = self._seed_confidence(agreement)

        skill = SkillContract(
            name=name,
            description=f"Council-derived skill for: {goal[:200]}",
            task_type=self._infer_task_type(tools),
            preconditions=[f"Task matches: {goal[:100]}"],
            execution_steps=execution_steps,
            tools_required=tools,
            success_criteria=success_criteria,
            triggers=self._extract_triggers(goal),
            tags=self._extract_tags(goal, tools),
            task_fingerprint=getattr(trace, "fingerprint", "") or "",
            council_origin_trace_id=getattr(trace, "trace_id", "") or "",
            status="candidate",
            confidence_score=seed_conf,
        )
        skill.compute_risk_level()
        return skill

    @staticmethod
    def _council_tools(rounds) -> list:
        """Walk debate rounds and collect a deduped tool list.

        Phase 3 council outputs don't expose suggested_tools per turn in
        ``DebateRound`` directly (votes/outputs are persisted), so we mine
        the freeform outputs for tool-name-looking tokens. Cheap and good
        enough — Phase 5 may persist suggested_tools explicitly.
        """
        all_text = []
        for r in rounds:
            for output in getattr(r, "agent_outputs", {}).values():
                if output:
                    all_text.append(str(output))
        text = "\n".join(all_text).lower()
        candidates = [
            "browser_navigate", "browser_click", "browser_type",
            "browser_screenshot", "browser_exec_js",
            "web_search", "web_fetch",
            "file_read", "file_write", "file_patch", "file_search",
            "bash_exec", "python_exec",
            "memory_store", "memory_recall",
            "send_file_tool", "delegate_task",
        ]
        return [c for c in candidates if c in text]

    @staticmethod
    def _council_steps(decision: str) -> list:
        """Split the synthesizer's decision into actionable steps."""
        if not decision:
            return []
        # Synthesizer prompts ask for short outputs; treat ; or newline as
        # step separators. Strip blank fragments.
        for sep in ("\n", ";"):
            if sep in decision:
                pieces = [p.strip(" -•") for p in decision.split(sep)]
                steps = [p for p in pieces if p]
                if steps:
                    return steps[:15]
        # Single-step decision is fine — many real plans are one move.
        return [decision]

    @staticmethod
    def _seed_confidence(agreement: Optional[float]) -> float:
        """Map inter-agent agreement to a starting confidence score."""
        if agreement is None:
            return 0.6
        a = max(0.0, min(1.0, float(agreement)))
        # 0.66 (the floor for crystallization) → 0.55; 1.0 → 0.7.
        return round(0.55 + 0.15 * (a - 0.66) / max(0.34, 1.0 - 0.66), 3)

    def _derive_name(self, goal: str) -> str:
        """Create a concise skill name from a goal description."""
        # Take first meaningful phrase, max 50 chars
        name = goal.strip().split("\n")[0]
        if len(name) > 50:
            name = name[:47] + "..."
        return name

    def _infer_task_type(self, tools: list[str]) -> str:
        """Infer task type from tools used."""
        tool_set = set(tools)
        if tool_set & {"bash_exec", "python_exec"}:
            return "coding"
        if tool_set & {"web_search", "web_fetch", "browser_navigate"}:
            return "web_research"
        if tool_set & {"file_read", "file_write", "file_patch", "file_search"}:
            return "file_ops"
        if tool_set & {"memory_store", "memory_recall"}:
            return "memory"
        return "general"

    def _extract_triggers(self, goal: str) -> list[str]:
        """Extract trigger keywords from goal text."""
        words = goal.lower().split()
        # Filter out common stop words
        stop = {"a", "an", "the", "is", "are", "was", "were", "be", "been",
                "being", "have", "has", "had", "do", "does", "did", "will",
                "would", "could", "should", "may", "might", "can", "shall",
                "to", "of", "in", "for", "on", "with", "at", "by", "from",
                "as", "into", "through", "during", "before", "after",
                "above", "below", "and", "or", "but", "not", "this", "that",
                "these", "those", "it", "its", "i", "me", "my", "we", "our",
                "you", "your", "he", "she", "they", "them", "their",
                "what", "which", "who", "whom", "how", "when", "where", "why",
                "please", "help", "need", "want"}
        triggers = [w for w in words if w not in stop and len(w) > 2]
        return triggers[:10]

    def _extract_tags(self, goal: str, tools: list[str]) -> list[str]:
        """Extract tags from goal and tools."""
        tags = list(tools)  # Tools are good tags
        # Add key action words from goal
        for word in goal.lower().split()[:5]:
            if len(word) > 3 and word not in tags:
                tags.append(word)
        return tags[:10]


__all__ = ["SkillExtractor"]
