"""Trusted grader. Submitted programs execute as an unprivileged child."""
import csv
import io
import json
import os
import random
import resource
import signal
import sqlite3
import subprocess
import tempfile
from pathlib import Path


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)


def run(value, args=(), code=None):
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            ["/usr/local/bin/python", "-I", *(["-c", code] if code else ["/app/main.py"]), *args],
            stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
            user=1000, group=1000, extra_groups=[], start_new_session=True,
            preexec_fn=limits, cwd="/app", env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
        try:
            process.communicate(json.dumps(value).encode(), timeout=3)
            if process.returncode:
                raise ValueError("program exited unsuccessfully")
            stdout.seek(0)
            return json.load(stdout)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def cases(kind):
    rng = random.Random(2026)
    if kind == "csv-totals":
        for rows in [[], [("a,b", 7), ("a,b", -2), ("x", 0)]] + [
            [(rng.choice(["a", "b", "c"]), rng.randint(-100, 100)) for _ in range(20)]
            for _ in range(12)
        ]:
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(["name", "amount"])
            writer.writerows(rows)
            expected = {name: sum(amount for key, amount in rows if key == name)
                        for name, _ in rows}
            yield {"csv": stream.getvalue() + "\n"}, (), expected
        for text in ["name,amount\nx,bad\n", "name,amount\nx\n", "name,amount\nx,1,extra\n",
                     "other,amount\nx,1\n"]:
            yield {"csv": text}, (), {"error": "invalid"}
    elif kind == "config-merge":
        for _ in range(20):
            layers = [{key: rng.randint(-20, 20) for key in "abcd" if rng.choice([0, 1])}
                      for _ in range(3)]
            yield dict(zip(["defaults", "file", "cli"], layers)), (), dict(
                pair for layer in layers for pair in layer.items())
        yield {}, (), {}
        yield {"defaults": {"enabled": True, "value": 1.5, "text": "old"},
               "file": {"enabled": False, "value": None}, "cli": {"text": "new"}}, (), {
                   "enabled": False, "value": None, "text": "new"}
    elif kind == "sqlite-update":
        for updates in [[], [["a", 3], ["a", -8]], [["a", 9], ["missing", 1]],
                        [["missing", 2]]] + [
            [[rng.choice(["a", "b"]), rng.randint(-10, 10)] for _ in range(8)]
            for _ in range(10)
        ]:
            yield {"updates": updates}, (), None
    elif kind == "dependency-order":
        for _ in range(15):
            nodes = [f"n{i}" for i in range(rng.randint(0, 8))]
            graph = {node: [prior for prior in nodes[:i] if rng.choice([0, 1])]
                     for i, node in enumerate(nodes)}
            yield graph, (), None
        yield {"a": ["b"], "b": ["a"]}, (), {"error": "cycle"}
        yield {"a": ["missing"]}, (), {"error": "unknown dependency"}
        yield {"a": ["a"]}, (), {"error": "cycle"}
        yield {"a": ["b"], "b": []}, (), None
    elif kind == "cli-unique":
        for numbers in [[], [-1, 2, -1, 0, 2]] + [
            [rng.randint(-5, 5) for _ in range(25)] for _ in range(10)
        ]:
            for args in [(), ("--sort",), ("--unique",), ("--sort", "--unique"),
                         ("--unique", "--sort")]:
                expected = list(dict.fromkeys(numbers)) if "--unique" in args else numbers
                yield numbers, args, sorted(expected) if "--sort" in args else expected
    elif kind == "sum-list":
        for numbers in [[], [2, 3], [-9, 4, 2], [10**50, 7, -10**50]]:
            yield numbers, (), sum(numbers)
    elif kind == "permission-check":
        yield None, (), [True, True]
    else:
        raise ValueError("unknown task")


def check(kind, value, args, expected):
    if kind == "sqlite-update":
        with tempfile.TemporaryDirectory() as directory:
            os.chown(directory, 1000, 1000)
            db = Path(directory) / "accounts.db"
            initial = {"a": 10, "b": 20, "c": 30}
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, balance INTEGER)")
                conn.executemany("INSERT INTO accounts VALUES (?, ?)", initial.items())
            os.chown(db, 1000, 1000)
            expected = initial.copy()
            invalid = any(key not in initial for key, _ in value["updates"])
            if not invalid:
                for key, delta in value["updates"]:
                    expected[key] += delta
            answer = run(value, [str(db)])
            with sqlite3.connect(db) as conn:
                actual = dict(conn.execute("SELECT id, balance FROM accounts"))
            return equal(actual, expected) and equal(answer,
                {"error": "unknown account"} if invalid else expected)
    answer = run(value, args)
    if kind == "dependency-order" and expected is None:
        return (type(answer) is list and all(type(node) is str for node in answer)
                and len(answer) == len(value) and set(answer) == set(value)
                and all(answer.index(dep) < answer.index(node)
                        for node, deps in value.items() for dep in deps))
    if kind == "config-merge":
        library = run(value, code="import json,sys; sys.path.insert(0,'/app'); "
                      "from config import merge; print(json.dumps(merge(json.load(sys.stdin))))")
        return equal(answer, expected) and equal(library, expected)
    return equal(answer, expected)


def equal(actual, expected):
    return json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)


def main():
    # Protect the parent: Docker bind mounts may ignore permissions inside it.
    os.chown("/logs", 0, 0)
    os.chmod("/logs", 0o700)
    os.umask(0o022)  # Host runner may read logs; submitted code still cannot write them.
    kind = Path("/tests/kind.txt").read_text().strip()
    results = []
    for number, (value, args, expected) in enumerate(cases(kind)):
        try:
            passed = check(kind, value, args, expected)
            detail = ""
        except (ValueError, OSError, subprocess.TimeoutExpired, sqlite3.Error) as error:
            passed, detail = False, type(error).__name__
        results.append({"case": number, "passed": passed, "detail": detail})
    logs = Path("/logs/verifier")
    (logs / "checks.json").write_text(json.dumps(results, indent=2))
    (logs / "reward.txt").write_text("1\n" if results and all(
        row["passed"] for row in results) else "0\n")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
