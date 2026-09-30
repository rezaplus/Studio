#!/usr/bin/env python3
"""Locally AI-upscale a vertical Reel with Real-ESRGAN and retain its audio.

This is intentionally an editorial helper, not a claim of native source detail.
It needs the isolated `.tools/realesrgan-test` environment created during setup
and the official RealESRGAN_x4plus model file in `models/realesrgan/`.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import cv2
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "models/realesrgan/RealESRGAN_x4plus.pth"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def source_fps(video: Path) -> str:
    output = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=avg_frame_rate", "-of", "json", str(video)], text=True
    )
    value = json.loads(output)["streams"][0]["avg_frame_rate"]
    return str(float(Fraction(value)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--duration", type=float, help="Optional short test duration in seconds.")
    parser.add_argument("--start", type=float, default=0, help="Test start in seconds.")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    parser.add_argument("--tile", type=int, default=256, help="Lower is safer for Apple Silicon memory.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()

    source = args.input.resolve()
    destination = args.output.resolve()
    if not source.is_file():
        parser.error(f"Input video not found: {source}")
    if not args.model.is_file():
        parser.error(f"Real-ESRGAN model not found: {args.model}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fps = source_fps(source)

    with tempfile.TemporaryDirectory(prefix="ai-upscale-reel-") as temp:
        workspace = Path(temp)
        frames_in = workspace / "frames-in"
        frames_out = workspace / "frames-out"
        frames_in.mkdir()
        frames_out.mkdir()
        extract = ["ffmpeg", "-y", "-ss", str(args.start), "-i", str(source)]
        if args.duration:
            extract += ["-t", str(args.duration)]
        extract += ["-an", "-vf", f"fps={fps}", str(frames_in / "frame_%06d.png")]
        run(*extract)

        net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23,
                      num_grow_ch=32, scale=4)
        device = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
        engine = RealESRGANer(scale=4, model_path=str(args.model), model=net,
                              tile=args.tile, tile_pad=16, pre_pad=0, half=False, device=device)
        images = sorted(frames_in.glob("*.png"))
        if not images:
            raise RuntimeError("No video frames were extracted.")
        for index, frame in enumerate(images, start=1):
            image = cv2.imread(str(frame), cv2.IMREAD_COLOR)
            enhanced, _ = engine.enhance(image, outscale=1.5)
            enhanced = cv2.resize(enhanced, (args.width, args.height), interpolation=cv2.INTER_LANCZOS4)
            cv2.imwrite(str(frames_out / frame.name), enhanced)
            print(f"AI-upscaled {index}/{len(images)}", flush=True)

        visual = workspace / "visual.mp4"
        run("ffmpeg", "-y", "-framerate", fps, "-i", str(frames_out / "frame_%06d.png"),
            "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", str(visual))
        audio_offset = ["-ss", str(args.start)] if args.start else []
        run("ffmpeg", "-y", "-i", str(visual), *audio_offset, "-i", str(source),
            "-map", "0:v:0", "-map", "1:a?", "-c:v", "copy", "-c:a", "copy", "-shortest", str(destination))
    print(f"Saved: {destination}")


if __name__ == "__main__":
    main()
