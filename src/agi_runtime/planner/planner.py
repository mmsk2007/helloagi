"""LLM-powered dynamic planner.

Decomposes goals into concrete, executable steps with tool assignments.
SRG screens the entire plan before execution begins.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


@dataclass
class PlanStep:
    id: int
    action: str
    tool: Optional[str] = None
    tool_input: Optional[dict] = None
    depends_on: List[int] = field(default_factory=list)
    success_criteria: str = ""
    status: str = "pending"  # pending | running | done | failed | skipped
    result: str = ""


@dataclass
class Plan:
    goal: str
    steps: List[PlanStep]
    reasoning: str = ""

    @property
    def pending_steps(self) -> List[PlanStep]:
        return [s for s in self.steps if s.status == "pending"]

    @property
    def ready_steps(self) -> List[PlanStep]:
        """Steps whose dependencies are all done."""
        done_ids = {s.id for s in self.steps if s.status == "done"}
        return [
            s for s in self.steps
            if s.status == "pending" and all(d in done_ids for d in s.depends_on)
        ]

    @property
    def is_complete(self) -> bool:
        return all(s.status in ("done", "skipped") for s in self.steps)

    @property
    def has_failures(self) -> bool:
        return any(s.status == "failed" for s in self.steps)


class Planner:
    """Intelligent goal decomposition using LLM or templates."""

    PLANNING_PROMPT = """You are a task planner for an autonomous AI agent. Given a goal and available tools, create a concrete execution plan.

Available tools: {tools}

Output a JSON object with:
- "reasoning": brief explanation of your approach
- "steps": array of step objects, each with:
  - "id": integer (1-based)
  - "action": what to do (human-readable)
  - "tool": which tool to use (from available tools, or null for reasoning steps)
  - "tool_input": dict of parameters for the tool (or null)
  - "depends_on": list of step IDs this depends on (empty for independent steps)
  - "success_criteria": how to verify this step succeeded

Keep it practical: 3-8 steps for most tasks. Use tools that exist.
Output ONLY valid JSON, no markdown."""

    def make_plan(self, goal: str, available_tools: List[str] = None) -> Plan:
        """Create an execution plan for the given goal."""
        if not _ANTHROPIC_AVAILABLE or not os.environ.get("ANTHROPIC_API_KEY"):
            return self._template_plan(goal)

        if available_tools is None:
            from agi_runtime.tools.registry import ToolRegistry
            available_tools = [t.name for t in ToolRegistry.get_instance().list_tools()]

        try:
            client = anthropic.Anthropic()
            tools_desc = ", ".join(available_tools) if available_tools else "bash_exec, file_read, file_write, python_exec, web_search"

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": self.PLANNING_PROMPT.format(tools=tools_desc) + f"\n\nGoal: {goal}",
                }],
            )

            text = response.content[0].text.strip()
            # Parse JSON from response
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text)
            steps = [
                PlanStep(
                    id=s.get("id", i + 1),
                    action=s["action"],
                    tool=s.get("tool"),
                    tool_input=s.get("tool_input"),
                    depends_on=s.get("depends_on", []),
                    success_criteria=s.get("success_criteria", ""),
                )
                for i, s in enumerate(data.get("steps", []))
            ]

            return Plan(
                goal=goal,
                steps=steps,
                reasoning=data.get("reasoning", ""),
            )

        except Exception as e:
            # Fall back to template on any error
            return self._template_plan(goal)

    def _template_plan(self, goal: str) -> Plan:
        """Fallback template plan when LLM is unavailable."""
        return Plan(
            goal=goal,
            steps=[
                PlanStep(id=1, action="Analyze the goal and identify requirements", success_criteria="Clear understanding of what needs to be done"),
                PlanStep(id=2, action="Gather necessary information and resources", depends_on=[1], success_criteria="All needed info collected"),
                PlanStep(id=3, action="Execute the core task", depends_on=[2], success_criteria="Task completed without errors"),
                PlanStep(id=4, action="Verify results against original goal", depends_on=[3], success_criteria="Results match expectations"),
            ],
            reasoning="Template plan (LLM unavailable)",
        )

    def replan(self, original_plan: Plan, failure_context: str) -> Plan:
        """Create a new plan after a failure, incorporating lessons learned."""
        failed_steps = [s for s in original_plan.steps if s.status == "failed"]
        context = (
            f"Original goal: {original_plan.goal}\n"
            f"Failed steps: {[s.action for s in failed_steps]}\n"
            f"Failure context: {failure_context}\n"
            f"Create an alternative plan that avoids the same failure."
        )
        return self.make_plan(context)
