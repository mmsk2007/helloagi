"""HelloAGI Live Dashboard — Terminal-based real-time monitoring.

Uses Rich Live to display:
  - Agent status and identity
  - SRG governance decisions (allow/deny/escalate counts)
  - Tool execution stats (calls, latency, failures)
  - Circuit breaker states
  - ALE cache hit rate
  - Memory and skill stats
  - Recent journal events
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    _RICH = True
except ImportError:
    _RICH = False


class DashboardStats:
    """Collects and aggregates stats from journal events for the dashboard."""

    def __init__(self, journal_path: str = "memory/events.jsonl"):
        self.journal_path = journal_path
        self.tool_calls: Dict[str, dict] = {}  # tool_name -> {calls, ok, fail, total_ms}
        self.governance: Dict[str, int] = {"allow": 0, "deny": 0, "escalate": 0}
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_requests = 0
        self.total_turns = 0
        self.recent_events: List[dict] = []
        self.started_at = time.time()

    def load_from_journal(self):
        """Parse the JSONL journal and aggregate stats."""
        p = Path(self.journal_path)
        if not p.exists():
            return

        self.tool_calls.clear()
        self.governance = {"allow": 0, "deny": 0, "escalate": 0}
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_requests = 0
        self.recent_events = []

        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            return

        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue

            kind = event.get("kind", "")

            if kind == "tool_exec":
                data = event.get("data", {})
                name = data.get("tool", "unknown")
                if name not in self.tool_calls:
                    self.tool_calls[name] = {"calls": 0, "ok": 0, "fail": 0}
                self.tool_calls[name]["calls"] += 1
                if data.get("ok"):
                    self.tool_calls[name]["ok"] += 1
                else:
                    self.tool_calls[name]["fail"] += 1

                gov = data.get("governance", "allow")
                if gov in self.governance:
                    self.governance[gov] += 1

            elif kind == "tool_denied":
                self.governance["deny"] += 1

            elif kind == "input":
                self.total_requests += 1

            elif kind == "cache_hit":
                self.cache_hits += 1

            elif kind == "response":
                data = event.get("data", {})
                self.total_turns += data.get("turns", 0)

            # Keep last 20 events for the feed
            self.recent_events.append(event)
            if len(self.recent_events) > 20:
                self.recent_events.pop(0)

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.total_requests
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100


def render_dashboard(
    agent=None,
    stats: Optional[DashboardStats] = None,
    circuit_breaker=None,
) -> str:
    """Render dashboard as plain text (fallback when Rich is not available)."""
    lines = ["=" * 60, "  HelloAGI Live Dashboard", "=" * 60, ""]

    if agent:
        lines.append(f"  Agent: {agent.identity.state.name} ({agent.identity.state.character})")
        lines.append(f"  Tools: {len(agent.tool_registry.list_tools())} | Skills: {len(agent.skills.list_skills())}")
        lines.append(f"  LLM: {'connected' if agent._claude else 'not configured'}")
        lines.append("")

    if stats:
        lines.append("  --- Governance ---")
        lines.append(f"  Allow: {stats.governance['allow']}  Deny: {stats.governance['deny']}  Escalate: {stats.governance['escalate']}")
        lines.append(f"  Requests: {stats.total_requests}  Cache Hit Rate: {stats.cache_hit_rate:.1f}%")
        lines.append("")

        if stats.tool_calls:
            lines.append("  --- Tool Stats ---")
            for name, s in sorted(stats.tool_calls.items()):
                fail_rate = (s["fail"] / s["calls"] * 100) if s["calls"] else 0
                lines.append(f"  {name:20s}  calls={s['calls']}  ok={s['ok']}  fail={s['fail']}  ({fail_rate:.0f}% fail)")
            lines.append("")

    if circuit_breaker:
        all_status = circuit_breaker.get_all_status()
        if all_status:
            lines.append("  --- Circuit Breakers ---")
            for cb in all_status:
                icon = {"closed": "🟢", "open": "🔴", "half_open": "🟡"}.get(cb["state"], "⬜")
                lines.append(f"  {icon} {cb['resource']:20s}  state={cb['state']}  failures={cb['failures']}  skipped={cb['short_circuited']}")
            lines.append("")

    if stats and stats.recent_events:
        lines.append("  --- Recent Events ---")
        for ev in stats.recent_events[-8:]:
            kind = ev.get("kind", "?")
            ts = ev.get("ts", 0)
            t = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "??:??:??"
            data_preview = str(ev.get("data", ""))[:60]
            lines.append(f"  [{t}] {kind:20s} {data_preview}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def render_rich_dashboard(
    agent=None,
    stats: Optional[DashboardStats] = None,
    circuit_breaker=None,
) -> Layout:
    """Render dashboard as Rich Layout for Live display."""
    if not _RICH:
        raise RuntimeError("Rich library required for live dashboard")

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=10),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    # Header
    header_text = Text("  HelloAGI Live Dashboard", style="bold white on blue")
    if agent:
        header_text.append(f"  |  {agent.identity.state.name}", style="bold cyan")
    layout["header"].update(Panel(header_text))

    # Left: Governance + Tool Stats
    gov_table = Table(title="SRG Governance", expand=True)
    gov_table.add_column("Decision", style="bold")
    gov_table.add_column("Count", justify="right")
    if stats:
        gov_table.add_row("🟢 Allow", str(stats.governance["allow"]))
        gov_table.add_row("🔴 Deny", str(stats.governance["deny"]))
        gov_table.add_row("🟡 Escalate", str(stats.governance["escalate"]))
        gov_table.add_row("📊 Requests", str(stats.total_requests))
        gov_table.add_row("⚡ Cache Hit", f"{stats.cache_hit_rate:.1f}%")

    tool_table = Table(title="Tool Execution", expand=True)
    tool_table.add_column("Tool")
    tool_table.add_column("Calls", justify="right")
    tool_table.add_column("OK", justify="right", style="green")
    tool_table.add_column("Fail", justify="right", style="red")
    if stats:
        for name, s in sorted(stats.tool_calls.items()):
            tool_table.add_row(name, str(s["calls"]), str(s["ok"]), str(s["fail"]))

    left_layout = Layout()
    left_layout.split_column(
        Layout(gov_table, size=9),
        Layout(tool_table),
    )
    layout["left"].update(left_layout)

    # Right: Circuit Breakers + Agent Info
    cb_table = Table(title="Circuit Breakers", expand=True)
    cb_table.add_column("Resource")
    cb_table.add_column("State")
    cb_table.add_column("Failures", justify="right")
    cb_table.add_column("Skipped", justify="right")
    if circuit_breaker:
        for cb in circuit_breaker.get_all_status():
            icon = {"closed": "🟢", "open": "🔴", "half_open": "🟡"}.get(cb["state"], "⬜")
            cb_table.add_row(cb["resource"], f"{icon} {cb['state']}", str(cb["failures"]), str(cb["short_circuited"]))

    info_table = Table(title="Agent Info", expand=True)
    info_table.add_column("Key", style="bold")
    info_table.add_column("Value")
    if agent:
        info_table.add_row("Name", agent.identity.state.name)
        info_table.add_row("Tools", str(len(agent.tool_registry.list_tools())))
        info_table.add_row("Skills", str(len(agent.skills.list_skills())))
        info_table.add_row("LLM", "connected" if agent._claude else "not configured")
        info_table.add_row("SRG", "active")

    right_layout = Layout()
    right_layout.split_column(
        Layout(info_table, size=9),
        Layout(cb_table),
    )
    layout["right"].update(right_layout)

    # Footer: Recent Events
    event_table = Table(title="Recent Events", expand=True)
    event_table.add_column("Time", style="dim", width=10)
    event_table.add_column("Kind", width=20)
    event_table.add_column("Details")
    if stats:
        for ev in stats.recent_events[-6:]:
            kind = ev.get("kind", "?")
            ts = ev.get("ts", 0)
            t = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "??:??:??"
            data_preview = str(ev.get("data", ""))[:80]

            style = "green" if kind == "response" else "red" if kind in ("deny", "tool_denied") else ""
            event_table.add_row(t, kind, data_preview, style=style)

    layout["footer"].update(Panel(event_table))

    return layout


def run_dashboard(agent=None, refresh_rate: float = 2.0):
    """Run the live dashboard in the terminal.

    Args:
        agent: HelloAGIAgent instance (optional, for live stats)
        refresh_rate: Seconds between refreshes
    """
    stats = DashboardStats()
    cb = agent.circuit_breaker if agent else None

    if _RICH:
        console = Console()
        with Live(console=console, refresh_per_second=1.0 / refresh_rate) as live:
            try:
                while True:
                    stats.load_from_journal()
                    layout = render_rich_dashboard(agent=agent, stats=stats, circuit_breaker=cb)
                    live.update(layout)
                    time.sleep(refresh_rate)
            except KeyboardInterrupt:
                console.print("\n[dim]Dashboard stopped.[/dim]")
    else:
        # Plain text fallback
        try:
            while True:
                stats.load_from_journal()
                print("\033[2J\033[H")  # Clear screen
                print(render_dashboard(agent=agent, stats=stats, circuit_breaker=cb))
                time.sleep(refresh_rate)
        except KeyboardInterrupt:
            print("\nDashboard stopped.")
