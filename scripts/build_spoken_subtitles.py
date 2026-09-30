#!/usr/bin/env python3
"""Turn word-timed STT into short phrase subtitles and a script QA report.

The expected script is never used as caption text. Captions are built from the
words the recognizer heard; the expected script is only compared for review.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from pathlib import Path


TIMING = re.compile(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s+-->\s+(\d\d):(\d\d):(\d\d),(\d\d\d)")


def seconds(value: tuple[str, ...]) -> tuple[float, float]:
    a = int(value[0]) * 3600 + int(value[1]) * 60 + int(value[2]) + int(value[3]) / 1000
    b = int(value[4]) * 3600 + int(value[5]) * 60 + int(value[6]) + int(value[7]) / 1000
    return a, b


def stamp(value: float) -> str:
    milliseconds = max(0, round(value * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02},{milliseconds:03}"


def words_from_srt(path: Path) -> list[tuple[float, float, str]]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").replace("\r\n", "\n").strip())
    words = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        match = TIMING.fullmatch(lines[1])
        if not match:
            continue
        start, end = seconds(match.groups())
        words.append((start, end, " ".join(lines[2:])))
    if not words:
        raise RuntimeError("The word-timed SRT did not contain usable words.")
    return words


def tokens(value: str) -> list[str]:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.findall(r"[\w\u0600-\u06ff]+", value, flags=re.UNICODE)


def phrase_groups(words: list[tuple[float, float, str]]) -> list[list[tuple[float, float, str]]]:
    groups, current = [], []
    for index, item in enumerate(words):
        current.append(item)
        next_start = words[index + 1][0] if index + 1 < len(words) else item[1] + 1
        text = " ".join(word[2] for word in current)
        ending = bool(re.search(r"[.!?؟]\s*$", item[2]))
        pause = next_start - item[1] > 0.42
        if ending or pause or len(current) >= 5 or len(text) >= 42:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--words", required=True, type=Path)
    expected = parser.add_mutually_exclusive_group(required=True)
    expected.add_argument("--expected-script", type=Path)
    expected.add_argument("--expected-words", type=Path, help="Second STT pass used as an automatic QA reference.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    words = words_from_srt(args.words)
    actual_text = " ".join(word[2] for word in words)
    expected_text = (
        args.expected_script.read_text(encoding="utf-8").strip()
        if args.expected_script else " ".join(word[2] for word in words_from_srt(args.expected_words))
    )
    actual_tokens, expected_tokens = tokens(actual_text), tokens(expected_text)
    matcher = difflib.SequenceMatcher(a=expected_tokens, b=actual_tokens, autojunk=False)
    differences = []
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag != "equal":
            differences.append({"kind": tag, "expected": expected_tokens[a0:a1], "heard": actual_tokens[b0:b1]})
    groups = phrase_groups(words)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for index, group in enumerate(groups, start=1):
            handle.write(f"{index}\n{stamp(group[0][0])} --> {stamp(group[-1][1])}\n")
            handle.write(" ".join(item[2] for item in group) + "\n\n")
    report = {
        "expected_script": expected_text,
        "heard_text": actual_text,
        "expected_word_count": len(expected_tokens),
        "heard_word_count": len(actual_tokens),
        "alignment_ratio": round(matcher.ratio(), 4),
        "differences": differences,
        "subtitle_source": "speech-to-text",
        "qa_reference": "provided script" if args.expected_script else "independent Speech-to-Text pass",
        "note": "Subtitle text comes from word-timed speech-to-text. The QA reference is never caption source text.",
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"subtitles": str(args.output.resolve()), "report": str(args.report.resolve()), "alignment_ratio": report["alignment_ratio"]}))


if __name__ == "__main__":
    main()
