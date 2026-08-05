"""Stage C: faster-whisper transcription → canonical transcript (ground truth)."""

import json
from pathlib import Path

from faster_whisper import WhisperModel


def transcribe(wav_path: Path, model_size: str = "small") -> dict:
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(wav_path), word_timestamps=True, vad_filter=True
    )
    seg_list = []
    for seg in segments:
        words = [
            {"word": w.word, "start": round(w.start, 2), "end": round(w.end, 2)}
            for w in (seg.words or [])
        ]
        seg_list.append({
            "id": seg.id,
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
            "words": words,
        })
    return {
        "model": model_size,
        "language": info.language,
        "duration": round(info.duration, 2),
        "audio_file": wav_path.name,
        "segments": seg_list,
    }


def write_files(transcript: dict, slug_dir: Path) -> None:
    """Write canonical transcript.json + plain transcript.txt. Read-only after this."""
    slug_dir.mkdir(parents=True, exist_ok=True)
    (slug_dir / "transcript.json").write_text(
        json.dumps(transcript, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    txt = "\n".join(
        f"[{s['start']:8.2f}-{s['end']:8.2f}] {s['text']}"
        for s in transcript["segments"]
    )
    (slug_dir / "transcript.txt").write_text(txt + "\n", encoding="utf-8")
