"""HelloAGI CLI — World-class terminal experience.

Rich TUI with streaming responses, tool execution panels,
SRG governance indicators, and slash commands.
"""

import argparse
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from agi_runtime.config.env import load_local_env
from agi_runtime.config.settings import load_settings, RuntimeSettings, save_settings
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.api.server import run_server
from agi_runtime.autonomy.loop import AutonomousLoop
from agi_runtime.workflows.graph import WorkflowGraph, WorkflowNode
from agi_runtime.orchestration.orchestrator import Orchestrator
from agi_runtime.orchestration.tri_loop import TriLoop
from agi_runtime.robustness.evaluator import evaluate_consistency
from agi_runtime.onboarding.wizard import run_wizard, status as onboard_status
from agi_runtime.storage.migrations import MigrationRunner
from agi_runtime.storage.sqlite_store import SQLiteStore
from agi_runtime.diagnostics.health import run_health
from agi_runtime.diagnostics.scorecard import run_scorecard
from agi_runtime.diagnostics.replay import replay_last_failure
from agi_runtime.adapters.openclaw_bridge import run_openclaw_agent
from agi_runtime.migration.importer import MigrationImporter
from agi_runtime.service.manager import ServiceManager

# Try to import Rich for enhanced display
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.markdown import Markdown
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.syntax import Syntax
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False


def _configure_stdio():
    """Avoid Unicode crashes on legacy Windows terminals."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="replace")
            except Exception:
                pass


def _run_pip_command(args: list[str]) -> int:
    """Run pip through the active Python interpreter."""
    return subprocess.run([sys.executable, "-m", "pip", *args]).returncode


def _gov_icon(decision: str) -> str:
    """Get governance indicator icon."""
    return {"allow": "🟢", "escalate": "🟡", "deny": "🔴"}.get(decision, "⬜")


def _risk_bar(risk: float) -> str:
    """Visual risk bar."""
    filled = int(risk * 10)
    return "█" * filled + "░" * (10 - filled) + f" {risk:.2f}"


def run_rich(goal: str, config_path: str, policy_pack: str = "safe-default"):
    """Run interactive session with Rich TUI."""
    # Auto-onboard on first run
    from agi_runtime.onboarding.wizard import is_onboarded, run_wizard
    if not is_onboarded():
        run_wizard()

    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings, policy_pack=policy_pack)

    if _RICH_AVAILABLE:
        console = Console()

        # Banner with inspirational quote
        from agi_runtime.onboarding.quotes import get_random_quote
        quote, source = get_random_quote()

        console.print(Panel(
            f"[bold cyan]HelloAGI[/bold cyan] — [dim]Governed Autonomous Intelligence[/dim]\n"
            f"[dim]Agent: {agent.identity.state.name} | {agent.identity.state.character}[/dim]\n"
            f"[dim]Tools: {len(agent._list_allowed_tools())} available | SRG: {agent.policy_pack.name}[/dim]\n\n"
            f"[dim italic magenta]\"{quote}\"[/dim italic magenta]\n"
            f"[dim italic]  — {source}[/dim italic]",
            title="🧠 HelloAGI Runtime",
            border_style="cyan",
        ))
        # Growth tracking
        from agi_runtime.core.personality import get_time_greeting
        greeting, energy, icon = get_time_greeting()
        streak_msg = agent.growth.get_streak_message()
        console.print(f"[dim]{icon} {greeting}[/dim]")
        console.print(f"[dim]{streak_msg}[/dim]")
        console.print(f"[dim]Type /help for commands, /tools to see tools, exit to quit[/dim]\n")

        # Set up tool execution callbacks
        def on_tool_start(name, input_data, decision):
            icon = _gov_icon(decision)
            console.print(f"  {icon} [bold yellow]⚡ {name}[/bold yellow] [dim]({decision})[/dim]", end="")

        def on_tool_end(name, ok, output):
            status = "[green]✓[/green]" if ok else "[red]✗[/red]"
            preview = output[:80].replace("\n", " ") if output else ""
            console.print(f" {status} [dim]{preview}[/dim]")

        agent.on_tool_start = on_tool_start
        agent.on_tool_end = on_tool_end

        while True:
            try:
                q = console.input("[bold green]you>[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]bye[/dim]")
                break

            if not q:
                continue
            if q in {"exit", "quit"}:
                console.print("[dim]bye[/dim]")
                break

            # Slash commands
            if q.startswith("/"):
                _handle_slash_command(q, agent, console)
                continue

            # Think with spinner
            with console.status("[bold cyan]Thinking...[/bold cyan]", spinner="dots"):
                r = agent.think(q)

            # Display response
            gov_icon = _gov_icon(r.decision)
            header = f"{gov_icon} [{r.decision}:{r.risk:.2f}]"
            if r.tool_calls_made > 0:
                header += f" | {r.tool_calls_made} tool calls in {r.turns_used} turns"

            console.print(f"\n[dim]{header}[/dim]")

            # Try to render as markdown
            try:
                console.print(Markdown(r.text))
            except Exception:
                console.print(r.text)
            console.print()

    else:
        # Fallback to basic REPL
        run_basic(goal, config_path)


def _handle_slash_command(cmd: str, agent: HelloAGIAgent, console=None):
    """Handle slash commands."""
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/help":
        help_text = (
            "[bold]Available Commands:[/bold]\n"
            "  /tools     — List available tools with risk levels\n"
            "  /skills    — List learned skills\n"
            "  /identity  — Show agent identity and principles\n"
            "  /memory    — Show memory stats\n"
            "  /new       — Start fresh conversation\n"
            "  /policy    — Show current governance policy\n"
            "  /packs     — List available policy packs\n"
            "  /growth    — Show your growth stats and streaks\n"
            "  /mood      — Show mood tracking and emotional intelligence\n"
            "  /patterns  — Show detected behavioral patterns\n"
            "  /dashboard — Show live monitoring dashboard\n"
            "  /supervisor— Show supervisor health status\n"
            "  /circuits  — Show circuit breaker states\n"
            "  /help      — Show this help\n"
            "  exit       — Quit\n"
        )
        if _RICH_AVAILABLE and console:
            console.print(Panel(help_text, title="Help", border_style="blue"))
        else:
            print(help_text)

    elif command == "/tools":
        info = agent.get_tools_info()
        if _RICH_AVAILABLE and console:
            console.print(Panel(info, title="Available Tools", border_style="green"))
        else:
            print(info)

    elif command == "/skills":
        from agi_runtime.skills.manager import SkillManager
        sm = SkillManager()
        skills = sm.list_skills()
        if skills:
            for s in skills:
                line = f"  {s.name}: {s.description} (used {s.invoke_count}x)"
                if console:
                    console.print(line)
                else:
                    print(line)
        else:
            msg = "No skills learned yet. Complete complex tasks to crystallize skills."
            if console:
                console.print(f"[dim]{msg}[/dim]")
            else:
                print(msg)

    elif command == "/identity":
        state = agent.identity.state
        info = (
            f"Name: {state.name}\n"
            f"Character: {state.character}\n"
            f"Purpose: {state.purpose}\n"
            f"Principles:\n" + "\n".join(f"  - {p}" for p in state.principles)
        )
        if _RICH_AVAILABLE and console:
            console.print(Panel(info, title="Agent Identity", border_style="magenta"))
        else:
            print(info)

    elif command == "/memory":
        try:
            from agi_runtime.memory.embeddings import GeminiEmbeddingStore
            store = GeminiEmbeddingStore()
            msg = f"Semantic memory: {store.count()} entries | Available: {store.available}"
        except Exception:
            msg = "Semantic memory: not configured"
        if console:
            console.print(f"[dim]{msg}[/dim]")
        else:
            print(msg)

    elif command == "/new":
        agent.clear_history()
        msg = "Conversation cleared. Fresh session started."
        if console:
            console.print(f"[green]{msg}[/green]")
        else:
            print(msg)

    elif command == "/policy":
        pack = agent.policy_pack
        info = (
            f"Active policy: {pack.name}\n"
            f"Deny keywords: {', '.join(pack.deny_keywords)}\n"
            f"Escalate keywords: {', '.join(pack.escalate_keywords)}\n"
        )
        if console:
            console.print(Panel(info, title="Governance Policy", border_style="red"))
        else:
            print(info)

    elif command == "/packs":
        from agi_runtime.policies.packs import list_packs
        for p in list_packs():
            line = f"  {p.name}: {p.description}"
            if console:
                console.print(line)
            else:
                print(line)

    elif command == "/growth":
        summary = agent.growth.get_growth_summary()
        streak_msg = agent.growth.get_streak_message()
        info = f"{streak_msg}\n\n{summary}"
        if _RICH_AVAILABLE and console:
            console.print(Panel(info, title="Your Growth", border_style="green"))
        else:
            print(info)

    elif command == "/mood":
        summary = agent.sentiment.get_summary()
        guidance = agent.sentiment.get_mood_guidance()
        info = summary
        if guidance:
            info += f"\n\nGuidance: {guidance}"
        if _RICH_AVAILABLE and console:
            console.print(Panel(info, title="Mood & Emotional Intelligence", border_style="magenta"))
        else:
            print(info)

    elif command == "/patterns":
        insights = agent.patterns.get_insights()
        if _RICH_AVAILABLE and console:
            console.print(Panel(insights, title="Behavioral Patterns", border_style="blue"))
        else:
            print(insights)

    elif command == "/dashboard":
        from agi_runtime.diagnostics.dashboard import DashboardStats, render_dashboard
        stats = DashboardStats()
        stats.load_from_journal()
        output = render_dashboard(agent=agent, stats=stats, circuit_breaker=agent.circuit_breaker)
        if console:
            console.print(output)
        else:
            print(output)

    elif command == "/supervisor":
        status = agent.supervisor.get_status()
        incident_summary = agent.supervisor.get_incident_summary()
        info = (
            f"Incidents: {incident_summary['total_incidents']} "
            f"(critical: {incident_summary['critical']}, warning: {incident_summary['warning']})\n"
            f"Paused tools: {', '.join(incident_summary['paused_tools']) or 'none'}\n"
            f"Paused agents: {', '.join(incident_summary['paused_agents']) or 'none'}"
        )
        if status["tools"]:
            info += "\n\nTool Health:"
            for name, ts in sorted(status["tools"].items()):
                info += f"\n  {name}: {ts['calls']} calls, {ts['failures']} failures ({ts['failure_rate']:.0%})"
        if _RICH_AVAILABLE and console:
            console.print(Panel(info, title="Supervisor Status", border_style="yellow"))
        else:
            print(info)

    elif command == "/circuits":
        all_cb = agent.circuit_breaker.get_all_status()
        if all_cb:
            lines = []
            for cb in all_cb:
                icon = {"closed": "🟢", "open": "🔴", "half_open": "🟡"}.get(cb["state"], "⬜")
                lines.append(f"  {icon} {cb['resource']}: {cb['state']} (failures={cb['failures']}, skipped={cb['short_circuited']})")
            output = "\n".join(lines)
        else:
            output = "No circuit breakers active yet."
        if _RICH_AVAILABLE and console:
            console.print(Panel(output, title="Circuit Breakers", border_style="cyan"))
        else:
            print(output)

    else:
        msg = f"Unknown command: {command}. Type /help for available commands."
        if console:
            console.print(f"[red]{msg}[/red]")
        else:
            print(msg)


def run_basic(goal: str, config_path: str, policy_pack: str = "safe-default"):
    """Basic REPL without Rich."""
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings, policy_pack=policy_pack)
    print("HelloAGI Runtime started.")
    print(f"Agent: {agent.identity.state.name} | Policy: {agent.policy_pack.name} | Tools: {len(agent._list_allowed_tools())} available")
    print(f"Goal: {goal}")
    print("Type /help for commands, exit to quit\n")

    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not q:
            continue
        if q in {"exit", "quit"}:
            print("bye")
            break

        if q.startswith("/"):
            _handle_slash_command(q, agent)
            continue

        r = agent.think(q)
        gov_icon = _gov_icon(r.decision)
        header = f"{gov_icon} [{r.decision}:{r.risk:.2f}]"
        if r.tool_calls_made > 0:
            header += f" | {r.tool_calls_made} tool calls in {r.turns_used} turns"
        print(f"{header}")
        print(r.text)
        print()


# Alias for backward compatibility
run = run_basic


def init_config(path: str):
    s = RuntimeSettings()
    save_settings(s, path)
    print(f"Initialized config at {path}")


def oneshot(message: str, config_path: str, policy_pack: str = "safe-default"):
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings, policy_pack=policy_pack)
    r = agent.think(message)
    print(r.text)


def auto(goal: str, steps: int, config_path: str, policy_pack: str = "safe-default"):
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings, policy_pack=policy_pack)
    loop = AutonomousLoop(agent, goal)
    results = loop.run_steps(steps=steps)
    for i, r in enumerate(results, start=1):
        print(f"step {i}: [{r.decision}:{r.risk:.2f}] {r.text}")


def doctor(config_path: str):
    p = Path(config_path)
    print(f"Config exists: {p.exists()} ({config_path})")
    s = load_settings(config_path)
    print(f"Identity file: {s.memory_path}")
    print(f"Journal file: {s.journal_path}")
    print(f"DB file: {s.db_path}")


def orchestrate_demo():
    g = WorkflowGraph()
    g.add_node(WorkflowNode(id="observe", title="Observe context", kind="task", prompt="Observation complete"))
    g.add_node(WorkflowNode(id="plan", title="Plan actions", deps=["observe"], kind="task", prompt="Plan complete"))
    g.add_node(WorkflowNode(id="execute", title="Execute safe actions", deps=["plan"], kind="verification", prompt="Execution reviewed"))
    orch = Orchestrator()
    result = orch.run_until_complete(g, title="demo workflow")
    print(result)


def tri_loop(goal: str):
    result = TriLoop().run(goal)
    print(f"tri-loop ok={result.ok} :: {result.summary}")


def benchmark_robustness(text: str):
    rep = evaluate_consistency(text)
    print(f"consistency={rep.consistency:.2f}")
    print(f"noisy={rep.noisy_text}")
    print(f"recovered={rep.recovered_text}")


def db_init(config_path: str):
    s = load_settings(config_path)
    runner = MigrationRunner(db_path=s.db_path, migrations_dir="src/agi_runtime/storage/migrations")
    runner.run()
    print(f"db initialized: {s.db_path}")


def db_demo(config_path: str):
    s = load_settings(config_path)
    runner = MigrationRunner(db_path=s.db_path, migrations_dir="src/agi_runtime/storage/migrations")
    runner.run()
    store = SQLiteStore(s.db_path)
    sid = store.create_session(owner_name="demo")
    tid = store.create_task(sid, "Ship HelloAGI")
    store.update_task_status(tid, "done")
    tasks = store.list_tasks(sid)
    print({"session_id": sid, "tasks": tasks})


def doctor_score(config_path: str, onboard_path: str):
    rep = run_scorecard(config_path=config_path, onboard_path=onboard_path)
    print(rep)


def health(config_path: str, onboard_path: str):
    rep = run_health(config_path=config_path, onboard_path=onboard_path)
    print(rep)


def replay_failure(config_path: str):
    s = load_settings(config_path)
    rep = replay_last_failure(journal_path=s.journal_path)
    print(rep)


def service_install(args):
    cfg = ServiceManager().install(
        host=args.host,
        port=args.port,
        config_path=args.config,
        policy_pack=args.policy,
        telegram=args.telegram,
        discord=args.discord,
    )
    print({"installed": cfg.installed, "host": cfg.host, "port": cfg.port, "policy_pack": cfg.policy_pack})


def service_start():
    cfg = ServiceManager().start()
    print({"running": True, "pid": cfg.pid, "host": cfg.host, "port": cfg.port})


def service_stop():
    cfg = ServiceManager().stop()
    print({"running": False, "host": cfg.host, "port": cfg.port})


def service_status():
    print(ServiceManager().status())


def service_uninstall():
    cfg = ServiceManager().uninstall()
    print({"installed": cfg.installed, "running": False})


def migrate(source: str, path: str = None, apply: bool = False):
    importer = MigrationImporter()
    report = importer.apply(source, path) if apply else importer.preview(source, path)
    print(asdict(report))


def openclaw(prompt: str, config_path: str, policy_pack: str = "safe-default"):
    import anyio
    settings = load_settings(config_path)
    task = anyio.run(run_openclaw_agent, prompt, settings, policy_pack)
    confirm_flag = "[requires-confirm]" if task.requires_human_confirm else "[auto]"
    print(f"openclaw {confirm_flag}\n{task.summary}")


def update_installation(package: str = "helloagi[rich,telegram]"):
    """Update HelloAGI in the current Python environment."""
    print(f"Updating {package}...")
    raise SystemExit(_run_pip_command(["install", "--user", "--upgrade", package]))


def uninstall_installation(yes: bool = False):
    """Uninstall HelloAGI from the current Python environment."""
    if not yes:
        print("Refusing to uninstall without --yes.")
        print("Run: helloagi uninstall --yes")
        raise SystemExit(2)

    print("Uninstalling helloagi...")
    raise SystemExit(_run_pip_command(["uninstall", "-y", "helloagi"]))


def _serve_with_channels(args):
    """Start HTTP API with optional Telegram/Discord channels."""
    import asyncio
    settings = load_settings(args.config)
    agent = HelloAGIAgent(settings, policy_pack=args.policy)

    from agi_runtime.channels.router import ChannelRouter
    router = ChannelRouter(agent)

    if args.telegram:
        try:
            from agi_runtime.channels.telegram import TelegramChannel
            tg = TelegramChannel(agent)
            router.register(tg)
            print("Telegram channel registered")
        except Exception as e:
            print(f"Telegram channel failed: {e}")

    if args.discord:
        try:
            from agi_runtime.channels.discord import DiscordChannel
            dc = DiscordChannel(agent)
            router.register(dc)
            print("Discord channel registered")
        except Exception as e:
            print(f"Discord channel failed: {e}")

    # Start HTTP server in a thread, channels via asyncio
    import threading
    from agi_runtime.api.server import HelloAGIHandler, ThreadedHTTPServer
    import os

    HelloAGIHandler.agent = agent
    HelloAGIHandler.api_key = os.environ.get("HELLOAGI_API_KEY")
    srv = ThreadedHTTPServer((args.host, args.port), HelloAGIHandler)

    http_thread = threading.Thread(target=srv.serve_forever, daemon=True)
    http_thread.start()
    print(f"HTTP API listening on http://{args.host}:{args.port}")

    # Start channels
    try:
        asyncio.run(router.start_all())
    except KeyboardInterrupt:
        print("\nShutting down...")
        srv.shutdown()


def main():
    _configure_stdio()
    load_local_env()
    parser = argparse.ArgumentParser(
        description="HelloAGI — Governed Autonomous Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  helloagi run --goal 'Build a web scraper'\n"
            "  helloagi oneshot --message 'What tools do you have?'\n"
            "  helloagi auto --goal 'Research AI agents' --steps 5\n"
            "  helloagi serve --port 8787\n"
        ),
    )
    sub = parser.add_subparsers(dest="cmd")

    initp = sub.add_parser("init", help="initialize config")
    initp.add_argument("--config", default="helloagi.json")

    runp = sub.add_parser("run", help="run interactive runtime (Rich TUI)")
    runp.add_argument("--goal", default="general assistant")
    runp.add_argument("--config", default="helloagi.json")
    runp.add_argument("--policy", default="safe-default")

    onep = sub.add_parser("oneshot", help="single message run")
    onep.add_argument("--message", required=True)
    onep.add_argument("--config", default="helloagi.json")
    onep.add_argument("--policy", default="safe-default")

    autop = sub.add_parser("auto", help="run autonomous steps")
    autop.add_argument("--goal", required=True)
    autop.add_argument("--steps", type=int, default=3)
    autop.add_argument("--config", default="helloagi.json")
    autop.add_argument("--policy", default="safe-default")

    serverp = sub.add_parser("serve", help="start local HTTP API")
    serverp.add_argument("--host", default="127.0.0.1")
    serverp.add_argument("--port", type=int, default=8787)
    serverp.add_argument("--telegram", action="store_true", help="also start Telegram bot")
    serverp.add_argument("--discord", action="store_true", help="also start Discord bot")
    serverp.add_argument("--config", default="helloagi.json")
    serverp.add_argument("--policy", default="safe-default")

    docp = sub.add_parser("doctor", help="check local runtime state")
    docp.add_argument("--config", default="helloagi.json")

    healthp = sub.add_parser("health", help="run full local health checks")
    healthp.add_argument("--config", default="helloagi.json")
    healthp.add_argument("--onboard", default="helloagi.onboard.json")

    updatep = sub.add_parser("update", help="update HelloAGI in the current Python environment")
    updatep.add_argument("--package", default="helloagi[rich,telegram]")

    uninstallp = sub.add_parser("uninstall", help="uninstall HelloAGI from the current Python environment")
    uninstallp.add_argument("--yes", action="store_true", help="confirm uninstall")

    servicep = sub.add_parser("service", help="manage local HelloAGI background service")
    service_sub = servicep.add_subparsers(dest="service_cmd")
    service_installp = service_sub.add_parser("install", help="install local service config")
    service_installp.add_argument("--host", default="127.0.0.1")
    service_installp.add_argument("--port", type=int, default=8787)
    service_installp.add_argument("--config", default="helloagi.json")
    service_installp.add_argument("--policy", default="safe-default")
    service_installp.add_argument("--telegram", action="store_true")
    service_installp.add_argument("--discord", action="store_true")
    service_sub.add_parser("start", help="start local background service")
    service_sub.add_parser("stop", help="stop local background service")
    service_sub.add_parser("status", help="show local background service status")
    service_sub.add_parser("uninstall", help="remove local background service config")

    migratep = sub.add_parser("migrate", help="import config and secrets from another agent runtime")
    migratep.add_argument("--source", choices=["openclaw", "hermes"], required=True)
    migratep.add_argument("--path", default=None)
    migratep.add_argument("--apply", action="store_true", help="apply the import instead of preview only")

    sub.add_parser("orchestrate-demo", help="run orchestration DAG demo")
    tri = sub.add_parser("tri-loop", help="run planner/executor/verifier loop")
    tri.add_argument("--goal", required=True)

    rb = sub.add_parser("benchmark-robustness", help="run noisecore robustness check")
    rb.add_argument("--text", required=True)

    onboard = sub.add_parser("onboard", help="run local onboarding wizard")
    onboard.add_argument("--path", default="helloagi.onboard.json")

    obstat = sub.add_parser("onboard-status", help="show onboarding status")
    obstat.add_argument("--path", default="helloagi.onboard.json")

    dbi = sub.add_parser("db-init", help="initialize sqlite state database")
    dbi.add_argument("--config", default="helloagi.json")

    dbd = sub.add_parser("db-demo", help="run sqlite state demo")
    dbd.add_argument("--config", default="helloagi.json")

    ds = sub.add_parser("doctor-score", help="readiness scorecard")
    ds.add_argument("--config", default="helloagi.json")
    ds.add_argument("--onboard", default="helloagi.onboard.json")

    rf = sub.add_parser("replay-failure", help="replay last failure context from journal")
    rf.add_argument("--config", default="helloagi.json")

    oc = sub.add_parser("openclaw", help="run governed openclaw agent (Claude Agent SDK)")
    oc.add_argument("--prompt", required=True, help="prompt for the openclaw agent")
    oc.add_argument("--config", default="helloagi.json")
    oc.add_argument("--policy", default="safe-default")

    # New commands
    toolsp = sub.add_parser("tools", help="list available tools")
    toolsp.add_argument("--policy", default="safe-default")
    skillsp = sub.add_parser("skills", help="list learned skills")
    dashp = sub.add_parser("dashboard", help="live monitoring dashboard")
    dashp.add_argument("--config", default="helloagi.json")
    dashp.add_argument("--policy", default="safe-default")

    args = parser.parse_args()

    # Default: no subcommand → run interactive session
    if not args.cmd:
        run_rich("general assistant", "helloagi.json")
        return

    if args.cmd == "init":
        init_config(args.config)
    elif args.cmd == "run":
        run_rich(args.goal, args.config, args.policy)
    elif args.cmd == "oneshot":
        oneshot(args.message, args.config, args.policy)
    elif args.cmd == "auto":
        auto(args.goal, args.steps, args.config, args.policy)
    elif args.cmd == "serve":
        if args.telegram or args.discord:
            _serve_with_channels(args)
        else:
            run_server(args.host, args.port, getattr(args, "config", "helloagi.json"), args.policy)
    elif args.cmd == "doctor":
        doctor(args.config)
    elif args.cmd == "health":
        health(args.config, args.onboard)
    elif args.cmd == "update":
        update_installation(args.package)
    elif args.cmd == "uninstall":
        uninstall_installation(args.yes)
    elif args.cmd == "service":
        if args.service_cmd == "install":
            service_install(args)
        elif args.service_cmd == "start":
            service_start()
        elif args.service_cmd == "stop":
            service_stop()
        elif args.service_cmd == "status":
            service_status()
        elif args.service_cmd == "uninstall":
            service_uninstall()
        else:
            parser.error("service requires a subcommand: install, start, stop, status, uninstall")
    elif args.cmd == "migrate":
        migrate(args.source, args.path, args.apply)
    elif args.cmd == "orchestrate-demo":
        orchestrate_demo()
    elif args.cmd == "tri-loop":
        tri_loop(args.goal)
    elif args.cmd == "benchmark-robustness":
        benchmark_robustness(args.text)
    elif args.cmd == "onboard":
        run_wizard(args.path)
    elif args.cmd == "onboard-status":
        onboard_status(args.path)
    elif args.cmd == "db-init":
        db_init(args.config)
    elif args.cmd == "db-demo":
        db_demo(args.config)
    elif args.cmd == "doctor-score":
        doctor_score(args.config, args.onboard)
    elif args.cmd == "replay-failure":
        replay_failure(args.config)
    elif args.cmd == "openclaw":
        openclaw(args.prompt, args.config, args.policy)
    elif args.cmd == "tools":
        from agi_runtime.tools.registry import ToolRegistry, discover_builtin_tools
        discover_builtin_tools()
        agent = HelloAGIAgent(policy_pack=args.policy)
        print(agent.get_tools_info())
    elif args.cmd == "skills":
        from agi_runtime.skills.manager import SkillManager
        sm = SkillManager()
        skills = sm.list_skills()
        if skills:
            for s in skills:
                print(f"  {s.name}: {s.description} (used {s.invoke_count}x)")
        else:
            print("No skills learned yet.")
    elif args.cmd == "dashboard":
        from agi_runtime.diagnostics.dashboard import run_dashboard
        settings = load_settings(args.config)
        agent = HelloAGIAgent(settings, policy_pack=args.policy)
        run_dashboard(agent=agent)


if __name__ == "__main__":
    main()
