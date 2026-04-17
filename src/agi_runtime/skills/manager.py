"""Skill manager — create, index, and invoke learned skills.

Skills are stored as markdown files with YAML frontmatter.
Compatible with Hermes/Agency skill formats.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Skill:
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    steps: str = ""
    created_at: float = 0
    invoke_count: int = 0
    source_file: str = ""


class SkillManager:
    """Manages the agent's learned skills library."""

    def __init__(self, skills_dir: str = "memory/skills"):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: Dict[str, Skill] = {}
        self._load_all()

    def _load_all(self):
        """Load all skills from the skills directory."""
        for f in self.skills_dir.glob("*.md"):
            skill = self._parse_skill_file(f)
            if skill:
                self._skills[skill.name] = skill

    def _parse_skill_file(self, path: Path) -> Optional[Skill]:
        """Parse a skill markdown file with YAML frontmatter."""
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Parse YAML frontmatter
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if not match:
            return None

        frontmatter = match.group(1)
        body = match.group(2)

        # Simple YAML parsing (no external dep)
        meta = {}
        for line in frontmatter.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                # Handle lists
                if val.startswith("[") and val.endswith("]"):
                    val = [v.strip().strip("'\"") for v in val[1:-1].split(",")]
                meta[key] = val

        return Skill(
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            triggers=meta.get("triggers", []) if isinstance(meta.get("triggers"), list) else [],
            tools=meta.get("tools", []) if isinstance(meta.get("tools"), list) else [],
            steps=body.strip(),
            created_at=float(meta.get("created_at", 0)),
            invoke_count=int(meta.get("invoke_count", 0)),
            source_file=str(path),
        )

    def create_skill(
        self,
        name: str,
        description: str,
        triggers: List[str],
        tools: List[str],
        steps: str,
    ) -> Skill:
        """Crystallize a new skill from a successful workflow."""
        # Sanitize filename
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower())
        path = self.skills_dir / f"{safe_name}.md"

        skill = Skill(
            name=name,
            description=description,
            triggers=triggers,
            tools=tools,
            steps=steps,
            created_at=time.time(),
            source_file=str(path),
        )

        # Write skill file
        triggers_str = "[" + ", ".join(triggers) + "]"
        tools_str = "[" + ", ".join(tools) + "]"
        content = f"""---
name: {name}
description: {description}
triggers: {triggers_str}
tools: {tools_str}
created_at: {skill.created_at}
invoke_count: 0
---

{steps}
"""
        path.write_text(content, encoding="utf-8")
        self._skills[name] = skill
        return skill

    def find_matching_skill(self, query: str) -> Optional[Skill]:
        """Find a skill that matches the given query based on triggers."""
        query_lower = query.lower()
        best_match = None
        best_score = 0

        for skill in self._skills.values():
            score = 0
            for trigger in skill.triggers:
                if trigger.lower() in query_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best_match = skill

        return best_match if best_score > 0 else None

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_skills(self) -> List[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.invoke_count, reverse=True)

    def get_skills_index(self) -> str:
        """Get a formatted index of available skills for system prompt injection."""
        skills = self.list_skills()
        if not skills:
            return ""

        lines = ["Available learned skills:"]
        for s in skills[:20]:  # Limit to top 20
            triggers_str = ", ".join(s.triggers[:5])
            lines.append(f"  - {s.name}: {s.description} (triggers: {triggers_str})")
        return "\n".join(lines)

    def increment_invoke_count(self, name: str):
        """Track skill usage."""
        skill = self._skills.get(name)
        if skill:
            skill.invoke_count += 1
            # Update the file
            if skill.source_file:
                try:
                    path = Path(skill.source_file)
                    text = path.read_text(encoding="utf-8")
                    text = re.sub(
                        r"invoke_count: \d+",
                        f"invoke_count: {skill.invoke_count}",
                        text,
                    )
                    path.write_text(text, encoding="utf-8")
                except Exception:
                    pass

    def delete_skill(self, name: str) -> bool:
        skill = self._skills.pop(name, None)
        if skill and skill.source_file:
            Path(skill.source_file).unlink(missing_ok=True)
            return True
        return False
