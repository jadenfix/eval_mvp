"""Small coding benchmark: Python standard library + Harbor + Docker."""
import argparse
import json
import subprocess
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=Path(__file__).parent / "tasks")
    parser.add_argument("--agent", default="terminus-2")
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "runs")
    args = parser.parse_args()
    if args.agent not in {"oracle", "nop"} and not args.model:
        parser.error("--model is required for a coding agent")
    tasks = sorted(p.parent for p in args.tasks.glob("*/task.toml"))
    if not tasks:
        parser.error("--tasks must contain task folders with task.toml")

    job = "benchmark-" + uuid.uuid4().hex[:12]
    command = ["harbor", "run", "-p", str(args.tasks.resolve()),
               "-a", args.agent, "-e", "docker", "-n", "1", "-k", "1",
               "-r", "0", "-o", str(args.output.resolve()), "--job-name", job]
    if args.model:
        command += ["-m", args.model]
    try:
        execution = subprocess.run(command, check=False)
    except FileNotFoundError:
        parser.error("Install Harbor and make sure 'harbor' is on PATH")

    folder = args.output / job
    rows = []
    for path in sorted(folder.glob("*/result.json")):
        result = json.loads(path.read_text())
        error = result.get("exception_info") or {}
        reward = (result.get("verifier_result") or {}).get("rewards") or {}
        status = "pass" if reward.get("reward") == 1 else "fail"
        if error:
            status = "timeout" if error.get("exception_type") == "AgentTimeoutError" else "error"
        elif reward.get("reward") not in (0, 1):
            status = "error"
        rows.append({"task": result["task_name"], "status": status,
                     "task_checksum": result["task_checksum"], "detail": error})

    missing = max(0, len(tasks) - len(rows))
    errors = missing + sum(r["status"] == "error" for r in rows)
    passed = sum(r["status"] == "pass" for r in rows)
    report = {"agent": args.agent, "model": args.model, "tasks": len(tasks),
              "passed": passed, "errors": errors,
              "complete": execution.returncode == 0 and errors == 0,
              "score": passed / len(tasks) if execution.returncode == 0 and errors == 0 else None,
              "results": rows}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print("Evidence:", folder.resolve())
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
