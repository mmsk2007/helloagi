"""Skill Bank — persistent storage for SkillContracts with lifecycle management.

Stores skills as JSON files. Backward-compatible with the old SkillManager's
markdown format — imports and converts on first load.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from agi_runtime.skills.skill_schema import SkillContract


class SkillBank:
    """Governed, versioned skill storage with decay and retirement.

    Skills progress through: candidate → active → retired → archived.
    """

    CONFIDENCE_RETIRE_THRESHOLD = 0.15
    DECAY_INTERVAL_DAYS = 7
    DECAY_RATE = 0.05  # Reduce confidence by 5% per decay interval

    def __init__(self, skills_dir: str = "memory/skills"):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: Dict[str, SkillContract] = {}
        self._load_all()

    # ── CRUD ─────────────────────────────────────────────────────

    def add(self, skill: SkillContract) -> SkillContract:
        """Add a new skill to the bank."""
        skill.compute_risk_level()
        self._skills[skill.skill_id] = skill
        self._save(skill)
        return skill

    def get(self, skill_id: str) -> Optional[SkillContract]:
        return self._skills.get(skill_id)

    def get_by_name(self, name: str) -> Optional[SkillContract]:
        for s in self._skills.values():
            if s.name == name:
                return s
        return None

    def update(self, skill: SkillContract) -> SkillContract:
        """Update and version-bump a skill."""
        skill.version += 1
        skill.updated_at = time.time()
        skill.compute_risk_level()
        self._skills[skill.skill_id] = skill
        self._save(skill)
        return skill

    def persist(self, skill: SkillContract) -> None:
        """Save skill metadata without bumping semantic version (e.g. usage counters)."""
        skill.updated_at = time.time()
        skill.compute_risk_level()
        self._skills[skill.skill_id] = skill
        self._save(skill)

    def remove(self, skill_id: str) -> bool:
        skill = self._skills.pop(skill_id, None)
        if skill:
            path = self._skill_path(skill)
            path.unlink(missing_ok=True)
            return True
        return False

    def list_skills(
        self,
        *,
        status: str | None = None,
        task_type: str | None = None,
        min_confidence: float | None = None,
    ) -> List[SkillContract]:
        """List skills with optional filters."""
        out = list(self._skills.values())
        if status:
            out = [s for s in out if s.status == status]
        if task_type:
            out = [s for s in out if s.task_type == task_type]
        if min_confidence is not None:
            out = [s for s in out if s.confidence_score >= min_confidence]
        return sorted(out, key=lambda s: s.confidence_score, reverse=True)

    def list_active(self) -> List[SkillContract]:
        return self.list_skills(status="active")

    @property
    def count(self) -> int:
        return len(self._skills)

    # ── Lifecycle ────────────────────────────────────────────────

    def promote(self, skill_id: str) -> Optional[SkillContract]:
        """Promote a candidate skill to active status."""
        skill = self._skills.get(skill_id)
        if skill and skill.status == "candidate":
            skill.status = "active"
            return self.update(skill)
        return None

    def retire(self, skill_id: str) -> Optional[SkillContract]:
        """Retire a skill (still stored, not used for matching)."""
        skill = self._skills.get(skill_id)
        if skill and skill.status in ("active", "candidate"):
            skill.status = "retired"
            return self.update(skill)
        return None

    def archive(self, skill_id: str) -> Optional[SkillContract]:
        """Archive a retired skill."""
        skill = self._skills.get(skill_id)
        if skill:
            skill.status = "archived"
            return self.update(skill)
        return None

    def merge_skills(self, keep_id: str, absorb_id: str) -> Optional[SkillContract]:
        """COS-PLAY-style bank curation: fold ``absorb`` into ``keep``, then retire absorb.

        Combines triggers, tools, execution steps, and failure modes; bumps ``keep`` version.
        Returns the updated keeper, or ``None`` if ids are invalid or identical.
        """
        if keep_id == absorb_id:
            return None
        keep = self._skills.get(keep_id)
        absorb = self._skills.get(absorb_id)
        if not keep or not absorb:
            return None

        def _uniq(seq: List[str]) -> List[str]:
            seen: Set[str] = set()
            out: List[str] = []
            for item in seq:
                key = (item or "").strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(item.strip())
            return out

        keep.triggers = _uniq(list(keep.triggers) + list(absorb.triggers))
        keep.tags = _uniq(list(keep.tags) + list(absorb.tags))
        keep.tools_required = _uniq(list(keep.tools_required) + list(absorb.tools_required))
        keep.preconditions = _uniq(list(keep.preconditions) + list(absorb.preconditions))
        keep.execution_steps = _uniq(list(keep.execution_steps) + list(absorb.execution_steps))
        keep.success_criteria = _uniq(list(keep.success_criteria) + list(absorb.success_criteria))
        for fm in absorb.failure_modes:
            if fm and fm not in keep.failure_modes:
                keep.failure_modes.append(fm)
        desc_bits = [d for d in (keep.description, absorb.description) if (d or "").strip()]
        if desc_bits:
            keep.description = " | ".join(desc_bits)[:2000]

        absorb.status = "retired"
        absorb.updated_at = time.time()
        self._save(absorb)

        keep.usage_count += absorb.usage_count
        keep.success_count += absorb.success_count
        keep.failure_count += absorb.failure_count
        keep.compute_risk_level()
        return self.update(keep)

    def split_skill(
        self,
        source_id: str,
        new_name: str,
        steps_for_new: List[str],
    ) -> Tuple[Optional[SkillContract], Optional[SkillContract]]:
        """Split a contiguous block of execution steps into a new candidate skill.

        Returns ``(new_skill, updated_source)`` or ``(None, None)`` if the step block
        is not found as a contiguous subsequence of ``source.execution_steps``.
        """
        src = self._skills.get(source_id)
        if not src or not new_name.strip() or not steps_for_new:
            return None, None
        seq = [s.strip() for s in steps_for_new if str(s).strip()]
        es = [s.strip() for s in src.execution_steps]
        n = len(seq)
        if n == 0 or n > len(es):
            return None, None
        found_at = -1
        for i in range(len(es) - n + 1):
            if es[i : i + n] == seq:
                found_at = i
                break
        if found_at < 0:
            return None, None

        branch_steps = es[found_at : found_at + n]
        remaining = es[:found_at] + es[found_at + n :]

        new_skill = SkillContract(
            name=new_name.strip(),
            description=f"Split from {src.name}",
            triggers=list(src.triggers)[:5],
            tools_required=list(dict.fromkeys(src.tools_required)),
            preconditions=list(src.preconditions)[:5],
            execution_steps=branch_steps,
            status="candidate",
            confidence_score=max(0.35, min(0.85, src.confidence_score * 0.85)),
        )
        new_skill.compute_risk_level()
        self.add(new_skill)

        src.execution_steps = remaining
        src.updated_at = time.time()
        src.compute_risk_level()
        return new_skill, self.update(src)

    def apply_decay(self) -> List[str]:
        """Apply confidence decay to unused skills. Returns IDs of retired skills."""
        now = time.time()
        retired_ids = []
        for skill in list(self._skills.values()):
            if skill.status not in ("active", "candidate"):
                continue
            if not skill.last_used_at:
                continue
            days_idle = (now - skill.last_used_at) / 86400
            if days_idle >= self.DECAY_INTERVAL_DAYS:
                intervals = int(days_idle / self.DECAY_INTERVAL_DAYS)
                decay = self.DECAY_RATE * intervals
                skill.confidence_score = max(0.0, round(skill.confidence_score - decay, 3))
                skill.updated_at = now
                if skill.confidence_score < self.CONFIDENCE_RETIRE_THRESHOLD:
                    skill.status = "retired"
                    retired_ids.append(skill.skill_id)
                self._save(skill)
        return retired_ids

    # ── Import from old SkillManager ─────────────────────────────

    def import_legacy_skills(self) -> int:
        """Import old markdown-format skills into the bank."""
        count = 0
        for f in self.skills_dir.glob("*.md"):
            # Skip if a contract file already exists for this markdown stem
            safe_stem = re.sub(r"[^a-zA-Z0-9_-]", "-", f.stem.lower())[:60]
            json_path = self.skills_dir / f"{safe_stem}.skill.json"
            if json_path.exists():
                continue
            skill = self._parse_legacy_markdown(f)
            if skill and skill.skill_id not in self._skills:
                skill.status = "active"  # Legacy skills are trusted
                self._skills[skill.skill_id] = skill
                self._save(skill)
                count += 1
        return count

    def _parse_legacy_markdown(self, path: Path) -> Optional[SkillContract]:
        """Parse an old SkillManager markdown file into a SkillContract."""
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return None
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if not match:
            return None
        frontmatter, body = match.group(1), match.group(2)
        meta = {}
        for line in frontmatter.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                key, val = key.strip(), val.strip()
                if val.startswith("[") and val.endswith("]"):
                    val = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
                meta[key] = val
        return SkillContract(
            skill_id=meta.get("skill_id", path.stem[:12]),
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            triggers=meta.get("triggers", []) if isinstance(meta.get("triggers"), list) else [],
            tools_required=meta.get("tools", []) if isinstance(meta.get("tools"), list) else [],
            execution_steps=[s.strip() for s in body.strip().split("\n") if s.strip()],
            usage_count=int(meta.get("invoke_count", 0)),
            created_at=float(meta.get("created_at", 0)),
            status="active",
        )

    # ── Persistence ──────────────────────────────────────────────

    def _skill_path(self, skill: SkillContract) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", skill.name.lower())[:60]
        return self.skills_dir / f"{safe}.skill.json"

    def _save(self, skill: SkillContract) -> None:
        path = self._skill_path(skill)
        try:
            path.write_text(skill.to_json(), encoding="utf-8")
        except Exception:
            pass

    def _load_all(self) -> None:
        """Load all JSON skill files, then import any legacy markdown skills."""
        for f in self.skills_dir.glob("*.skill.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                skill = SkillContract.from_dict(data)
                self._skills[skill.skill_id] = skill
            except Exception:
                continue
        # Auto-import legacy skills
        self.import_legacy_skills()

    # ── Index for prompts ────────────────────────────────────────

    def get_skills_index(self, max_skills: int = 15) -> str:
        """Get a formatted index for system prompt injection."""
        active = self.list_active()
        if not active:
            return ""
        lines = ["Available learned skills:"]
        for s in active[:max_skills]:
            lines.append(f"  - {s.name}: {s.description} (conf={s.confidence_score:.2f})")
        return "\n".join(lines)


__all__ = ["SkillBank"]
