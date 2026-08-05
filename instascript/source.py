"""Stage A: resolve input (URL or local file) → local media + metadata.

Dedup hashes live here:
- url_sha256    — SHA-256 of the URL with tracking params (utm_*, igsh, …) stripped.
                  Same share link (different utm string) → same hash.
- content_sha256 — SHA-256 of the normalized 16 kHz wav, computed by the CLI
                  after Stage B. Decoding is deterministic, so the same audio
                  from a URL, a local file, or a re-encoded copy yields the same
                  hash → nothing is ever transcribed twice.
"""

import hashlib
import json
import re
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path

_TRACKING_PREFIXES = ("utm_", "igsh", "fbclid", "gclid", "mc_", "ref_")


def slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text.lower()).strip("-")
    return text[:64] or "untitled"


def normalize_url(url: str) -> str:
    """Strip share-tracking params so the same link hashes identically."""
    base, _, query = url.partition("?")
    if not query:
        return base.rstrip("/")
    keep = [
        p for p in query.split("&")
        if p and not p.split("=", 1)[0].lower().startswith(_TRACKING_PREFIXES)
    ]
    q = "&".join(keep)
    return base.rstrip("/") + (f"?{q}" if q else "")


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def hash_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def hash_audio(wav_path: Path, chunk_frames: int = 1 << 18) -> str:
    """SHA-256 of the *PCM samples* of a 16-bit WAV, ignoring the header.

    The RIFF header can legitimately differ between ffmpeg builds (extra
    chunks, LIST/INFO metadata) while the audio is byte-identical. Hashing only
    the sample data keeps content_sha256 stable across encoders/machines.
    """
    h = hashlib.sha256()
    with wave.open(str(wav_path), "rb") as w:
        while True:
            frames = w.readframes(chunk_frames)
            if not frames:
                break
            h.update(frames)
    return h.hexdigest()


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _auth_wall(stderr: str) -> bool:
    """yt-dlp error hints that the source requires a logged-in session."""
    hints = ("cookies", "logged-in", "login required", "empty media response")
    return any(h in stderr.lower() for h in hints)


def _run_ytdlp(url: str, out_tmpl: str, cookies: str | None) -> tuple[int, str, str]:
    cmd = [
        "yt-dlp", "-f", "bestaudio", "--no-playlist", "-o", out_tmpl,
        "--print", "after_move:%(filepath)s|%(title)s|%(id)s|%(uploader)s",
    ]
    if cookies:
        cmd += ["--cookies-from-browser", cookies]
    cmd.append(url)
    proc = subprocess.run(
        cmd, capture_output=True, text=True, check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _download_url(url: str, out_dir: Path, cookies_browsers: str) -> dict:
    """yt-dlp bestaudio → out_dir. Returns {media, title, id, uploader}.

    Sources like Instagram require a logged-in session. We try without cookies
    first (most platforms work anonymously); on an auth wall we retry with the
    configured browser cookies (YTDLP_COOKIES_FROM_BROWSER, comma-separated).
    """
    out_tmpl = str(out_dir / "%(id)s.%(ext)s")
    ret, out, err = _run_ytdlp(url, out_tmpl, cookies=None)
    if ret != 0 and _auth_wall(err):
        for browser in (b.strip() for b in cookies_browsers.split(",") if b.strip()):
            ret, out, err = _run_ytdlp(url, out_tmpl, cookies=browser)
            if ret == 0:
                break
    if ret != 0:
        raise RuntimeError(f"yt-dlp failed: {err.strip()}")
    line = out.strip().splitlines()[0] if out.strip() else ""
    fields = line.split("|")
    media = Path(fields[0])
    return {
        "media": media,
        "title": fields[1] if len(fields) > 1 else media.stem,
        "id": fields[2] if len(fields) > 2 else media.stem,
        "uploader": fields[3] if len(fields) > 3 else "",
    }


def resolve(
    input_arg: str,
    out_root: Path,
    cookies_browsers: str = "firefox",
) -> tuple[Path, dict]:
    """Return (media_path, source_meta dict)."""
    if input_arg.startswith(("http://", "https://")):
        tmp_dir = out_root / ".download"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        meta = _download_url(input_arg, tmp_dir, cookies_browsers)
        media = meta["media"]
        source_meta = {
            "input": input_arg,
            "kind": "url",
            "url_sha256": url_hash(input_arg),
            "slug": slugify(meta["title"] or meta["id"]),
            "title": meta["title"],
            "source_id": meta["id"],
            "uploader": meta["uploader"],
            "duration": _ffprobe_duration(media),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "orig_format": media.suffix.lstrip("."),
        }
    else:
        media = Path(input_arg).expanduser().resolve()
        if not media.is_file():
            raise FileNotFoundError(f"file not found: {media}")
        source_meta = {
            "input": str(media),
            "kind": "local",
            "url_sha256": "",
            "slug": slugify(media.stem),
            "title": media.stem,
            "source_id": media.stem,
            "uploader": "",
            "duration": _ffprobe_duration(media),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "orig_format": media.suffix.lstrip("."),
        }
    return media, source_meta
