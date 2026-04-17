"""Execute Python code in an isolated subprocess."""

import subprocess
import sys
import tempfile
from pathlib import Path

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="python_exec",
    description="Execute Python code in an isolated subprocess. Returns stdout, stderr, and exit code. Code is screened by SRG governance.",
    toolset="code",
    risk="high",
    parameters=[
        ToolParam("code", "string", "Python code to execute"),
        ToolParam("timeout", "integer", "Timeout in seconds (default 30)", required=False, default=30),
    ],
)
def python_exec(code: str, timeout: int = 30) -> ToolResult:
    try:
        # Write code to a temp file for clean execution
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"[stderr] {result.stderr}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        if len(output) > 50000:
            output = output[:50000] + "\n... (truncated)"

        if result.returncode != 0:
            output = f"[exit code {result.returncode}]\n{output}"

        return ToolResult(ok=result.returncode == 0, output=output)

    except subprocess.TimeoutExpired:
        Path(tmp_path).unlink(missing_ok=True)
        return ToolResult(ok=False, output="", error=f"Code execution timed out after {timeout}s")
    except Exception as e:
        return ToolResult(ok=False, output="", error=str(e))
