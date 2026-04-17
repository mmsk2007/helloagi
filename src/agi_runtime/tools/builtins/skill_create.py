"""Crystallize a successful workflow into a reusable skill."""

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="skill_create",
    description="Save a successful workflow as a reusable skill. The skill can be invoked later for similar tasks, making the agent smarter over time.",
    toolset="memory",
    risk="low",
    parameters=[
        ToolParam("name", "string", "Short name for the skill (e.g. 'deploy-python-app')"),
        ToolParam("description", "string", "What this skill does"),
        ToolParam("triggers", "string", "Comma-separated trigger words (e.g. 'deploy,publish,release')"),
        ToolParam("tools_used", "string", "Comma-separated tools this skill uses (e.g. 'bash_exec,file_write')"),
        ToolParam("steps", "string", "Step-by-step instructions for the skill (markdown format)"),
    ],
)
def skill_create(name: str, description: str, triggers: str, tools_used: str, steps: str) -> ToolResult:
    from agi_runtime.skills.manager import SkillManager

    sm = SkillManager()

    trigger_list = [t.strip() for t in triggers.split(",") if t.strip()]
    tools_list = [t.strip() for t in tools_used.split(",") if t.strip()]

    skill = sm.create_skill(
        name=name,
        description=description,
        triggers=trigger_list,
        tools=tools_list,
        steps=steps,
    )

    return ToolResult(
        ok=True,
        output=f"Skill '{name}' crystallized successfully!\nTriggers: {trigger_list}\nTools: {tools_list}\nStored at: {skill.source_file}",
    )
