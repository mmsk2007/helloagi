"""Skill manager — facade over SkillBank + legacy markdown workflows.

Preserves the public Skill / SkillManager API while delegating storage and
retrieval to SkillContract + SkillBank + SkillRetriever.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from agi_runtime.skills.skill_bank import SkillBank
from agi_runtime.skills.skill_retriever import SkillMatch, SkillRetriever
from agi_runtime.skills.skill_schema import SkillContract


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
    """Manages the agent's learned skills library (bank-backed)."""

    def __init__(
        self,
        skills_dir: str = "memory/skills",
        skill_bank_settings: Optional[Dict[str, Any]] = None,
    ):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._bank_cfg = skill_bank_settings or {}
        self._bank_enabled = self._bank_cfg.get("enabled", True)
        self.bank = SkillBank(str(self.skills_dir))
        self._retriever = SkillRetriever()

    @property
    def skill_bank(self) -> SkillBank:
        """Underlying contract store (for TriLoop and diagnostics)."""
        return self.bank

    def _contract_to_skill(self, c: SkillContract) -> Skill:
        steps = "\n".join(c.execution_steps) if c.execution_steps else ""
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", (c.name or "skill").lower())
        md_path = self.skills_dir / f"{safe}.md"
        return Skill(
            name=c.name,
            description=c.description,
            triggers=list(c.triggers),
            tools=list(c.tools_required),
            steps=steps,
            created_at=float(c.created_at or 0),
            invoke_count=int(c.usage_count),
            source_file=str(md_path) if md_path else "",
        )

    def _all_contracts_for_match(self) -> List[SkillContract]:
        return [
            s for s in self.bank.list_skills()
            if s.status in ("active", "candidate")
        ]

    def find_matching_skill(self, query: str) -> Optional[Skill]:
        """Find a skill matching the query (triggers first, then strong semantic match)."""
        if not self._bank_enabled:
            return self._find_trigger_only(query)

        query_lower = query.lower()
        contracts = self._all_contracts_for_match()
        matches = self._retriever.find_matches(
            query, contracts, top_k=8, min_relevance=0.05, task_type=""
        )
        best_trigger: Optional[SkillContract] = None
        best_tr_score = 0.0
        for m in matches:
            if any(t.lower() in query_lower for t in m.skill.triggers):
                if m.relevance > best_tr_score:
                    best_tr_score = m.relevance
                    best_trigger = m.skill
        if best_trigger:
            return self._contract_to_skill(best_trigger)
        if matches and matches[0].relevance >= 0.42:
            return self._contract_to_skill(matches[0].skill)

        return self._find_trigger_only(query)

    def _find_trigger_only(self, query: str) -> Optional[Skill]:
        query_lower = query.lower()
        best: Optional[SkillContract] = None
        best_score = 0
        for skill in self._all_contracts_for_match():
            score = 0
            for trigger in skill.triggers:
                if trigger.lower() in query_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best = skill
        return self._contract_to_skill(best) if best and best_score > 0 else None

    def find_matching_skill_semantic(
        self, query: str, *, top_k: int = 3, task_type: str = ""
    ) -> List[SkillMatch]:
        """Return ranked SkillMatch objects (empty if skill bank disabled)."""
        if not self._bank_enabled:
            return []
        return self._retriever.find_matches(
            query,
            self._all_contracts_for_match(),
            top_k=top_k,
            min_relevance=0.1,
            task_type=task_type,
        )

    def create_skill(
        self,
        name: str,
        description: str,
        triggers: List[str],
        tools: List[str],
        steps: Union[str, List[str]],
    ) -> Skill:
        """Crystallize a new skill from a successful workflow (markdown + bank)."""
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower())
        path = self.skills_dir / f"{safe_name}.md"

        if isinstance(steps, str):
            execution_lines = [ln.strip() for ln in steps.splitlines() if ln.strip()]
            body_text = steps
        else:
            execution_lines = [str(s).strip() for s in steps if str(s).strip()]
            body_text = "\n".join(execution_lines)

        skill = Skill(
            name=name,
            description=description,
            triggers=triggers,
            tools=tools,
            steps=body_text,
            created_at=time.time(),
            source_file=str(path),
        )

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

{body_text}
"""
        path.write_text(content, encoding="utf-8")

        contract = SkillContract(
            name=name,
            description=description,
            triggers=triggers,
            tools_required=tools,
            execution_steps=execution_lines,
            status="active",
            confidence_score=0.75,
        )
        contract.compute_risk_level()
        self.bank.add(contract)

        return skill

    def get_skill(self, name: str) -> Optional[Skill]:
        c = self.bank.get_by_name(name)
        return self._contract_to_skill(c) if c else None

    def list_skills(self) -> List[Skill]:
        out: List[Skill] = []
        for c in self.bank.list_skills(status="active"):
            out.append(self._contract_to_skill(c))
        for c in self.bank.list_skills(status="candidate"):
            out.append(self._contract_to_skill(c))
        return sorted(out, key=lambda s: s.invoke_count, reverse=True)

    def get_skills_index(self) -> str:
        """Formatted index of skills for system prompt injection."""
        if not self._bank_enabled:
            return ""
        return self.bank.get_skills_index(max_skills=20)

    def bind_embedding_store(self, store) -> None:
        """Attach Gemini embedding store for COS-PLAY-style semantic skill retrieval."""
        self._retriever.bind_embedding_store(store)

    def merge_skills(self, keep_id: str, absorb_id: str) -> Optional[SkillContract]:
        """Merge two contracts; ``absorb_id`` is retired (bank curation)."""
        if not self._bank_enabled:
            return None
        merged = self.bank.merge_skills(keep_id, absorb_id)
        if merged:
            self._retriever.invalidate_embedding_cache(keep_id, absorb_id)
        return merged

    def split_skill(
        self, source_id: str, new_name: str, steps_for_new: List[str],
    ) -> Tuple[Optional[SkillContract], Optional[SkillContract]]:
        """Split a contiguous execution-step block into a new candidate skill."""
        if not self._bank_enabled:
            return None, None
        new_c, updated = self.bank.split_skill(source_id, new_name, steps_for_new)
        if new_c:
            self._retriever.invalidate_embedding_cache(source_id)
            self._retriever.invalidate_embedding_cache(new_c.skill_id)
        return new_c, updated

    def increment_invoke_count(self, name: str):
        c = self.bank.get_by_name(name)
        if not c:
            return
        c.usage_count += 1
        c.last_used_at = time.time()
        c.updated_at = time.time()
        self.bank.persist(c)
        # Best-effort: sync invoke_count line in markdown if present
        md_path = self.skills_dir / f"{re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())}.md"
        if md_path.exists():
            try:
                text = md_path.read_text(encoding="utf-8")
                text = re.sub(
                    r"invoke_count: \d+",
                    f"invoke_count: {c.usage_count}",
                    text,
                )
                md_path.write_text(text, encoding="utf-8")
            except Exception:
                pass

    def delete_skill(self, name: str) -> bool:
        c = self.bank.get_by_name(name)
        if c:
            self.bank.remove(c.skill_id)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower())
        md = self.skills_dir / f"{safe_name}.md"
        if md.exists():
            md.unlink(missing_ok=True)
            return True
        return c is not None
