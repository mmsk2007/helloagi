"""Context unrolling primitives for typed agent workspaces.

The design follows the Context Unrolling pattern:

    C[t+1] = C[t] + primitive(input, C[t])

HelloAGI uses this module to keep intermediate reasoning explicit,
source-tagged, confidence-scored, and separated from verified evidence.
"""

from __future__ import annotations

import ast
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
class ActionReadiness:
    """Machine-checkable context gate decision before an agent action."""

    risk: str
    ready: bool
    blockers: list[str]
    required_evidence: list[str]
    summary: str


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

        return evaluate_action_readiness(self, risk=risk).ready

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


def evaluate_action_readiness(workspace: ContextWorkspace, *, risk: str) -> ActionReadiness:
    """Evaluate whether typed workspace evidence is sufficient before acting.

    Low-risk actions may proceed with provenance only. High-risk actions require
    no unverified generated assumptions plus verified risk and scope evidence so
    callers can enforce the Context Unrolling action gate mechanically instead
    of relying on prompt text alone.
    """

    normalized = risk.lower().strip()
    high_risk = normalized in {"high", "critical", "destructive", "irreversible"}
    required_evidence = ["action_risk", "scope"] if high_risk else []
    blockers: list[str] = []

    if high_risk and workspace.has_unverified_generated_context():
        blockers.append("unverified_generated_context")
    for item_type in required_evidence:
        if not any(item.verified for item in workspace.by_type(item_type)):
            blockers.append(f"missing_verified_{item_type}")

    labels = {
        "unverified_generated_context": "unverified generated context",
        "missing_verified_action_risk": "missing verified action risk",
        "missing_verified_scope": "missing verified scope",
    }
    summary = "ready" if not blockers else "blocked: " + "; ".join(labels.get(blocker, blocker) for blocker in blockers)
    return ActionReadiness(
        risk=normalized,
        ready=not blockers,
        blockers=blockers,
        required_evidence=required_evidence,
        summary=summary,
    )


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


def summarize_goal_artifact_metadata(goal: str, *, root: str | Path = ".") -> PrimitiveResult:
    """Record content-safe metadata for referenced artifacts.

    This primitive reads only public-safe file metadata for repo-relative paths:
    path, byte size, line count, and artifact kind. It never stores file contents,
    absolute paths, or path escapes outside ``root``.
    """

    references = extract_goal_artifact_references(goal).content
    existence = verify_goal_artifact_references(goal, root=root).content
    root_path = Path(root).resolve()
    files: list[dict[str, Any]] = []
    unreadable_files: list[str] = []

    for file_ref in existence["present_files"]:
        candidate = (root_path / file_ref).resolve()
        try:
            candidate.relative_to(root_path)
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            unreadable_files.append(file_ref)
            continue
        files.append({
            "path": file_ref,
            "bytes": len(data),
            "lines": data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0),
            "kind": "test" if file_ref.startswith("tests/") else "file",
        })

    return PrimitiveResult(
        item_type="artifact_metadata",
        content={
            "files": sorted(files, key=lambda item: item["path"]),
            "missing_files": list(existence["missing_files"]),
            "unreadable_files": sorted(unreadable_files),
        },
        confidence=1.0 if references["files"] or references["tests"] else 0.0,
        observed=True,
        verified=True,
        relation="repo-relative artifact metadata without content",
    )


def collect_goal_pytest_references(goal: str, *, root: str | Path = ".") -> PrimitiveResult:
    """Resolve referenced pytest node ids without executing repository code.

    This primitive uses a static AST scan for repo-relative pytest references.
    It records only references, compact statuses, and counts; it does not run
    pytest collection, import test modules, store file contents, or record
    absolute paths/tracebacks.
    """

    def parameter_count(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        count = 1
        for decorator in function.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            if call is None:
                continue
            target = call.func
            if not isinstance(target, ast.Attribute) or target.attr != "parametrize":
                continue
            if len(call.args) < 2:
                continue
            values = call.args[1]
            if isinstance(values, (ast.List, ast.Tuple)):
                count *= max(1, len(values.elts))
        return count

    def static_collect_count(candidate: Path, node_parts: list[str]) -> tuple[str, int]:
        try:
            tree = ast.parse(candidate.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return "collection_error", 0
        module_nodes = list(tree.body)
        if not node_parts:
            total = sum(
                parameter_count(node)
                for node in module_nodes
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            )
            total += sum(
                parameter_count(child)
                for node in module_nodes
                if isinstance(node, ast.ClassDef) and node.name.startswith("Test")
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_")
            )
            return ("collected", total) if total else ("not_collected", 0)
        first = node_parts[0]
        top = next(
            (
                node
                for node in module_nodes
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == first
            ),
            None,
        )
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if len(node_parts) == 1 and top.name.startswith("test_"):
                return "collected", parameter_count(top)
            return "not_collected", 0
        if isinstance(top, ast.ClassDef):
            if not top.name.startswith("Test"):
                return "not_collected", 0
            if len(node_parts) == 1:
                total = sum(
                    parameter_count(child)
                    for child in top.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_")
                )
                return ("collected", total) if total else ("not_collected", 0)
            method_name = node_parts[1]
            method = next(
                (
                    child
                    for child in top.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name
                ),
                None,
            )
            return ("collected", parameter_count(method)) if method is not None and method.name.startswith("test_") else ("not_collected", 0)
        return "not_collected", 0

    references = extract_goal_artifact_references(goal).content
    existence = verify_goal_artifact_references(goal, root=root).content
    root_path = Path(root).resolve()
    present_test_files = {test_ref.split("::", 1)[0] for test_ref in existence["present_tests"]}
    tests: list[dict[str, Any]] = []
    skipped: list[str] = []

    for test_ref in sorted(references["tests"]):
        file_ref, _, node_ref = test_ref.partition("::")
        path = Path(file_ref)
        if path.is_absolute() or ".." in path.parts:
            skipped.append(test_ref)
            continue
        candidate = (root_path / file_ref).resolve()
        try:
            candidate.relative_to(root_path)
        except ValueError:
            skipped.append(test_ref)
            continue
        if file_ref not in present_test_files:
            tests.append({"reference": test_ref, "status": "missing_file", "collected_count": 0})
            continue
        status, collected_count = static_collect_count(candidate, node_ref.split("::") if node_ref else [])
        tests.append({"reference": test_ref, "status": status, "collected_count": collected_count})

    return PrimitiveResult(
        item_type="pytest_collection",
        content={"tests": tests, "skipped": sorted(skipped)},
        confidence=1.0 if references["tests"] else 0.0,
        observed=True,
        verified=True,
        relation="repo-relative static pytest node check without output",
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
