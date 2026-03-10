import argparse
from pathlib import Path

from agi_runtime.config.settings import load_settings, RuntimeSettings, save_settings
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.api.server import run_server
from agi_runtime.autonomy.loop import AutonomousLoop
from agi_runtime.workflows.graph import WorkflowGraph, WorkflowNode
from agi_runtime.orchestration.orchestrator import Orchestrator
from agi_runtime.orchestration.tri_loop import TriLoop
from agi_runtime.robustness.evaluator import evaluate_consistency


def run(goal: str, config_path: str):
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings)
    print("HelloAGI Runtime started.")
    print(f"Goal: {goal}")
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
        r = agent.think(q)
        print(f"agent[{r.decision}:{r.risk:.2f}]> {r.text}")


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


def main():
    parser = argparse.ArgumentParser(description="HelloAGI Runtime")
    sub = parser.add_subparsers(dest="cmd", required=True)

    initp = sub.add_parser("init", help="initialize config")
    initp.add_argument("--config", default="helloagi.json")

    runp = sub.add_parser("run", help="run interactive runtime")
    runp.add_argument("--goal", required=True)
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

    args = parser.parse_args()
    if args.cmd == "init":
        init_config(args.config)
    elif args.cmd == "run":
        run(args.goal, args.config)
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


if __name__ == "__main__":
    main()
