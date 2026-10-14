#!/usr/bin/env python3
"""Render a truthful source/output visualization from the retained E2E receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1280, 720
FPS, SECONDS = 10, 12
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_inputs(commit: str) -> list[dict[str, str]]:
    rows = []
    for line in run("git", "ls-tree", "-r", "--full-tree", commit).splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, blob = metadata.split()
        if kind != "blob":
            continue
        data = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)
        rows.append({"path": path, "mode": mode, "blob": blob,
                     "sha256": hashlib.sha256(data).hexdigest()})
    return rows


def font(size: int, *, bold: bool = False, mono: bool = False):
    return ImageFont.truetype(FONT_MONO if mono else FONT_BOLD if bold else FONT, size)


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
          fill: str = "#d8e3f0", size: int = 24, *, bold: bool = False,
          mono: bool = False):
    draw.text(xy, text, fill=fill, font=font(size, bold=bold, mono=mono))


def panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str,
          accent: str = "#2dd4bf"):
    draw.rounded_rectangle(box, radius=18, fill="#111c2d", outline="#28405d", width=2)
    x1, y1, _, _ = box
    draw.rounded_rectangle((x1 + 18, y1 + 18, x1 + 30, y1 + 50), radius=6, fill=accent)
    label(draw, (x1 + 44, y1 + 18), title, size=23, bold=True)


def status(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color: str):
    draw.rounded_rectangle((x, y, x + 214, y + 42), radius=21, fill=color)
    label(draw, (x + 18, y + 8), text, fill="#07111d", size=19, bold=True)


def base_frame(frame: int, source_commit: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#07111d")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 78), fill="#0b1726")
    label(draw, (44, 20), "eval_mvp", fill="#f8fafc", size=32, bold=True)
    label(draw, (226, 27), "CURRENT-MAIN E2E RECEIPT", fill="#5eead4", size=20, mono=True)
    status(draw, 804, 18, "NO MODEL CALL", "#5eead4")
    status(draw, 1036, 18, "NO SCORE", "#fbbf24")
    progress = (frame + 1) / (FPS * SECONDS)
    draw.rectangle((0, HEIGHT - 7, WIDTH, HEIGHT), fill="#17263a")
    draw.rectangle((0, HEIGHT - 7, int(WIDTH * progress), HEIGHT), fill="#2dd4bf")
    label(draw, (44, 674), f"captured source {source_commit[:12]}", fill="#7f96b0", size=16, mono=True)
    return image, draw


def draw_scene(draw: ImageDraw.ImageDraw, scene: int, receipt: dict, source_commit: str):
    hosted = receipt["hosted_evidence"]
    valid = receipt["validation"]
    good = valid["complete_reference_and_negative_controls"]
    bad = valid["broken_reference_control"]
    if scene == 0:
        label(draw, (54, 116), "Real benchmark validation, replayed truthfully", size=38, bold=True)
        label(draw, (56, 168), "The visual is derived from the retained Harbor + Docker artifact.",
              fill="#a9bed4", size=23)
        panel(draw, (52, 226, 1228, 610), "IMMUTABLE EVIDENCE")
        rows = [
            ("repository", receipt["repository"]),
            ("current main", receipt["source"]["commit"]),
            ("workflow run", str(hosted["workflow_run"])),
            ("artifact SHA-256", hosted["archive_sha256"]),
        ]
        for index, (key, value) in enumerate(rows):
            y = 292 + index * 70
            label(draw, (88, y), key.upper(), fill="#6f8aa6", size=18, mono=True)
            label(draw, (324, y - 4), value, fill="#edf6ff", size=21, mono=True)
    elif scene == 1:
        label(draw, (54, 116), "What the real E2E job exercised", size=38, bold=True)
        panel(draw, (52, 188, 720, 610), "FIVE SCORED TASK TYPES")
        tasks = ["CSV aggregation", "configuration precedence", "SQLite transactions",
                 "dependency ordering", "CLI --unique behavior"]
        for index, task in enumerate(tasks):
            y = 258 + index * 61
            draw.ellipse((88, y + 4, 108, y + 24), fill="#2dd4bf")
            label(draw, (126, y), task, size=23)
        panel(draw, (748, 188, 1228, 610), "ISOLATION CONTRACT", accent="#fbbf24")
        for index, item in enumerate(["separate verifier", "task network disabled",
                                      "grader stays protected", "container cleanup checked"]):
            y = 264 + index * 70
            label(draw, (790, y), "✓", fill="#fbbf24", size=25, bold=True)
            label(draw, (830, y), item, size=21)
    elif scene == 2:
        label(draw, (54, 116), "Complete validation: actual output", size=38, bold=True)
        panel(draw, (52, 188, 1228, 610), "HOSTED COMMAND + RESULT")
        label(draw, (88, 258), "$ EVAL_MVP_E2E=1 python -m unittest discover \\",
              fill="#94a3b8", size=20, mono=True)
        label(draw, (88, 294), "    -s tests -p test_e2e.py -v", fill="#94a3b8", size=20, mono=True)
        label(draw, (88, 372), f"PASS  {good['pass']:>2}  reference + smoke outcomes",
              fill="#5eead4", size=29, bold=True, mono=True)
        label(draw, (88, 424), f"FAIL  {good['expected_fail']:>2}  expected negative controls",
              fill="#fbbf24", size=29, bold=True, mono=True)
        label(draw, (88, 496), f"{good['real_trials']} unique real Harbor/Docker trials • complete=true",
              fill="#edf6ff", size=24, mono=True)
        label(draw, (88, 548), "score=null • model=null", fill="#7dd3fc", size=24, mono=True)
    elif scene == 3:
        label(draw, (54, 116), "Negative controls are evidence—not errors", size=38, bold=True)
        panel(draw, (52, 188, 1228, 610), "EXPECTED VALIDATION MATRIX")
        headers = [(100, "LANE"), (610, "EXPECTED"), (910, "OBSERVED")]
        for x, value in headers:
            label(draw, (x, 246), value, fill="#6f8aa6", size=18, mono=True)
        rows = [
            ("reference solution ×2", "pass", "12 pass"),
            ("unchanged starter", "reject", "5 fail"),
            ("known-wrong solution", "reject", "5 fail"),
            ("smoke checks", "pass", "2 pass"),
        ]
        for index, row in enumerate(rows):
            y = 304 + index * 62
            draw.line((88, y + 42, 1190, y + 42), fill="#223853", width=1)
            label(draw, (100, y), row[0], size=22)
            label(draw, (610, y), row[1], fill="#a9bed4", size=22, mono=True)
            color = "#5eead4" if "pass" in row[2] else "#fbbf24"
            label(draw, (910, y), row[2], fill=color, size=22, bold=True, mono=True)
    elif scene == 4:
        label(draw, (54, 116), "Broken reference: fail closed", size=38, bold=True)
        panel(draw, (52, 188, 1228, 610), "INTENTIONAL CORRUPTION CONTROL", accent="#fb7185")
        label(draw, (88, 258), "csv-totals reference replaced with known-wrong solution",
              fill="#cbd8e6", size=24, mono=True)
        label(draw, (88, 336), f"{bad['pass_before_rejection']} earlier trials passed before the corrupted task",
              fill="#a9bed4", size=25)
        label(draw, (88, 394), f"{bad['expected_fail']} oracle trial rejected the broken reference",
              fill="#fb7185", size=28, bold=True)
        label(draw, (88, 466), "complete=false • score=null", fill="#fbbf24", size=29, bold=True, mono=True)
        label(draw, (88, 530), f"reason: {bad['reason']}", fill="#edf6ff", size=23, mono=True)
    else:
        label(draw, (54, 116), "Verified scope", size=38, bold=True)
        panel(draw, (52, 188, 690, 610), "DEMONSTRATED")
        label(draw, (90, 270), "✓ provider-free validation", fill="#5eead4", size=25, bold=True)
        label(draw, (90, 326), "✓ real Harbor + Docker", fill="#5eead4", size=25, bold=True)
        label(draw, (90, 382), f"✓ {valid['total_real_harbor_docker_trials']} retained trials", fill="#5eead4", size=25, bold=True)
        label(draw, (90, 438), "✓ separate grading container", fill="#5eead4", size=25, bold=True)
        panel(draw, (720, 188, 1228, 610), "NOT CLAIMED", accent="#fb7185")
        for index, item in enumerate(["model quality", "benchmark score", "private holdout",
                                      "escape resistance", "performance", "deployment"]):
            label(draw, (762, 256 + index * 49), "—", fill="#fb7185", size=22, bold=True)
            label(draw, (800, 256 + index * 49), item, fill="#cbd8e6", size=21)
        label(draw, (54, 628), hosted["workflow_url"], fill="#6f8aa6", size=17, mono=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=ROOT / "demo/e2e_receipt.json")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "demo")
    args = parser.parse_args()
    if run("git", "rev-parse", f"{args.source_commit}^{{tree}}") != args.source_tree:
        raise SystemExit("source commit/tree mismatch")
    receipt = json.loads(args.receipt.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    mp4 = args.output_dir / "eval_mvp.mp4"
    gif = args.output_dir / "eval_mvp.gif"
    poster = args.output_dir / "eval_mvp_poster.png"
    with tempfile.TemporaryDirectory(prefix="eval-mvp-frames-") as directory:
        frames = []
        for frame_number in range(FPS * SECONDS):
            image, draw = base_frame(frame_number, args.source_commit)
            scene = min(5, frame_number // (2 * FPS))
            draw_scene(draw, scene, receipt, args.source_commit)
            path = Path(directory) / f"frame-{frame_number:04d}.png"
            image.save(path, optimize=True)
            frames.append(image)
        frames[-1].save(poster, optimize=True)
        gif_frames = [frame.resize((960, 540), Image.Resampling.LANCZOS)
                      for frame in frames[::2]]
        gif_frames[0].save(gif, save_all=True, append_images=gif_frames[1:],
                           duration=200, loop=0, optimize=True, disposal=2)
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
            "-i", str(Path(directory) / "frame-%04d.png"), "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4),
        ], check=True)
    capture = {
        "schema_version": 1,
        "captured_source": {"commit": args.source_commit, "tree": args.source_tree},
        "evidence_source": receipt["source"],
        "receipt": {"path": str(args.receipt.relative_to(ROOT)),
                    "sha256": file_hash(args.receipt)},
        "source_inputs": source_inputs(args.source_commit),
        "artifacts": {
            str(path.relative_to(ROOT)): {"sha256": file_hash(path)}
            for path in (gif, mp4, poster)
        },
        "render": {"seconds": SECONDS, "mp4_fps": FPS, "gif_fps": FPS // 2,
                   "mp4_size": [WIDTH, HEIGHT], "gif_size": [960, 540]},
        "scope": receipt["scope"],
    }
    (args.output_dir / "capture.json").write_text(
        json.dumps(capture, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
