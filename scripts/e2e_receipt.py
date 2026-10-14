#!/usr/bin/env python3
"""Validate a retained GitHub Actions E2E artifact and emit a small receipt.

The archive is evidence from the real Harbor/Docker job.  This script never
executes an agent or a model and never turns validation outcomes into a score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import benchmark  # noqa: E402


MAX_MEMBERS = 20_000
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def current_source_hash() -> str:
    config = json.loads((benchmark.ROOT / "benchmark.json").read_text())
    sources = [benchmark.ROOT / "tasks" / name for name in config["tasks"]]
    smoke = [benchmark.ROOT / "smoke" / name for name in ("sum-list", "permission-check")]
    inputs = [benchmark.ROOT / name for name in (
        "benchmark.json", "benchmark.py", "grader.py",
        "agent.Dockerfile", "verifier.Dockerfile",
    )]
    files = inputs + [path for source in sources + smoke
                      for path in source.rglob("*") if path.is_file()]
    return benchmark.digest(files)


def _safe_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise ValueError("artifact contains too many members")
    if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
        raise ValueError("artifact is too large after decompression")
    members: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
            raise ValueError(f"unsafe artifact member: {info.filename!r}")
        if info.is_dir():
            continue
        if info.filename in members:
            raise ValueError(f"duplicate artifact member: {info.filename!r}")
        members[info.filename] = info
    return members


def _json(archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], name: str):
    try:
        return json.loads(archive.read(members[name]))
    except KeyError as error:
        raise ValueError(f"missing artifact member: {name}") from error


def _validate_rows(archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo],
                   summary_name: str, report: dict) -> tuple[Counter, int]:
    base = PurePosixPath(summary_name).parent
    statuses = Counter()
    identities: set[str] = set()
    for row in report.get("results", []):
        status = row.get("status")
        if status not in {"pass", "fail"}:
            raise ValueError("retained E2E evidence contains an infrastructure error")
        statuses[status] += 1
        evidence = row.get("evidence")
        identity = row.get("trial_id")
        if not evidence or not identity or identity in identities:
            raise ValueError("missing or duplicate retained trial identity")
        identities.add(identity)
        result_name = str(base / PurePosixPath(evidence))
        result = _json(archive, members, result_name)
        if result.get("id") != identity or result.get("verifier_environment_mode") != "separate":
            raise ValueError("trial identity or verifier-isolation evidence does not match")
        if result.get("exception_info") is not None:
            raise ValueError("retained trial contains an execution exception")
        checks_name = str(PurePosixPath(result_name).parent / "verifier/checks.json")
        reward_name = str(PurePosixPath(result_name).parent / "verifier/reward.txt")
        checks = _json(archive, members, checks_name)
        reward = archive.read(members[reward_name]).decode().strip()
        passed = bool(checks) and all(item.get("passed") is True for item in checks)
        if passed != (status == "pass") or reward != ("1" if passed else "0"):
            raise ValueError("trial checks, reward, and summary status disagree")
    return statuses, len(identities)


def inspect_archive(path: Path, *, workflow_run: int, artifact_id: int,
                    head_sha: str, head_tree: str, created_at: str) -> dict:
    archive_bytes = path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        members = _safe_members(archive)
        summaries = sorted(name for name in members if name.endswith("/summary.json"))
        logs = sorted(name for name in members if name.endswith("/cli.log"))
        if len(summaries) != 2 or len(logs) != 2:
            raise ValueError("expected exactly two E2E summaries and two CLI logs")
        reports = [(name, _json(archive, members, name)) for name in summaries]
        complete = [(name, row) for name, row in reports if row.get("complete") is True]
        rejected = [(name, row) for name, row in reports if row.get("complete") is False]
        if len(complete) != 1 or len(rejected) != 1:
            raise ValueError("expected one complete and one intentionally rejected E2E run")
        good_name, good = complete[0]
        bad_name, bad = rejected[0]
        good_statuses, good_trials = _validate_rows(archive, members, good_name, good)
        bad_statuses, bad_trials = _validate_rows(archive, members, bad_name, bad)
        expected_source = current_source_hash()
        if good.get("source_hash") != expected_source:
            raise ValueError("retained run does not match the current benchmark source")
        if good.get("score") is not None or good.get("model") is not None:
            raise ValueError("validation evidence must not contain a benchmark score or model")
        if good_statuses != Counter({"pass": 12, "fail": 10}) or good_trials != 22:
            raise ValueError("complete validation outcome counts changed")
        if bad.get("score") is not None or bad.get("model") is not None:
            raise ValueError("broken-reference evidence must not contain a score or model")
        if bad_statuses != Counter({"pass": 4, "fail": 1}) or bad_trials != 5:
            raise ValueError("broken-reference rejection outcome counts changed")
        if "pre-check failed: oracle" not in bad.get("error", ""):
            raise ValueError("broken reference was not rejected by the oracle pre-check")
        evidence_hashes = {
            name: sha256(archive.read(members[name]))
            for name in sorted(summaries + logs)
        }
    return {
        "schema_version": 1,
        "repository": "jadenfix/eval_mvp",
        "source": {"commit": head_sha, "tree": head_tree,
                   "benchmark_hash": expected_source},
        "hosted_evidence": {
            "workflow_run": workflow_run,
            "workflow_url": f"https://github.com/jadenfix/eval_mvp/actions/runs/{workflow_run}",
            "artifact_id": artifact_id,
            "artifact_created_at": created_at,
            "archive_sha256": sha256(archive_bytes),
            "evidence_file_sha256": evidence_hashes,
        },
        "validation": {
            "complete_reference_and_negative_controls": {
                "complete": True, "score": None, "pass": 12, "expected_fail": 10,
                "real_trials": 22,
            },
            "broken_reference_control": {
                "complete": False, "score": None, "pass_before_rejection": 4,
                "expected_fail": 1, "real_trials": 5,
                "reason": "pre-check failed: oracle",
            },
            "total_real_harbor_docker_trials": good_trials + bad_trials,
            "separate_verifier": True,
            "model_called": False,
            "benchmark_score_measured": False,
        },
        "scope": {
            "demonstrated": "provider-free local benchmark validation with Harbor and Docker",
            "not_demonstrated": [
                "model quality", "benchmark score", "private holdout quality",
                "container escape resistance", "performance", "production deployment",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--workflow-run", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--head-tree", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = inspect_archive(args.archive, workflow_run=args.workflow_run,
                              artifact_id=args.artifact_id, head_sha=args.head_sha,
                              head_tree=args.head_tree, created_at=args.created_at)
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
