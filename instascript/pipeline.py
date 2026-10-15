"""Recoverable private checkpoints; atomic publication of a complete artifact directory."""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from . import audio, source, transcribe
from .contract import bundle, validate_transcript
from .review import review_transcript


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def complete_item(path):
    try:
        record = json.loads((path / "complete.json").read_text())
        return (
            bool(record["files"])
            and all(
                "/" not in k
                and not k.startswith(".")
                and source.hash_file(path / k) == v
                for k, v in record["files"].items()
            )
            and bool(
                validate_transcript(json.loads((path / "transcript.json").read_text()))
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def ingest(
    input_arg,
    out_root,
    model="small",
    review=False,
    review_model="standard",
    cookies_browsers="",
):
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256(
        (
            (
                source.normalize_url(input_arg)
                if input_arg.startswith(("https://", "http://"))
                else str(input_arg)
            )
            + "\0"
            + model
            + "\0"
            + str(review)
            + "\0"
            + review_model
        ).encode()
    )
    if not input_arg.startswith(("https://", "http://")):
        identity.update(source.hash_file(Path(input_arg).expanduser()).encode())
    key = identity.hexdigest()[:24]
    pending = out_root / ".pending"
    pending.mkdir(exist_ok=True, mode=0o700)
    work = pending / key
    work.mkdir(exist_ok=True, mode=0o700)
    lock = work / "running.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError(
            "This source is already running, or an interrupted process left a lock. Verify the old process has stopped before removing its .pending running.lock."
        ) from None
    os.close(fd)
    try:
        state = work / "source.json"
        if not state.exists():
            media, meta = source.resolve(input_arg, work, cookies_browsers)
            audio.normalize(media, work / "audio.wav")
            meta["content_sha256"] = source.hash_audio(work / "audio.wav")
            atomic_json(state, meta)
        else:
            meta = json.loads(state.read_text())
        target = out_root / (source.slugify(meta["title"])[:40] + "-" + key[:10])
        if complete_item(target):
            return target
        checkpoint = work / "transcript.json"
        if checkpoint.exists():
            raw = validate_transcript(json.loads(checkpoint.read_text()))
        else:
            raw = transcribe.transcribe(work / "audio.wav", model)
            validate_transcript(raw)
            atomic_json(checkpoint, raw)
        checked = None
        if review:
            checked = review_transcript(raw, review_model)
        publish = Path(tempfile.mkdtemp(prefix="publish-", dir=pending))
        try:
            for name, text in bundle(raw, meta, checked, {}).items():
                (publish / name).write_text(text, encoding="utf-8")
            shutil.copyfile(work / "audio.wav", publish / "audio.wav")
            files = {
                p.name: source.hash_file(p) for p in publish.iterdir() if p.is_file()
            }
            atomic_json(publish / "complete.json", {"version": 1, "files": files})
            if target.exists():
                if complete_item(target):
                    return target
                raise RuntimeError(
                    "Existing output is incomplete or modified; it was preserved. Move it aside explicitly before retrying."
                )
            os.rename(publish, target)
        finally:
            if publish.exists():
                shutil.rmtree(publish)
        return target
    finally:
        lock.unlink(missing_ok=True)
