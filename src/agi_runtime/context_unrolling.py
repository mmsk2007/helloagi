"""Context unrolling primitives for typed agent workspaces.

The design follows the Context Unrolling pattern:

    C[t+1] = C[t] + primitive(input, C[t])

HelloAGI uses this module to keep intermediate reasoning explicit,
source-tagged, confidence-scored, and separated from verified evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


@dataclass(frozen=True)
class WorkspaceItem:
    """A typed piece of context produced by observation, a primitive, or a tool."""

    id: str
    type: str
    content: Any
    source: str
    confidence: float
    observed: bool
    verified: bool
    relation: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.type:
            raise ValueError("workspace item type is required")
        if not self.source:
            raise ValueError("workspace item source is required")


@dataclass(frozen=True)
class PrimitiveResult:
    """Result returned by a context-producing primitive."""

    item_type: str
    content: Any
    confidence: float
    observed: bool = False
    verified: bool = False
    relation: str | None = None


@dataclass(frozen=True)
class ContextPrimitive:
    """Metadata for a primitive the controller may activate."""

    name: str
    produces: str
    task_types: set[str]
    cost: int = 1

    def supports(self, task_type: str) -> bool:
        return task_type in self.task_types or "any" in self.task_types


class ContextWorkspace:
    """Shared typed context workspace used before answering or acting."""

    def __init__(self, goal: str, inputs: Iterable[Any] | None = None) -> None:
        if not goal:
            raise ValueError("goal is required")
        self.goal = goal
        self.inputs = list(inputs or [])
        self._items: list[WorkspaceItem] = []

    @property
    def items(self) -> list[WorkspaceItem]:
        return list(self._items)

    def add(
        self,
        *,
        item_type: str,
        content: Any,
        source: str,
        confidence: float,
        observed: bool,
        verified: bool = False,
        relation: str | None = None,
    ) -> WorkspaceItem:
        item = WorkspaceItem(
            id=f"ctx_{uuid4().hex[:12]}",
            type=item_type,
            content=content,
            source=source,
            confidence=confidence,
            observed=observed,
            verified=verified,
            relation=relation,
        )
        self._items.append(item)
        return item

    def record_result(self, *, source: str, result: PrimitiveResult) -> WorkspaceItem:
        return self.add(
            item_type=result.item_type,
            content=result.content,
            source=source,
            confidence=result.confidence,
            observed=result.observed,
            verified=result.verified,
            relation=result.relation,
        )

    def by_type(self, item_type: str) -> list[WorkspaceItem]:
        return [item for item in self._items if item.type == item_type]

    def has_unverified_generated_context(self) -> bool:
        return any(not item.observed and not item.verified for item in self._items)

    def ready_for_action(self, *, risk: str) -> bool:
        """Return whether the workspace is safe enough to act.

        High-risk actions require generated assumptions to be verified. Low-risk
        actions may proceed while still carrying provenance into the final answer.
        """

        normalized = risk.lower().strip()
        if normalized in {"high", "critical", "destructive", "irreversible"}:
            return not self.has_unverified_generated_context()
        return True

    def summarize(self, *, include_content: bool = False) -> dict[str, Any]:
        items = []
        for item in self._items:
            row = {
                "id": item.id,
                "type": item.type,
                "source": item.source,
                "confidence": item.confidence,
                "observed": item.observed,
                "verified": item.verified,
                "relation": item.relation,
            }
            if include_content:
                row["content"] = item.content
            items.append(row)
        return {
            "goal": self.goal,
            "inputs_count": len(self.inputs),
            "items": items,
        }


_RELATIVE_ARTIFACT_RE = re.compile(
    r"(?<![\w./-])"
    r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|md|txt|json|yaml|yml|toml|ini|cfg)"
    r"(?:::[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)?)?)"
)


def extract_goal_artifact_references(goal: str) -> PrimitiveResult:
    """Extract public-safe file/test references mentioned in a user goal.

    This lightweight Context Unrolling primitive adapter converts raw prompt
    text into typed observed workspace evidence without reading file contents or
    exposing absolute/local runtime paths.
    """

    files: list[str] = []
    tests: list[str] = []
    for match in _RELATIVE_ARTIFACT_RE.finditer(goal):
        reference = match.group(1)
        file_part = reference.split("::", 1)[0]
        if file_part not in files:
            files.append(file_part)
        if "::" in reference and reference not in tests:
            tests.append(reference)

    return PrimitiveResult(
        item_type="artifact_references",
        content={"files": sorted(files), "tests": sorted(tests)},
        confidence=1.0 if files or tests else 0.0,
        observed=True,
        verified=True,
        relation="goal artifact mentions",
    )


def verify_goal_artifact_references(goal: str, *, root: str | Path = ".") -> PrimitiveResult:
    """Verify referenced artifacts exist without reading or leaking contents.

    The result keeps only repo-relative references. It never records absolute
    paths, file contents, runtime state, or path escapes outside ``root``.
    """

    references = extract_goal_artifact_references(goal).content
    root_path = Path(root).resolve()
    present_files: list[str] = []
    missing_files: list[str] = []
    present_tests: list[str] = []
    missing_tests: list[str] = []

    def is_safe_relative(reference: str) -> bool:
        path = Path(reference)
        return not path.is_absolute() and ".." not in path.parts

    for file_ref in references["files"]:
        if not is_safe_relative(file_ref):
            continue
        candidate = (root_path / file_ref).resolve()
        try:
            candidate.relative_to(root_path)
        except ValueError:
            continue
        target = present_files if candidate.is_file() else missing_files
        target.append(file_ref)

    for test_ref in references["tests"]:
        file_ref = test_ref.split("::", 1)[0]
        if not is_safe_relative(file_ref):
            continue
        candidate = (root_path / file_ref).resolve()
        try:
            candidate.relative_to(root_path)
        except ValueError:
            continue
        target = present_tests if candidate.is_file() else missing_tests
        target.append(test_ref)

    return PrimitiveResult(
        item_type="artifact_existence",
        content={
            "present_files": sorted(present_files),
            "missing_files": sorted(missing_files),
            "present_tests": sorted(present_tests),
            "missing_tests": sorted(missing_tests),
        },
        confidence=1.0 if references["files"] or references["tests"] else 0.0,
        observed=True,
        verified=True,
        relation="repo-relative artifact existence check",
    )


class ContextUnrollingController:
    """Budget-aware selector for task-relevant context primitives."""

    def __init__(self, primitives: Iterable[ContextPrimitive], max_primitives: int = 3) -> None:
        if max_primitives < 1:
            raise ValueError("max_primitives must be at least 1")
        self.primitives = list(primitives)
        self.max_primitives = max_primitives

    def select(self, *, task_type: str, workspace: ContextWorkspace) -> list[ContextPrimitive]:
        _ = workspace  # Reserved for future uncertainty/budget-aware selection.
        supported = [primitive for primitive in self.primitives if primitive.supports(task_type)]
        supported.sort(key=lambda primitive: (primitive.cost, primitive.name))
        return supported[: self.max_primitives]
