"""Real CLI → Harbor → Docker → grading → report tests; no model calls."""
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("EVAL_MVP_E2E") == "1",
                     "set EVAL_MVP_E2E=1 to run Harbor/Docker tests")
class EndToEndTests(unittest.TestCase):
    def setUp(self):
        # Each test owns a separate benchmark copy and validation receipt.
        self.root = ROOT / "runs" / "e2e" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        for name in ("benchmark.py", "benchmark.json", "grader.py",
                     "agent.Dockerfile", "verifier.Dockerfile"):
            shutil.copy(ROOT / name, self.root / name)
        for name in ("tasks", "smoke"):
            shutil.copytree(ROOT / name, self.root / name)

    def run_check(self):
        with (self.root / "cli.log").open("w") as log:
            process = subprocess.run(
                [sys.executable, "benchmark.py", "--check", "--deadline", "600"],
                cwd=self.root, stdout=log, stderr=subprocess.STDOUT, timeout=660)
        reports = list((self.root / "runs").glob("*/summary.json"))
        self.assertEqual(len(reports), 1, f"See {self.root / 'cli.log'}")
        report_path = reports[0]
        report = json.loads(report_path.read_text())
        containers = subprocess.check_output(
            ["docker", "ps", "-aq", "--filter",
             f"label=eval_mvp.run={report_path.parent.name}"], text=True)
        self.assertEqual(containers.strip(), "", "Run left task containers behind")
        return process.returncode, report, report_path.parent

    def test_complete_validation_and_protected_grading(self):
        code, report, folder = self.run_check()
        self.assertEqual(code, 0, report.get("error"))
        self.assertTrue(report["complete"])
        self.assertIsNone(report["score"])
        self.assertEqual(Counter(row["status"] for row in report["results"]),
                         {"pass": 12, "fail": 10})
        self.assertEqual(len({row["trial_id"] for row in report["results"]}), 22)
        for task in report["settings"]["tasks"]:
            self.assertEqual(Counter(row["status"] for row in report["results"]
                                     if row["task"] == task), {"pass": 2, "fail": 2})
        for row in report["results"]:
            trial = folder / row["evidence"]
            result = json.loads(trial.read_text())
            self.assertEqual(result["verifier_environment_mode"], "separate")
            self.assertIsNone(result["exception_info"])
            checks = json.loads((trial.parent / "verifier/checks.json").read_text())
            self.assertTrue(checks)
            self.assertEqual(all(check["passed"] for check in checks),
                             row["status"] == "pass")
        receipt = json.loads((self.root / "runs/validated.json").read_text())
        self.assertEqual(receipt, {"source_hash": report["source_hash"],
                                   "images": report["images"]})

    def test_broken_reference_cannot_validate_or_produce_a_score(self):
        shutil.copy(self.root / "tasks/csv-totals/wrong/main.py",
                    self.root / "tasks/csv-totals/solution/main.py")
        code, report, _ = self.run_check()
        self.assertEqual(code, 2)
        self.assertFalse(report["complete"])
        self.assertIsNone(report["score"])
        self.assertIn("pre-check failed: oracle", report["error"])
        self.assertFalse((self.root / "runs/validated.json").exists())
        self.assertTrue(any(row["task"] == "csv-totals" and row["status"] == "fail"
                            for row in report["results"]))


if __name__ == "__main__":
    unittest.main()
