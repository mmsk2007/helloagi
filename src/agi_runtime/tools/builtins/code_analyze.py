"""Static code analysis — find patterns, count functions, analyze structure."""

import ast
import os
from pathlib import Path

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="code_analyze",
    description="Analyze Python code structure: list functions, classes, imports, and basic metrics.",
    toolset="code",
    risk="low",
    parameters=[
        ToolParam("path", "string", "Path to a Python file or directory to analyze"),
    ],
)
def code_analyze(path: str) -> ToolResult:
    p = Path(path)
    if not p.exists():
        return ToolResult(ok=False, output="", error=f"Path not found: {path}")

    if p.is_file():
        return _analyze_file(p)

    # Directory — analyze all .py files
    results = []
    py_files = sorted(p.rglob("*.py"))
    total_lines = 0
    total_functions = 0
    total_classes = 0

    for f in py_files[:50]:  # Limit to 50 files
        info = _file_info(f)
        if info:
            total_lines += info["lines"]
            total_functions += len(info["functions"])
            total_classes += len(info["classes"])
            results.append(f"  {f.relative_to(p)}: {info['lines']} lines, {len(info['functions'])} fns, {len(info['classes'])} classes")

    summary = (
        f"Directory: {path}\n"
        f"Python files: {len(py_files)}\n"
        f"Total lines: {total_lines}\n"
        f"Total functions: {total_functions}\n"
        f"Total classes: {total_classes}\n\n"
        + "\n".join(results)
    )
    return ToolResult(ok=True, output=summary)


def _analyze_file(p: Path) -> ToolResult:
    try:
        source = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return ToolResult(ok=False, output="", error=str(e))

    info = _file_info(p)
    if not info:
        return ToolResult(ok=True, output=f"File: {p}\nCould not parse as Python.")

    parts = [
        f"File: {p}",
        f"Lines: {info['lines']}",
    ]

    if info["imports"]:
        parts.append(f"\nImports ({len(info['imports'])}):")
        for imp in info["imports"]:
            parts.append(f"  {imp}")

    if info["classes"]:
        parts.append(f"\nClasses ({len(info['classes'])}):")
        for cls in info["classes"]:
            parts.append(f"  class {cls['name']} (line {cls['line']}): {len(cls['methods'])} methods")
            for m in cls["methods"]:
                parts.append(f"    def {m}")

    if info["functions"]:
        parts.append(f"\nFunctions ({len(info['functions'])}):")
        for fn in info["functions"]:
            parts.append(f"  def {fn['name']}({fn['args']}) — line {fn['line']}")

    return ToolResult(ok=True, output="\n".join(parts))


def _file_info(p: Path):
    try:
        source = p.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except Exception:
        return None

    imports = []
    classes = []
    functions = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            imports.append(f"from {node.module} import {', '.join(a.name for a in node.names)}")

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes.append({"name": node.name, "line": node.lineno, "methods": methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = ", ".join(a.arg for a in node.args.args)
            functions.append({"name": node.name, "args": args, "line": node.lineno})

    return {
        "lines": len(source.splitlines()),
        "imports": imports,
        "classes": classes,
        "functions": functions,
    }
