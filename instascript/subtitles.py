"""Export timed transcripts without loading a model or changing ground truth."""

import json
import math
from pathlib import Path


def timestamp(seconds: float, separator: str = ",") -> str:
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or seconds < 0
    ):
        raise ValueError("Subtitle times must be finite, nonnegative numbers")
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}{separator}{milliseconds:03}"


def render(transcript: dict, format: str) -> str:
    if format not in {"srt", "vtt"}:
        raise ValueError("Subtitle format must be srt or vtt")
    if not isinstance(transcript, dict) or not isinstance(
        transcript.get("segments"), list
    ):
        raise ValueError("Transcript must contain a segments array")
    blocks = []
    for segment in transcript["segments"]:
        if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
            raise ValueError("Each segment must contain text, start, and end")
        start = timestamp(segment.get("start"), "." if format == "vtt" else ",")
        end = timestamp(segment.get("end"), "." if format == "vtt" else ",")
        if segment["end"] < segment["start"]:
            raise ValueError("Subtitle end must not precede its start")
        text = "\n".join(
            line.strip() for line in segment["text"].splitlines() if line.strip()
        )
        if text:
            blocks.append(f"{len(blocks) + 1}\n{start} --> {end}\n{text}")
    prefix = "WEBVTT\n\n" if format == "vtt" else ""
    return prefix + ("\n\n".join(blocks) + "\n" if blocks else "")


def export_item(item_dir: Path, format: str) -> Path:
    transcript = json.loads((item_dir / "transcript.json").read_text(encoding="utf-8"))
    content = render(transcript, format)
    output = item_dir / f"transcript.{format}"
    output.write_text(content, encoding="utf-8")
    return output
