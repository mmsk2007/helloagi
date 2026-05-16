"""Context unrolling primitives for typed agent workspaces.

The design follows the Context Unrolling pattern:

    C[t+1] = C[t] + primitive(input, C[t])

HelloAGI uses this module to keep intermediate reasoning explicit,
source-tagged, confidence-scored, and separated from verified evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
