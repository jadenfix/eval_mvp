import json
import subprocess
from pathlib import Path

cases = [[], [2, 3], [-9, 4, 2], [10**50, 7, -10**50], [0, 0, 0]]
passed = True
for numbers in cases:
    try:
        run = subprocess.run(
            ["/usr/local/bin/python", "-I", "/app/main.py"],
            input=json.dumps(numbers), capture_output=True, text=True,
            timeout=3, user=1000, group=1000, extra_groups=[], cwd="/app",
            env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
        answer = json.loads(run.stdout)
        ok = run.returncode == 0 and type(answer) is int and answer == sum(numbers)
    except (subprocess.TimeoutExpired, ValueError):
        ok = False
    print(json.dumps({"input": numbers, "passed": ok}), flush=True)
    passed &= ok
Path("/logs/verifier/reward.txt").write_text("1\n" if passed else "0\n")
