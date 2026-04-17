"""HelloAGI CLI — World-class terminal experience.

Rich TUI with streaming responses, tool execution panels,
SRG governance indicators, and slash commands.
"""

import argparse
import sys
from pathlib import Path

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
from agi_runtime.diagnostics.scorecard import run_scorecard
from agi_runtime.diagnostics.replay import replay_last_failure
from agi_runtime.adapters.openclaw_bridge import run_openclaw_agent

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


def _gov_icon(decision: str) -> str:
    """Get governance indicator icon."""
    return {"allow": "🟢", "escalate": "🟡", "deny": "🔴"}.get(decision, "⬜")


def _risk_bar(risk: float) -> str:
    """Visual risk bar."""
    filled = int(risk * 10)
    return "█" * filled + "░" * (10 - filled) + f" {risk:.2f}"


def run_rich(goal: str, config_path: str):
    """Run interactive session with Rich TUI."""
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings)

    if _RICH_AVAILABLE:
        console = Console()

        # Banner
        console.print(Panel(
            f"[bold cyan]HelloAGI[/bold cyan] — [dim]Governed Autonomous Intelligence[/dim]\n"
            f"[dim]Agent: {agent.identity.state.name} | {agent.identity.state.character}[/dim]\n"
            f"[dim]Tools: {len(agent.tool_registry.list_tools())} available | SRG: active[/dim]",
            title="🧠 HelloAGI Runtime",
            border_style="cyan",
        ))
        console.print(f"[dim]Goal: {goal}[/dim]")
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
        from agi_runtime.policies.packs import get_pack
        pack = get_pack("safe-default")
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

    else:
        msg = f"Unknown command: {command}. Type /help for available commands."
        if console:
            console.print(f"[red]{msg}[/red]")
        else:
            print(msg)


def run_basic(goal: str, config_path: str):
    """Basic REPL without Rich."""
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings)
    print("HelloAGI Runtime started.")
    print(f"Agent: {agent.identity.state.name} | Tools: {len(agent.tool_registry.list_tools())} available")
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


def oneshot(message: str, config_path: str):
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings)
    r = agent.think(message)
    print(r.text)


def auto(goal: str, steps: int, config_path: str):
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings)
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
    g.add_node(WorkflowNode(id="observe", title="Observe context"))
    g.add_node(WorkflowNode(id="plan", title="Plan actions", deps=["observe"]))
    g.add_node(WorkflowNode(id="execute", title="Execute safe actions", deps=["plan"]))
    done = set()
    orch = Orchestrator()
    for _ in range(3):
        ex = orch.run_once(g, done)
        if not ex:
            break
        print("executed:", ", ".join(ex))
    print("done:", ", ".join(sorted(done)))


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


def replay_failure(config_path: str):
    s = load_settings(config_path)
    rep = replay_last_failure(journal_path=s.journal_path)
    print(rep)


def openclaw(prompt: str, config_path: str):
    import anyio
    settings = load_settings(config_path)
    task = anyio.run(run_openclaw_agent, prompt, settings)
    confirm_flag = "[requires-confirm]" if task.requires_human_confirm else "[auto]"
    print(f"openclaw {confirm_flag}\n{task.summary}")


def main():
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
    sub = parser.add_subparsers(dest="cmd", required=True)

    initp = sub.add_parser("init", help="initialize config")
    initp.add_argument("--config", default="helloagi.json")

    runp = sub.add_parser("run", help="run interactive runtime (Rich TUI)")
    runp.add_argument("--goal", default="general assistant")
    runp.add_argument("--config", default="helloagi.json")

    onep = sub.add_parser("oneshot", help="single message run")
    onep.add_argument("--message", required=True)
    onep.add_argument("--config", default="helloagi.json")

    autop = sub.add_parser("auto", help="run autonomous steps")
    autop.add_argument("--goal", required=True)
    autop.add_argument("--steps", type=int, default=3)
    autop.add_argument("--config", default="helloagi.json")

    serverp = sub.add_parser("serve", help="start local HTTP API")
    serverp.add_argument("--host", default="127.0.0.1")
    serverp.add_argument("--port", type=int, default=8787)

    docp = sub.add_parser("doctor", help="check local runtime state")
    docp.add_argument("--config", default="helloagi.json")

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

    # New commands
    toolsp = sub.add_parser("tools", help="list available tools")
    skillsp = sub.add_parser("skills", help="list learned skills")

    args = parser.parse_args()

    if args.cmd == "init":
        init_config(args.config)
    elif args.cmd == "run":
        run_rich(args.goal, args.config)
    elif args.cmd == "oneshot":
        oneshot(args.message, args.config)
    elif args.cmd == "auto":
        auto(args.goal, args.steps, args.config)
    elif args.cmd == "serve":
        run_server(args.host, args.port)
    elif args.cmd == "doctor":
        doctor(args.config)
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
        openclaw(args.prompt, args.config)
    elif args.cmd == "tools":
        from agi_runtime.tools.registry import ToolRegistry, discover_builtin_tools
        discover_builtin_tools()
        agent = HelloAGIAgent()
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


if __name__ == "__main__":
    main()
