import argparse
from agi_runtime.core.agent import HelloAGIAgent


def run(goal: str):
    agent = HelloAGIAgent()
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


def main():
    parser = argparse.ArgumentParser(description="HelloAGI Runtime")
    sub = parser.add_subparsers(dest="cmd", required=True)

    runp = sub.add_parser("run", help="run interactive runtime")
    runp.add_argument("--goal", required=True)

    args = parser.parse_args()
    if args.cmd == "run":
        run(args.goal)


if __name__ == "__main__":
    main()
