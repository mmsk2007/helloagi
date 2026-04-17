"""HelloAGI Supervisor — Failure tracking, auto-pause, and incident reporting.

Monitors agent and tool health across sessions. When failure rates exceed
thresholds, the supervisor can pause agents and generate incident reports
from journal data.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class FailureRecord:
    """Tracks failures for a single resource (agent or tool)."""
    total_failures: int = 0
    consecutive_failures: int = 0
    total_calls: int = 0
    last_failure_time: float = 0.0
    last_failure_reason: str = ""
    paused: bool = False
    paused_at: float = 0.0

    @property
    def failure_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_failures / self.total_calls

    def record_success(self):
        self.total_calls += 1
        self.consecutive_failures = 0

    def record_failure(self, reason: str = ""):
        self.total_calls += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        self.last_failure_reason = reason


@dataclass
class IncidentReport:
    """A generated incident report from failure patterns."""
    resource: str
    resource_type: str  # "tool" or "agent"
    severity: str  # "warning", "critical"
    failure_count: int
    failure_rate: float
    last_failure_reason: str
    recommendation: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "resource": self.resource,
            "type": self.resource_type,
            "severity": self.severity,
            "failures": self.failure_count,
            "failure_rate": round(self.failure_rate, 3),
            "last_reason": self.last_failure_reason,
            "recommendation": self.recommendation,
            "ts": self.timestamp,
        }


class Supervisor:
    """Monitors tool and agent health with auto-pause and incident reporting.

    Thresholds:
      - pause_consecutive: Pause after N consecutive failures (default 5)
      - pause_rate: Pause if failure rate exceeds this (default 0.5 = 50%)
      - min_calls_for_rate: Minimum calls before rate-based pausing kicks in
    """

    def __init__(
        self,
        pause_consecutive: int = 5,
        pause_rate: float = 0.5,
        min_calls_for_rate: int = 10,
    ):
        self.pause_consecutive = pause_consecutive
        self.pause_rate = pause_rate
        self.min_calls_for_rate = min_calls_for_rate
        self._tools: Dict[str, FailureRecord] = {}
        self._agents: Dict[str, FailureRecord] = {}
        self._incidents: List[IncidentReport] = []

    def _get_tool(self, name: str) -> FailureRecord:
        if name not in self._tools:
            self._tools[name] = FailureRecord()
        return self._tools[name]

    def _get_agent(self, agent_id: str) -> FailureRecord:
        if agent_id not in self._agents:
            self._agents[agent_id] = FailureRecord()
        return self._agents[agent_id]

    # ── Tool Tracking ───────────────────────────────────────────

    def record_tool_success(self, tool_name: str):
        """Record a successful tool execution."""
        rec = self._get_tool(tool_name)
        rec.record_success()

    def record_tool_failure(self, tool_name: str, reason: str = ""):
        """Record a tool failure and check if pause is needed."""
        rec = self._get_tool(tool_name)
        rec.record_failure(reason)
        self._check_tool_health(tool_name, rec)

    def _check_tool_health(self, tool_name: str, rec: FailureRecord):
        """Check if a tool should be paused based on failure patterns."""
        if rec.paused:
            return

        should_pause = False
        severity = "warning"
        recommendation = ""

        if rec.consecutive_failures >= self.pause_consecutive:
            should_pause = True
            severity = "critical"
            recommendation = (
                f"Tool '{tool_name}' has {rec.consecutive_failures} consecutive failures. "
                f"Check if the underlying service/dependency is available. "
                f"Circuit breaker should handle automatic recovery."
            )

        elif (rec.total_calls >= self.min_calls_for_rate and
              rec.failure_rate > self.pause_rate):
            should_pause = True
            severity = "warning"
            recommendation = (
                f"Tool '{tool_name}' has a {rec.failure_rate:.0%} failure rate "
                f"over {rec.total_calls} calls. Consider investigating common error patterns."
            )

        if should_pause:
            rec.paused = True
            rec.paused_at = time.time()
            incident = IncidentReport(
                resource=tool_name,
                resource_type="tool",
                severity=severity,
                failure_count=rec.total_failures,
                failure_rate=rec.failure_rate,
                last_failure_reason=rec.last_failure_reason,
                recommendation=recommendation,
            )
            self._incidents.append(incident)

    def is_tool_paused(self, tool_name: str) -> bool:
        """Check if a tool has been paused by the supervisor."""
        rec = self._tools.get(tool_name)
        return rec.paused if rec else False

    def unpause_tool(self, tool_name: str):
        """Manually unpause a tool."""
        rec = self._tools.get(tool_name)
        if rec:
            rec.paused = False
            rec.consecutive_failures = 0

    # ── Agent Tracking ──────────────────────────────────────────

    def record_failure(self, agent_id: str, reason: str = ""):
        """Record an agent-level failure."""
        rec = self._get_agent(agent_id)
        rec.record_failure(reason)

        if rec.consecutive_failures >= self.pause_consecutive and not rec.paused:
            rec.paused = True
            rec.paused_at = time.time()
            self._incidents.append(IncidentReport(
                resource=agent_id,
                resource_type="agent",
                severity="critical",
                failure_count=rec.total_failures,
                failure_rate=rec.failure_rate,
                last_failure_reason=rec.last_failure_reason,
                recommendation=f"Agent '{agent_id}' paused after {rec.consecutive_failures} consecutive failures.",
            ))

    def record_success(self, agent_id: str):
        """Record an agent-level success."""
        rec = self._get_agent(agent_id)
        rec.record_success()

    def should_pause(self, agent_id: str, threshold: int = None) -> bool:
        """Check if an agent should be paused."""
        t = threshold if threshold is not None else self.pause_consecutive
        rec = self._agents.get(agent_id)
        if not rec:
            return False
        return rec.paused or rec.consecutive_failures >= t

    # ── Incident Reports ────────────────────────────────────────

    def get_incidents(self, severity: Optional[str] = None) -> List[IncidentReport]:
        """Get incident reports, optionally filtered by severity."""
        if severity:
            return [i for i in self._incidents if i.severity == severity]
        return list(self._incidents)

    def get_incident_summary(self) -> dict:
        """Get a summary of all incidents."""
        return {
            "total_incidents": len(self._incidents),
            "critical": sum(1 for i in self._incidents if i.severity == "critical"),
            "warning": sum(1 for i in self._incidents if i.severity == "warning"),
            "paused_tools": [name for name, rec in self._tools.items() if rec.paused],
            "paused_agents": [aid for aid, rec in self._agents.items() if rec.paused],
            "incidents": [i.to_dict() for i in self._incidents[-10:]],
        }

    def generate_journal_report(self, journal_path: str = "memory/events.jsonl") -> dict:
        """Generate an incident report by analyzing the journal file."""
        p = Path(journal_path)
        if not p.exists():
            return {"error": "Journal file not found", "path": journal_path}

        tool_failures: Dict[str, int] = {}
        tool_denials: Dict[str, int] = {}
        total_events = 0
        error_events = []

        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue

                total_events += 1
                kind = event.get("kind", "")
                data = event.get("data", {})

                if kind == "tool_exec" and not data.get("ok"):
                    name = data.get("tool", "unknown")
                    tool_failures[name] = tool_failures.get(name, 0) + 1

                elif kind == "tool_denied":
                    name = data.get("tool", "unknown")
                    tool_denials[name] = tool_denials.get(name, 0) + 1

                elif kind in ("llm_error", "deny"):
                    error_events.append({
                        "kind": kind,
                        "data": str(data)[:200],
                        "ts": event.get("ts"),
                    })
        except Exception as e:
            return {"error": f"Failed to parse journal: {e}"}

        recommendations = []
        for tool, count in sorted(tool_failures.items(), key=lambda x: -x[1]):
            if count >= 3:
                recommendations.append(
                    f"Tool '{tool}' failed {count} times — check underlying service/permissions."
                )
        for tool, count in sorted(tool_denials.items(), key=lambda x: -x[1]):
            if count >= 2:
                recommendations.append(
                    f"Tool '{tool}' was denied {count} times by SRG — review governance policy if these are false positives."
                )

        return {
            "total_events": total_events,
            "tool_failures": tool_failures,
            "tool_denials": tool_denials,
            "error_events": error_events[-10:],
            "recommendations": recommendations,
        }

    # ── Status ──────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Get full supervisor status."""
        tools_status = {}
        for name, rec in self._tools.items():
            tools_status[name] = {
                "calls": rec.total_calls,
                "failures": rec.total_failures,
                "consecutive": rec.consecutive_failures,
                "failure_rate": round(rec.failure_rate, 3),
                "paused": rec.paused,
            }

        agents_status = {}
        for aid, rec in self._agents.items():
            agents_status[aid] = {
                "calls": rec.total_calls,
                "failures": rec.total_failures,
                "consecutive": rec.consecutive_failures,
                "paused": rec.paused,
            }

        return {
            "tools": tools_status,
            "agents": agents_status,
            "incidents": len(self._incidents),
        }

    def reset(self):
        """Reset all tracking data."""
        self._tools.clear()
        self._agents.clear()
        self._incidents.clear()
