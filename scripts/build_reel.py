#!/usr/bin/env python3
"""Build a silent, normalized 9:16 Reel from a project's completed shot files."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def probe(path: Path) -> dict:
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height,r_frame_rate", "-of", "json", str(path)]
    return json.loads(subprocess.check_output(command, text=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--output", default="final/reel-visual.mp4", help="Path relative to project")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe must be installed.")
    project = args.project.resolve()
    manifest = json.loads((project / "project.json").read_text(encoding="utf-8"))
    clips = [project / shot["final_path"] for shot in manifest["shots"]]
    missing = [str(clip.relative_to(project)) for clip in clips if not clip.is_file()]
    if missing:
        raise RuntimeError("Missing completed shots:\n" + "\n".join(missing))
    probes = {clip.name: probe(clip) for clip in clips}
    (project / "edit" / "ffprobe.json").write_text(json.dumps(probes, indent=2) + "\n", encoding="utf-8")
    output = (project / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.overwrite:
        raise RuntimeError(f"Output already exists: {output}. Use --overwrite to replace it.")
    filters = []
    for index, shot in enumerate(manifest["shots"]):
        filters.append(f"[{index}:v]trim=duration={shot['duration']},setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,setsar=1[v{index}]")
    filters.append("".join(f"[v{index}]" for index in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[v]")
    command = ["ffmpeg", "-y" if args.overwrite else "-n"] + sum((["-i", str(clip)] for clip in clips), []) + ["-filter_complex", ";".join(filters), "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-movflags", "+faststart", str(output)]
    subprocess.run(command, check=True)
    print(f"Built visual assembly: {output}"); print(json.dumps(probe(output)["format"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
