"""Stage B: normalize media → 16kHz mono 16-bit PCM wav."""

import subprocess
from pathlib import Path


def normalize(media: Path, out_wav: Path) -> Path:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(media),
            "-ar", "16000", "-ac", "1",
            "-c:a", "pcm_s16le",
            str(out_wav),
        ],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()}")
    return out_wav
