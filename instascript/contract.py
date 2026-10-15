"""Portable transcript contract shared by CLI, hosted jobs and future Noteweld imports."""

import hashlib
import json
import math
from .subtitles import render


def validate_transcript(value):
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("segments"), list)
        or len(value["segments"]) > 20000
    ):
        raise ValueError("Invalid transcript segments.")
    duration = value.get("duration")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or not 0 <= duration <= 86400
    ):
        raise ValueError("Invalid transcript duration.")
    previous = 0.0
    for segment in value["segments"]:
        if (
            not isinstance(segment, dict)
            or not isinstance(segment.get("text"), str)
            or len(segment["text"]) > 10000
        ):
            raise ValueError("Invalid transcript text.")
        start, end = segment.get("start"), segment.get("end")
        if (
            any(
                isinstance(n, bool)
                or not isinstance(n, (int, float))
                or not math.isfinite(n)
                for n in (start, end)
            )
            or not 0 <= start <= end <= duration + 1
            or start < previous
        ):
            raise ValueError("Invalid or out-of-order transcript timestamps.")
        previous = start
    return value


def segments(value):
    validate_transcript(value)
    return [{**s, "segment_id": f"s{i:06d}"} for i, s in enumerate(value["segments"])]


def validate_review(transcript, value):
    if not isinstance(value, dict) or set(value) != {
        "summary_md",
        "claims",
        "corrections",
    }:
        raise ValueError("Review must contain summary_md, claims and corrections.")
    if not isinstance(value["summary_md"], str) or len(value["summary_md"]) > 20000:
        raise ValueError("Invalid review summary.")
    source = {s["segment_id"]: s["text"] for s in segments(transcript)}
    for field in ("claims", "corrections"):
        entries = value[field]
        if not isinstance(entries, list) or len(entries) > 30:
            raise ValueError("Too many review entries.")
        for entry in entries:
            required = {
                "segment_id",
                "quote",
                "question" if field == "claims" else "replacement",
            }
            if (
                not isinstance(entry, dict)
                or set(entry) != required
                or any(not isinstance(v, str) or len(v) > 5000 for v in entry.values())
            ):
                raise ValueError("Invalid review entry.")
            if (
                entry["segment_id"] not in source
                or not entry["quote"]
                or entry["quote"] not in source[entry["segment_id"]]
            ):
                raise ValueError("Review cites text absent from the original segment.")
    return value


def bundle(transcript, source, review=None, corrections=None):
    """Return strings, never mutate ASR output or pretend generated notes are verified facts."""
    rows = segments(transcript)
    if review is not None:
        validate_review(transcript, review)
    corrected = corrections or {}
    if any(
        k not in {s["segment_id"] for s in rows}
        or not isinstance(v, str)
        or len(v) > 10000
        for k, v in corrected.items()
    ):
        raise ValueError("Invalid correction segment.")
    dump = lambda v: json.dumps(v, ensure_ascii=False, indent=2) + "\n"
    markdown = [
        "---",
        "title: "
        + json.dumps(str(source.get("title", "Transcript")), ensure_ascii=False),
        'format: "instascript-export/v1"',
        'kind: "original-asr"',
        "---",
        "",
        "# Transcript",
        "",
        "Machine transcript; check important words against the recording.",
        "",
    ]
    for s in rows:
        markdown += [
            f'<a id="{s["segment_id"]}"></a>',
            f"**[{s['start']:.2f}–{s['end']:.2f}]** {s['text']}",
            "",
        ]
    files = {
        "transcript.json": dump(transcript),
        "source.json": dump(source),
        "transcript.md": "\n".join(markdown),
        "transcript.txt": "\n".join(
            f"[{s['start']:.2f}-{s['end']:.2f}] {s['text']}" for s in rows
        )
        + "\n",
        "transcript.srt": render(transcript, "srt"),
        "transcript.vtt": render(transcript, "vtt"),
        "corrections.json": dump(corrected),
    }
    if corrected:
        derived = {
            **transcript,
            "segments": [
                {**s, "text": corrected.get(s["segment_id"], s["text"])} for s in rows
            ],
        }
        files["corrected.json"] = dump(derived)
        files["corrected.md"] = (
            "# User-corrected transcript\n\nOriginal ASR remains in transcript.json.\n\n"
            + "\n\n".join(
                f"[{s['start']:.2f}] {s['text']}" for s in derived["segments"]
            )
            + "\n"
        )
    if review:
        files["review.json"] = dump(review)
        files["summary.md"] = (
            "# AI-derived notes\n\nAdvisory, not fact-checked. Original transcript preserved.\n\n"
            + review["summary_md"]
            + "\n"
        )
        files["claims.md"] = (
            "# Claims to investigate\n\nThese are source-linked research questions, not verdicts of truth.\n\n"
            + "\n\n".join(
                f"- [{c['segment_id']}](transcript.md#{c['segment_id']}): {c['quote']}\n  - {c['question']}"
                for c in review["claims"]
            )
            + "\n"
        )
    manifest = {
        "format": "instascript-export/v1",
        "producer": "sonaweft",
        "version": 1,
        "language": transcript.get("language", "en"),
        "duration": transcript["duration"],
        "segments": [
            {"id": s["segment_id"], "start": s["start"], "end": s["end"]} for s in rows
        ],
        "files": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()},
        "asr_model": transcript.get("model"),
        "review_model": source.get("review_model", transcript.get("review_model"))
        if review
        else None,
    }
    files["manifest.json"] = dump(manifest)
    return files
