"""Sonaweft CLI: recoverable ingest, queues, separate reviews and subtitle export.

Legacy instascript commands remain compatible. Local ASR needs installed media
tools and model weights; optional review additionally needs a provider account.
No external agent or editor plugin is required.
"""

import argparse
import json
import logging
import re
import shutil
import sys
from pathlib import Path

from . import config, ui

log = logging.getLogger("instascript")

_QUEUE_LINE_RE = re.compile(r"^\s*-\s*\[\s?\]\s+(\S+)\s*$")


def _existing_index(
    roots: list[Path],
) -> tuple[dict[str, str], dict[str, str]]:
    """Scan every source.json under roots → {hash: item_dir}.

    Two maps so dedup works at two levels:
    - url_sha256    — exact link (tracking params stripped) already ingested
    - content_sha256 — the same audio already ingested from any other source
    """
    url_map, content_map = {}, {}
    seen: set[Path] = set()
    for root in roots:
        p = Path(root).expanduser().resolve()
        if p in seen or not p.is_dir():
            continue
        seen.add(p)
        for sj in p.rglob("source.json"):
            from .pipeline import complete_item

            if (
                ".pending" in sj.parts
                or ".download" in sj.parts
                or not complete_item(sj.parent)
            ):
                continue
            try:
                data = json.loads(sj.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            d = str(sj.parent)
            if uh := data.get("url_sha256"):
                url_map.setdefault(uh, d)
            if ch := data.get("content_sha256"):
                content_map.setdefault(ch, d)
    return url_map, content_map


def _label(meta: dict | None, fallback: str = "?") -> str:
    if not meta:
        return str(fallback)[:40]
    title = meta.get("title") or meta.get("slug") or meta.get("input") or fallback
    return str(title)[:40]


def _run_single(input_arg, args, quiet=False, pos=(0, 0)):
    """Publish the requested complete result, preserving interrupted ASR work privately."""
    from .pipeline import ingest

    result = ingest(
        input_arg,
        Path(args.out).expanduser(),
        model=args.model,
        review=args.review,
        review_model=getattr(args, "review_model", "standard"),
        cookies_browsers=config.YTDLP_COOKIES_FROM_BROWSER,
    )
    if not quiet:
        ui.success("Complete Sonaweft export is ready; original ASR is preserved.")
    else:
        ui.compact(*pos, result.name[:40], "done")
    print(result)
    return 0, "done"


def run_single(
    input_arg: str,
    args: argparse.Namespace,
    quiet: bool = False,
    pos: tuple[int, int] = (0, 0),
) -> tuple[int, str]:
    try:
        return _run_single(input_arg, args, quiet, pos)
    except (
        Exception
    ) as error:  # Keep failed items pending; continue the rest of a queue.
        log.debug("pipeline failed for %s", input_arg, exc_info=True)
        if quiet:
            ui.compact(*pos, input_arg[:40], "error", str(error)[:60])
        else:
            ui.error(f"pipeline failed: {error}")
        return 1, "error"


def run_queue(args: argparse.Namespace) -> int:
    qfile = Path(args.queue).expanduser()
    if not qfile.is_file():
        ui.error(f"queue file not found: {qfile}")
        return 1
    lines = qfile.read_text(encoding="utf-8").splitlines()
    pending = [m.group(1) for line in lines if (m := _QUEUE_LINE_RE.match(line))]
    if not pending:
        ui.info(f"queue empty (no pending items): {qfile}")
        return 0

    ui.banner(f"instaScript · batch queue ({len(pending)} items)")
    done: set[str] = set()
    n_done = n_dup = n_fail = 0
    for pos, link in enumerate(pending, 1):
        _, status = run_single(link, args, quiet=True, pos=(pos, len(pending)))
        if status == "done":
            n_done += 1
            done.add(link)
        elif status == "dup":
            n_dup += 1
            done.add(link)  # already ingested → nothing left to do
        else:
            n_fail += 1

    # Drop processed lines; keep headers/comments and any failed items.
    new_lines = [
        line
        for line in lines
        if not ((m := _QUEUE_LINE_RE.match(line)) and m.group(1) in done)
    ]
    qfile.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    ui.summary(n_done, n_dup, n_fail, f"queue updated: {qfile}")
    return 0 if n_fail == 0 else 1


def _resolve_item_dir(ref: str) -> Path | None:
    p = Path(ref).expanduser()
    if p.is_dir():
        return p
    for base in (config.PIPELINE_INBOX, config.IG_INTEL_VAULT):
        c = base / ref
        if c.is_dir():
            return c
    for hit in config.IG_INTEL_VAULT.rglob(f"{ref}/transcript.json"):
        return hit.parent
    return None


def run_review_item(args):
    import os
    import tempfile
    import uuid
    from .review import review_transcript
    from .contract import bundle

    d = _resolve_item_dir(args.review_item)
    if d is None:
        ui.error("Transcript item not found.")
        return 1
    try:
        raw = json.loads((d / "transcript.json").read_text())
        source_meta = json.loads((d / "source.json").read_text())
        review = review_transcript(raw, getattr(args, "review_model", "standard"))
        root = d / "reviews"
        root.mkdir(exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=root))
        try:
            files = bundle(raw, source_meta, review, {})
            for name in ("review.json", "summary.md", "claims.md"):
                (stage / name).write_text(files[name], encoding="utf-8")
            target = root / str(uuid.uuid4())
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        ui.success(f"Source-linked advisory review written → {target}")
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        ui.error(f"Review failed: {error}")
        return 1


def run(args: argparse.Namespace) -> int:
    if args.export_item:
        from .subtitles import export_item

        d = _resolve_item_dir(args.export_item)
        if d is None:
            ui.error(f"item not found: {args.export_item}")
            return 1
        try:
            output = export_item(d, args.format)
        except (OSError, ValueError, TypeError) as error:
            ui.error(f"subtitle export failed: {error}")
            return 1
        ui.success(f"subtitles written → {output}")
        return 0
    if args.queue:
        return run_queue(args)
    if args.review_item:
        return run_review_item(args)
    if not args.input:
        ui.error("no input: pass a URL/file, --queue, or --review-item")
        return 2
    return run_single(args.input, args)[0]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="sonaweft",
        description=(
            "Audio/video → timestamped transcript and source-linked notes. Optional AI review; raw ASR preserved."
        ),
    )
    p.add_argument(
        "input", nargs="?", help="Instagram reel URL or local audio/video file"
    )
    p.add_argument(
        "--export-item",
        metavar="SLUG_OR_DIR",
        help="export an existing transcript to subtitles; no model or API call",
    )
    p.add_argument(
        "--format",
        choices=("srt", "vtt"),
        default="srt",
        help="subtitle export format (default srt)",
    )
    p.add_argument(
        "--queue",
        default=None,
        nargs="?",
        const=str(config.QUEUE_FILE),
        help=f"batch queue: process every '- [ ]' link in FILE (default "
        f"{config.QUEUE_FILE}) through the pipeline into Inbox",
    )
    p.add_argument(
        "--model",
        default=config.WHISPER_MODEL_DEFAULT,
        help="whisper model size: tiny|base|small|medium|large-v3 (default small)",
    )
    p.add_argument(
        "--review",
        action="store_true",
        help="DeepSeek summary + source-quoted research questions (needs DEEPSEEK_API_KEY)",
    )
    p.add_argument(
        "--review-item",
        default=None,
        metavar="SLUG_OR_DIR",
        help="DeepSeek review of an ALREADY-extracted item "
        "(no re-transcription)",
    )
    p.add_argument(
        "--out",
        default=str(config.PIPELINE_INBOX),
        help=f"output root (default {config.PIPELINE_INBOX} — vault Inbox)",
    )
    p.add_argument(
        "--review-model",
        choices=("standard", "advanced"),
        default="standard",
        help="Optional review: DeepSeek Flash or V4 Pro; separate from the speech model",
    )
    p.add_argument("--verbose", action="store_true", help="debug logging to stderr")
    a = p.parse_args(argv)
    if (
        sum(bool(value) for value in (a.input, a.queue, a.review_item, a.export_item))
        > 1
    ):
        p.error("choose one input mode: source, queue, review-item, or export-item")

    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    return run(a)
