"""A small, local coding benchmark. Requires Harbor 0.23.0 and Docker."""
import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path
from grader import cases

ROOT = Path(__file__).resolve().parent


def digest(paths, root=ROOT):
    hash_ = hashlib.sha256()
    for path in sorted(paths):
        hash_.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes())
    return hash_.hexdigest()


def execute(command, deadline, capture=False):
    process = subprocess.Popen(command, start_new_session=True,
                               stdout=subprocess.PIPE if capture else None, text=True)
    try:
        output, _ = process.communicate(timeout=max(0.01, deadline - time.monotonic()))
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    if process.returncode:
        raise RuntimeError(f"Command failed ({process.returncode}): {command[0]}")
    return (output or "").strip()


def prepare(source, target, config, run_id, deadline):
    """Assemble a Harbor task; solutions and tests never enter the agent image."""
    target.mkdir(parents=True)
    shutil.copy(source / "instruction.md", target)
    shutil.copytree(source / "start", target / "environment")
    shutil.copy(ROOT / "agent.Dockerfile", target / "environment/Dockerfile")
    shutil.copytree(source / "solution", target / "solution")
    (target / "solution/solve.sh").write_text("#!/bin/sh\ncp /solution/*.py /app/\n")
    tests = target / "tests"
    tests.mkdir()
    shutil.copy(ROOT / "grader.py", tests / "grade.py")
    shutil.copy(ROOT / "verifier.Dockerfile", tests / "Dockerfile")
    (tests / "kind.txt").write_text(source.name)
    (tests / "test.sh").write_text("#!/bin/sh\nexec python -I /tests/grade.py\n")
    images = {}
    for role, directory in [("agent", target / "environment"), ("verifier", tests)]:
        images[role] = execute(["docker", "build", "-q", str(directory)], deadline, True)
        # Runtime labels are added after building; they do not alter image contents.
        (directory / "docker-compose.yaml").write_text(
            f"services:\n  main:\n    network_mode: none\n    labels:\n      eval_mvp.run: {run_id}\n")
    (target / "task.toml").write_text(
        'schema_version = "1.4"\nartifacts = ["/app"]\n'
        f'[agent]\ntimeout_sec = {config["agent_seconds"]}\n'
        '[environment]\nnetwork_mode = "public"\nbuild_timeout_sec = 300\n'
        f'docker_image = "{images["agent"]}"\n'
        f'cpus = {config["cpus"]}\nmemory_mb = {config["memory_mb"]}\n'
        '[verifier]\nenvironment_mode = "separate"\n'
        f'timeout_sec = {config["verifier_seconds"]}\n'
        '[verifier.environment]\nnetwork_mode = "public"\n'
        f'docker_image = "{images["verifier"]}"\n'
        f'cpus = {config["cpus"]}\nmemory_mb = {config["memory_mb"]}\n')
    return images


def trial_status(result, trial, expected_checks=None):
    error = result.get("exception_info")
    if error:
        return "timeout" if error.get("exception_type") == "AgentTimeoutError" else "error"
    if result.get("verifier_environment_mode") != "separate":
        return "error"
    reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    checks = json.loads((trial / "verifier/checks.json").read_text())
    recorded = float((trial / "verifier/reward.txt").read_text())
    if (not checks or (expected_checks is not None and len(checks) != expected_checks)
            or [row["case"] for row in checks] != list(range(len(checks)))
            or any(type(row.get("passed")) is not bool for row in checks)
            or reward not in (0, 1) or recorded != reward
            or reward != int(all(row["passed"] for row in checks))):
        return "error"
    return "pass" if reward == 1 else "fail"


def job(tasks, agent, attempts, config, folder, deadline, model=None):
    files = [p for p in tasks.rglob("*") if p.is_file()]
    before = digest(files, tasks)
    name = agent + "-" + uuid.uuid4().hex[:8]
    command = ["harbor", "run", "-p", str(tasks), "-a", agent, "-e", "docker",
               "-n", "1", "-k", str(attempts), "-r", "0", "-o", str(folder / "jobs"),
               "--job-name", name]
    if model:
        command += ["-m", model]
        for key, value in config["agent_kwargs"].items():
            command += ["--ak", f"{key}={json.dumps(value)}"]
    execute(command, deadline)
    counts = {task.name: 0 for task in tasks.iterdir() if (task / "task.toml").exists()}
    rows = []
    seen = set()
    for path in sorted((folder / "jobs" / name).glob("*/result.json")):
        try:
            result = json.loads(path.read_text())
            task = result["task_name"]
            identity = result["id"]
            if (task not in counts or counts[task] >= attempts or identity in seen
                    or result["trial_name"] != path.parent.name
                    or Path(result["config"]["task"]["path"]).resolve() != (tasks / task).resolve()):
                raise ValueError("unexpected or duplicate task result")
            seen.add(identity)
            counts[task] += 1
            rows.append({"task": task, "attempt": counts[task],
                         "status": trial_status(result, path.parent, sum(1 for _ in cases(task))),
                         "trial_id": identity,
                         "task_checksum": result["task_checksum"],
                         "agent_info": result["agent_info"],
                         "evidence": str(path.relative_to(folder))})
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            rows.append({"task": path.parent.name, "status": "error"})
    for task, count in counts.items():
        rows.extend({"task": task, "status": "error", "detail": "missing result"}
                    for _ in range(attempts - count))
    if digest([p for p in tasks.rglob("*") if p.is_file()], tasks) != before:
        rows.append({"task": "snapshot", "status": "error", "detail": "task changed during execution"})
    return rows


def cleanup(run_id):
    ids = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=eval_mvp.run={run_id}"],
                         capture_output=True, text=True, check=True, timeout=30)
    if ids.stdout.split():
        subprocess.run(["docker", "rm", "-f", *ids.stdout.split()], check=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--model", help="Harbor/LiteLLM model identifier; credentials stay in the environment")
    parser.add_argument("--deadline", type=int, default=3600, help="whole-run time limit in seconds")
    args = parser.parse_args()
    if args.deadline <= 0 or (not args.check and not args.model):
        parser.error("use --check or supply --model; --deadline must be positive")
    deadline = time.monotonic() + args.deadline
    config = json.loads((ROOT / "benchmark.json").read_text())
    version = execute(["harbor", "--version"], deadline, True)
    if version != config["harbor"]:
        parser.error(f'Harbor {config["harbor"]} is required; found {version}')
    sources = [ROOT / "tasks" / name for name in config["tasks"]]
    smoke = [ROOT / "smoke" / name for name in ["sum-list", "permission-check"]]
    inputs = [ROOT / name for name in ["benchmark.json", "benchmark.py", "grader.py",
                                     "agent.Dockerfile", "verifier.Dockerfile"]]
    def fingerprint():
        return digest(inputs + [p for source in sources + smoke
                                for p in source.rglob("*") if p.is_file()])
    before = fingerprint()
    run_id = uuid.uuid4().hex
    folder = ROOT / "runs" / run_id
    folder.mkdir(parents=True)
    report = {"version": config["version"], "source_hash": before,
              "harbor": version, "model": args.model, "settings": config,
              "complete": False, "score": None, "results": []}
    receipt = ROOT / "runs/validated.json"
    if args.check:
        receipt.unlink(missing_ok=True)
    try:
        report["images"] = {source.name: prepare(source, folder / "tasks" / source.name,
                            config, run_id, deadline) for source in sources + smoke}
        identity = {"source_hash": before, "images": report["images"]}
        if args.check:
            stages = [("oracle", True), ("oracle", True), ("nop", False), ("wrong", False)]
            for index, (role, expected) in enumerate(stages):
                target = folder / f"check-{index}"
                for source in sources:
                    destination = target / source.name
                    shutil.copytree(folder / "tasks" / source.name, destination)
                    if role == "wrong":
                        shutil.rmtree(destination / "solution")
                        shutil.copytree(source / "wrong", destination / "solution")
                        (destination / "solution/solve.sh").write_text(
                            "#!/bin/sh\ncp /solution/*.py /app/\n")
                rows = job(target, "oracle" if role == "wrong" else role, 1,
                           config, folder, deadline)
                report["results"] += rows
                if any(row["status"] != ("pass" if expected else "fail") for row in rows):
                    raise ValueError(f"pre-check failed: {role}")
            for source in smoke:
                target = folder / ("smoke-" + source.name)
                shutil.copytree(folder / "tasks" / source.name, target / source.name)
                rows = job(target, "oracle", 1, config, folder, deadline)
                report["results"] += rows
                if any(row["status"] != "pass" for row in rows):
                    raise ValueError(f"smoke check failed: {source.name}")
            if fingerprint() != before:
                raise ValueError("source changed during checks")
            receipt.write_text(json.dumps(identity, indent=2))
            report["complete"] = True
        else:
            if not receipt.exists() or json.loads(receipt.read_text()) != identity:
                raise ValueError("run --check first; source or images are not validated")
            target = folder / "scored"
            for source in sources:
                shutil.copytree(folder / "tasks" / source.name, target / source.name)
            rows = job(target, config["agent"], config["attempts"], config,
                       folder, deadline, args.model)
            report["results"] = rows
            if fingerprint() != before or any(row["status"] == "error" for row in rows):
                raise ValueError("source changed or a trial could not be graded")
            report["complete"] = True
            report["passed"] = sum(row["status"] == "pass" for row in rows)
            report["score"] = report["passed"] / (len(sources) * config["attempts"])
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        try:
            cleanup(run_id)
        except (OSError, subprocess.SubprocessError) as error:
            report.update(complete=False, score=None, cleanup_error=str(error))
        (folder / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print("Evidence:", folder)
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
