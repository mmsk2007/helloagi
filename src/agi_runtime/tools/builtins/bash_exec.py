"""Execute shell commands with SRG governance pre-screening."""

import subprocess
import platform

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="bash_exec",
    description="Execute a shell command and return stdout/stderr. Commands are screened by SRG governance before execution.",
    toolset="system",
    risk="high",
    parameters=[
        ToolParam("command", "string", "The shell command to execute"),
        ToolParam("timeout", "integer", "Timeout in seconds (default 30)", required=False, default=30),
        ToolParam("working_dir", "string", "Working directory for the command", required=False),
    ],
)
def bash_exec(command: str, timeout: int = 30, working_dir: str = None) -> ToolResult:
    try:
        shell = True
        if platform.system() == "Windows":
            shell_cmd = command
        else:
            shell_cmd = command

        result = subprocess.run(
            shell_cmd,
            shell=shell,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=working_dir,
        )

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"[stderr] {result.stderr}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        # Truncate very large outputs
        if len(output) > 50000:
            output = output[:50000] + "\n... (truncated, output too large)"

        if result.returncode != 0:
            output = f"[exit code {result.returncode}]\n{output}"

        return ToolResult(ok=result.returncode == 0, output=output)

    except subprocess.TimeoutExpired:
        return ToolResult(ok=False, output="", error=f"Command timed out after {timeout}s")
    except Exception as e:
        return ToolResult(ok=False, output="", error=str(e))
