"""Invoke a previously learned skill."""

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="skill_invoke",
    description="Execute a previously learned skill by name. Returns the skill's steps and instructions.",
    toolset="memory",
    risk="medium",
    parameters=[
        ToolParam("name", "string", "Name of the skill to invoke, or a query to match against triggers"),
    ],
)
def skill_invoke(name: str) -> ToolResult:
    from agi_runtime.skills.manager import SkillManager

    sm = SkillManager()

    # Try exact name match first
    skill = sm.get_skill(name)

    # Fall back to trigger matching
    if not skill:
        skill = sm.find_matching_skill(name)

    if not skill:
        available = sm.list_skills()
        if available:
            names = ", ".join(s.name for s in available[:10])
            return ToolResult(ok=False, output="", error=f"Skill '{name}' not found. Available skills: {names}")
        return ToolResult(ok=False, output="", error="No skills learned yet. Complete complex tasks to build your skill library.")

    sm.increment_invoke_count(name)

    return ToolResult(
        ok=True,
        output=(
            f"Skill: {skill.name}\n"
            f"Description: {skill.description}\n"
            f"Tools needed: {', '.join(skill.tools)}\n\n"
            f"## Steps\n{skill.steps}"
        ),
    )
