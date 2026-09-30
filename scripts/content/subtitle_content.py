#!/usr/bin/env python3
"""Word-by-word subtitles for a Content record: STT, optional script check, burn, register.

Steps per content:
  1. Speech-to-text with word timestamps (faster-whisper via uv; language auto-detected).
  2. If the content has a script (script.txt, script.md or source/script.txt), compare it
     with what was heard. Below --threshold the item stops as "needs-review" (nothing burned).
  3. Subtitles are the STT words themselves, one word per cue, exactly as heard.
  4. Burn with the brand's subtitle preset and register the result as a Studio draft.

Free and local. Use --all-missing to process every content that has a source video and no
subtitle run yet, one after another.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import workspace  # noqa: E402
CONTENT_ROOT = ROOT / "content"
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
SCRIPT_NAMES = ("script.txt", "script.md", "source/script.txt")


def source_video(content: Path) -> Path | None:
    folder = content / "source" / "video"
    if not folder.is_dir():
        return None
    videos = sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES)
    return videos[0] if videos else None


def script_file(content: Path) -> Path | None:
    return next((content / n for n in SCRIPT_NAMES if (content / n).is_file()), None)


def preset_for(content: Path) -> str:
    try:
        brand = json.loads((content / "content.json").read_text(encoding="utf-8")).get("brand")
    except (OSError, ValueError):
        brand = None
    return workspace.subtitle_preset(brand)


def already_done(content: Path) -> bool:
    return any((content / "edit" / "subtitles").glob("*/result.json"))


def run(cmd: list[str]) -> str:
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} failed: {(done.stderr or done.stdout)[-800:]}")
    return done.stdout


def process(content: Path, args: argparse.Namespace) -> dict:
    video = source_video(content)
    if not video:
        return {"content": content.name, "status": "skipped", "reason": "no source video in source/video/"}
    work = content / "edit" / "subtitles" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work.mkdir(parents=True, exist_ok=True)
    words, subtitles = work / "word-timed.srt", work / "subtitles.srt"
    out = run(["uv", "run", "--with", "faster-whisper", "--with", "av>=13,<16", "python", "skills/reel-subtitles/scripts/transcribe_words.py",
               "--video", str(video), "--output", str(words), "--language", args.language, "--model", args.model])
    detected = re.search(r"^Language: (\w+)", out, re.M)
    language = detected.group(1) if detected else args.language
    result: dict = {"content": content.name, "video": video.relative_to(ROOT).as_posix(), "language": language,
                    "workDir": work.relative_to(ROOT).as_posix(), "scriptCheck": "no script"}
    script = script_file(content)
    if script:
        report = work / "speech-qa.json"
        run(["python3", "scripts/build_spoken_subtitles.py", "--words", str(words), "--expected-script", str(script),
             "--output", str(work / "phrases.srt"), "--report", str(report)])
        data = json.loads(report.read_text(encoding="utf-8"))
        result["alignmentRatio"] = data["alignment_ratio"]
        result["differences"] = len(data["differences"])
        result["scriptCheck"] = "ok" if data["alignment_ratio"] >= args.threshold else "mismatch"
    if result["scriptCheck"] == "mismatch":
        result["status"] = "needs-review"
        result["reason"] = (f"Speech differs from {script.name} (match {result['alignmentRatio']:.0%}, "
                            f"need {args.threshold:.0%}). See {result['workDir']}/speech-qa.json; fix the script or the video, then rerun.")
    else:
        shutil.copyfile(words, subtitles)  # word-by-word: exactly the STT words and timings
        result["subtitles"] = subtitles.relative_to(ROOT).as_posix()
        result["status"] = "ok"
        if not args.no_burn:
            captioned = work / "captioned.mp4"
            run(["python3", "skills/reel-subtitles/scripts/burn_subtitles.py", "--video", str(video),
                 "--subtitles", str(subtitles), "--output", str(captioned), "--preset", preset_for(content)])
            result["captioned"] = captioned.relative_to(ROOT).as_posix()
            if not args.no_publish:
                run(["python3", "scripts/publish_to_studio.py", str(content), str(captioned), "--language", language,
                     "--subtitles", str(subtitles), "--label", "Word-by-word subtitles (review)", "--status", "draft",
                     "--notes", "Word-by-word subtitles from speech-to-text" +
                     (f"; script check {result['scriptCheck']}." if script else "; no script to check against.")])
                result["registered"] = True
    (work / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--content", help="content/<content-id>")
    target.add_argument("--all-missing", action="store_true", help="Every content with a source video and no subtitle run yet.")
    parser.add_argument("--language", default="auto", help="Speech language code, default auto-detect.")
    parser.add_argument("--model", default="small", help="Whisper model (default small).")
    parser.add_argument("--threshold", type=float, default=0.80, help="Minimum script match to proceed (default 0.80).")
    parser.add_argument("--no-burn", action="store_true")
    parser.add_argument("--no-publish", action="store_true", help="Do not register a Studio draft.")
    args = parser.parse_args()
    if args.content:
        path = Path(args.content)
        path = (path if path.is_absolute() else ROOT / path).resolve()
        if path.parent != CONTENT_ROOT.resolve() or not path.is_dir():
            parser.error("--content must be an existing direct child of content/.")
        targets = [path]
    else:
        targets = [p for p in sorted(CONTENT_ROOT.iterdir()) if p.is_dir() and source_video(p) and not already_done(p)]
        if not targets:
            print(json.dumps({"status": "nothing-to-do"}))
            return 0
    code = 0
    for content in targets:
        try:
            print(json.dumps(process(content, args), ensure_ascii=False), flush=True)
        except Exception as error:  # keep the batch going; report per item
            print(json.dumps({"content": content.name, "status": "failed", "reason": str(error)}, ensure_ascii=False), flush=True)
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
