import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import benchmark


class RunnerTests(unittest.TestCase):
    def test_whole_run_deadline_stops_a_hung_process(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            benchmark.execute([sys.executable, "-c", "import time; time.sleep(10)"],
                              time.monotonic() + 0.1, capture=True)

    def test_reward_forgery_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = Path(directory)
            logs = trial / "verifier"
            logs.mkdir()
            (logs / "checks.json").write_text('[{"case":0,"passed":false}]')
            (logs / "reward.txt").write_text("1")
            result = {"verifier_environment_mode": "separate",
                      "verifier_result": {"rewards": {"reward": 1}}}
            self.assertEqual(benchmark.trial_status(result, trial), "error")

    def test_shared_grading_is_rejected(self):
        self.assertEqual(benchmark.trial_status({"verifier_environment_mode": "shared"},
                                                Path("unused")), "error")

    def test_skipped_checks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            trial = Path(directory)
            (trial / "verifier").mkdir()
            (trial / "verifier/checks.json").write_text('[{"case":0,"passed":true}]')
            (trial / "verifier/reward.txt").write_text("1")
            result = {"verifier_environment_mode": "separate",
                      "verifier_result": {"rewards": {"reward": 1}}}
            self.assertEqual(benchmark.trial_status(result, trial, 2), "error")

    def test_only_agent_timeout_is_an_unsuccessful_attempt(self):
        for error, expected in [("AgentTimeoutError", "timeout"),
                                ("VerifierTimeoutError", "error")]:
            result = {"exception_info": {"exception_type": error}}
            self.assertEqual(benchmark.trial_status(result, Path("unused")), expected)

    def test_missing_task_result_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = root / "tasks"
            (tasks / "example").mkdir(parents=True)
            (tasks / "example/task.toml").write_text("")
            with patch.object(benchmark, "execute"):
                rows = benchmark.job(tasks, "nop", 1, {}, root, 0)
            self.assertEqual(rows, [{"task": "example", "status": "error",
                                     "detail": "missing result"}])

    def test_malformed_result_is_retained_as_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = root / "tasks"
            (tasks / "example").mkdir(parents=True)
            (tasks / "example/task.toml").write_text("")

            def bad_result(command, *_):
                job_name = command[command.index("--job-name") + 1]
                path = root / "jobs" / job_name / "trial"
                path.mkdir(parents=True)
                (path / "result.json").write_text("{broken")

            with patch.object(benchmark, "execute", side_effect=bad_result):
                rows = benchmark.job(tasks, "nop", 1, {}, root, 0)
            self.assertTrue(rows)
            self.assertTrue(all(row["status"] == "error" for row in rows))

    def test_duplicate_trial_cannot_replace_an_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = root / "tasks"
            (tasks / "sum-list").mkdir(parents=True)
            (tasks / "sum-list/task.toml").write_text("")

            def duplicates(command, *_):
                job_name = command[command.index("--job-name") + 1]
                for name in ["first", "second"]:
                    trial = root / "jobs" / job_name / name
                    (trial / "verifier").mkdir(parents=True)
                    result = {"id": "same-id", "task_name": "sum-list", "trial_name": name,
                              "config": {"task": {"path": str(tasks / "sum-list")}},
                              "agent_info": {}, "task_checksum": "fixture",
                              "verifier_environment_mode": "separate",
                              "verifier_result": {"rewards": {"reward": 1}}}
                    (trial / "result.json").write_text(json.dumps(result))
                    (trial / "verifier/reward.txt").write_text("1")
                    (trial / "verifier/checks.json").write_text(json.dumps(
                        [{"case": i, "passed": True} for i in range(4)]))

            with patch.object(benchmark, "execute", side_effect=duplicates):
                rows = benchmark.job(tasks, "nop", 2, {}, root, 0)
            self.assertEqual(sum(row["status"] == "pass" for row in rows), 1)
            self.assertTrue(any(row["status"] == "error" for row in rows))

    def test_snapshot_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = root / "tasks"
            (tasks / "sum-list").mkdir(parents=True)
            config = tasks / "sum-list/task.toml"
            config.write_text("before")
            with patch.object(benchmark, "execute", side_effect=lambda *_: config.write_text("after")):
                rows = benchmark.job(tasks, "nop", 1, {}, root, 0)
            self.assertIn({"task": "snapshot", "status": "error",
                           "detail": "task changed during execution"}, rows)


if __name__ == "__main__":
    unittest.main()
