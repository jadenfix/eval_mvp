#!/usr/bin/env python3
"""Verify source provenance, receipt, media hashes, probes, and full decode."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, binary: bool = False):
    return subprocess.check_output(args, cwd=ROOT, text=not binary)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_source(commit: str) -> list[dict[str, str]]:
    rows = []
    listing = run("git", "ls-tree", "-r", "--full-tree", commit)
    for line in listing.splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, blob = metadata.split()
        if kind != "blob":
            continue
        data = run("git", "show", f"{commit}:{path}", binary=True)
        rows.append({"path": path, "mode": mode, "blob": blob,
                     "sha256": hashlib.sha256(data).hexdigest()})
    return rows


def probe(path: Path) -> dict:
    return json.loads(run(
        "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ))


def main() -> int:
    capture_path = ROOT / "demo/capture.json"
    capture = json.loads(capture_path.read_text())
    source = capture["captured_source"]
    if run("git", "rev-parse", f"{source['commit']}^{{tree}}").strip() != source["tree"]:
        raise SystemExit("captured source commit/tree mismatch")
    subprocess.run(["git", "merge-base", "--is-ancestor", source["commit"], "HEAD"],
                   cwd=ROOT, check=True)
    if tracked_source(source["commit"]) != capture["source_inputs"]:
        raise SystemExit("captured source inputs do not match Git blobs")
    receipt = ROOT / capture["receipt"]["path"]
    if sha256(receipt) != capture["receipt"]["sha256"]:
        raise SystemExit("receipt hash mismatch")
    receipt_data = json.loads(receipt.read_text())
    if receipt_data["source"] != capture["evidence_source"]:
        raise SystemExit("evidence source mismatch")
    artifacts = capture["artifacts"]
    if set(artifacts) != {
        "demo/eval_mvp.gif", "demo/eval_mvp.mp4", "demo/eval_mvp_poster.png",
    }:
        raise SystemExit("unexpected artifact inventory")
    probes = {}
    for name, metadata in artifacts.items():
        path = ROOT / name
        if sha256(path) != metadata["sha256"]:
            raise SystemExit(f"artifact hash mismatch: {name}")
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                       check=True)
        probes[name] = probe(path)
    mp4_stream = probes["demo/eval_mvp.mp4"]["streams"][0]
    gif_stream = probes["demo/eval_mvp.gif"]["streams"][0]
    poster_stream = probes["demo/eval_mvp_poster.png"]["streams"][0]
    if (int(mp4_stream["width"]), int(mp4_stream["height"])) != (1280, 720):
        raise SystemExit("unexpected MP4 dimensions")
    if int(mp4_stream.get("nb_read_frames", 0)) != 120:
        raise SystemExit("unexpected MP4 frame count")
    if (int(gif_stream["width"]), int(gif_stream["height"])) != (960, 540):
        raise SystemExit("unexpected GIF dimensions")
    if int(gif_stream.get("nb_read_frames", 0)) != 60:
        raise SystemExit("unexpected GIF frame count")
    if (int(poster_stream["width"]), int(poster_stream["height"])) != (1280, 720):
        raise SystemExit("unexpected poster dimensions")
    for name in ("demo/eval_mvp.mp4", "demo/eval_mvp.gif"):
        duration = float(probes[name]["format"]["duration"])
        if not 11.9 <= duration <= 12.1:
            raise SystemExit(f"unexpected duration for {name}: {duration}")
    if run("git", "status", "--porcelain", "--untracked-files=all").strip():
        raise SystemExit("verification must leave a clean checkout")
    print(json.dumps({
        "captured_source": source,
        "evidence_workflow_run": receipt_data["hosted_evidence"]["workflow_run"],
        "real_trials": receipt_data["validation"]["total_real_harbor_docker_trials"],
        "artifacts": {name: metadata["sha256"] for name, metadata in artifacts.items()},
        "decoded": True,
        "clean": True,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
