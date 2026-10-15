"""Only local, bounded media files. No remote protocols or playlist demuxers."""

import json, math, os, subprocess
from .errors import DomainError

FORMATS = "mov,mp4,m4a,3gp,3g2,mj2,mp3,wav,flac,ogg,matroska,webm,aac"


def run(command, timeout):
    environment = {
        k: v
        for k, v in os.environ.items()
        if k in ("PATH", "LANG", "LD_LIBRARY_PATH", "SYSTEMROOT")
    }
    try:
        r = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DomainError(
            "Media inspection/decoding timed out or is unavailable."
        ) from None
    if r.returncode:
        raise DomainError(
            "This file could not be decoded as supported audio/video. Playlists and remote references are not accepted."
        )
    return r.stdout


def inspect(path):
    data = json.loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-format_whitelist",
                FORMATS,
                "-show_entries",
                "format=duration:stream=codec_type",
                "-of",
                "json",
                str(path),
            ],
            20,
        )
    )
    try:
        duration = float(data["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        raise DomainError("Media duration could not be verified.") from None
    if (
        not math.isfinite(duration)
        or not 0 < duration <= 3600
        or not any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    ):
        raise DomainError("Upload playable audio/video with audio, up to 60 minutes.")
    return duration


def normalize(path, target, seconds):
    if not 0 < seconds <= 3600:
        raise DomainError("Invalid decoding limit.")
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            FORMATS,
            "-i",
            str(path),
            "-t",
            str(seconds),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        120,
    )
    return target
