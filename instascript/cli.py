"""CLI orchestration.

Three modes, no Claude Code required:

  Single mode:   instascript <url|file>            → Inbox/<slug>/   (manual)
  Queue mode:    instascript --queue [FILE]        → every `- [ ]` link in the
                                                   queue file through the
                                                   pipeline, checked off on
                                                   success.               (auto)
  Review mode:   instascript --review-item <slug>  → summary.md + flags.md
                                                   on an existing item.  (manual)

Claude Code is an OPTIONAL orchestration layer (UTCP tools). The CLI below is
the complete, standalone interface — nothing external is ever required.
"""

import argparse
import json
import logging
import re
import shutil
import sys
from pathlib import Path

from . import audio, config, source, summarize, transcribe, ui
from .llm import get_provider

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
            if ".download" in sj.parts:
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


def run_single(
    input_arg: str,
    args: argparse.Namespace,
    quiet: bool = False,
    pos: tuple[int, int] = (0, 0),
) -> tuple[int, str]:
    """Run the pipeline for one source. Returns (exit_code, status).

    status: done | dup | error. In manual mode (quiet=False) full progress is
    rendered; in queue mode (quiet=True) one compact line is printed at the end.
    """
    is_url = input_arg.startswith(("http://", "https://"))
    out_root = Path(args.out).expanduser()
    total = 4 if args.review else 3

    if not quiet:
        ui.banner("instaScript · reel/audio → local transcript")

    url_map, content_map = _existing_index([config.IG_INTEL_VAULT, out_root])

    # Layer 1: exact link dedup — before any download.
    if is_url:
        uh = source.url_hash(input_arg)
        if uh in url_map:
            if not quiet:
                ui.skip("already ingested — same link (url_sha256)")
                ui.info(f"existing: {url_map[uh]}")
                print(url_map[uh])
            else:
                ui.compact(*pos, _label(None, input_arg), "dup", "same link, skipped")
            return 0, "dup"

    # Resolve input → media + metadata (yt-dlp for URLs, else local file).
    try:
        media, meta = source.resolve(
            input_arg, config.PIPELINE_INBOX, config.YTDLP_COOKIES_FROM_BROWSER
        )
    except Exception as e:  # noqa: BLE001
        if not quiet:
            ui.error(f"source resolve failed: {e}")
        else:
            ui.compact(*pos, _label(None, input_arg), "error", str(e)[:60])
        return 1, "error"

    if not quiet:
        detail = (
            f"{meta['title']} ({meta['uploader']} · {meta['duration']:.1f}s)"
            if meta["kind"] == "url" else str(meta["title"])
        )
        ui.step(1, total, "source", detail)

    slug_dir = out_root / meta["slug"]
    slug_dir.mkdir(parents=True, exist_ok=True)

    # URL case: move downloaded media into slug dir.
    if meta["kind"] == "url" and media.parent != slug_dir:
        dest = slug_dir / media.name
        shutil.move(str(media), str(dest))
        media = dest

    wav = audio.normalize(media, slug_dir / "audio.wav")
    if not quiet:
        ui.step(2, total, "audio", "16 kHz mono → audio.wav")

    # Layer 2: content dedup — hash the PCM samples, not the container bytes
    # or the wav header (which can differ between ffmpeg builds).
    meta["content_sha256"] = source.hash_audio(wav)
    if existing := content_map.get(meta["content_sha256"]):
        if existing != str(slug_dir):  # different item, same audio → drop new
            shutil.rmtree(slug_dir, ignore_errors=True)
        if not quiet:
            ui.skip("already ingested — identical audio (content_sha256)")
            ui.info(f"existing: {existing}")
            print(existing)
        else:
            ui.compact(*pos, _label(meta), "dup", "same audio, skipped")
        return 0, "dup"

    (slug_dir / "source.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if not quiet:
        ui.step(3, total, "transcribe", f"faster-whisper {args.model} (CPU int8)")
    tr = transcribe.transcribe(wav, args.model)
    transcribe.write_files(tr, slug_dir)

    if args.review:
        try:
            provider = get_provider()
        except Exception as e:  # noqa: BLE001
            ui.warn(f"review skipped: {e} (transcript saved; use --review-item later)")
            if not quiet:
                ui.done_block(slug_dir)
            else:
                ui.compact(*pos, _label(meta), "done")
            print(slug_dir)
            return 0, "done"
        if not quiet:
            ui.step(4, total, "review", "DeepSeek summary + factual flags")
        result = summarize.summarize_and_flag(provider, tr, slug_dir)
        if not quiet:
            ui.info(f"flags: {result['flags_file'] or 'none — nothing flaggable'}")

    if not quiet:
        ui.done_block(slug_dir)
    else:
        ui.compact(*pos, _label(meta), "done")
    print(slug_dir)
    return 0, "done"


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
        line for line in lines
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


def run_review_item(args: argparse.Namespace) -> int:
    d = _resolve_item_dir(args.review_item)
    if d is None:
        ui.error(f"item not found: {args.review_item} (looked in Inbox and vault)")
        return 1
    tr_path = d / "transcript.json"
    if not tr_path.is_file():
        ui.error(f"no transcript.json in {d}")
        return 1
    tr = json.loads(tr_path.read_text(encoding="utf-8"))
    try:
        provider = get_provider()
    except Exception as e:  # noqa: BLE001
        ui.error(f"review unavailable: {e}")
        return 1

    ui.banner(f"instaScript · review {d.name}")
    result = summarize.summarize_and_flag(provider, tr, d)
    ui.success(f"summary written → {d}/summary.md")
    if result["flags_file"]:
        ui.success(f"flags written  → {d}/{result['flags_file']}")
    else:
        ui.info("flags: none — nothing flaggable")
    print(d)
    return 0


def run(args: argparse.Namespace) -> int:
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
        prog="instascript",
        description=(
            "Reel/audio → local transcript → optional DeepSeek summary + "
            "factual flags. Fully standalone CLI; Claude Code integration is optional."
        ),
    )
    p.add_argument("input", nargs="?", help="Instagram reel URL or local audio/video file")
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
        help="DeepSeek summary + factual flags (needs DEEPSEEK_API_KEY)",
    )
    p.add_argument(
        "--review-item",
        default=None,
        metavar="SLUG_OR_DIR",
        help="DeepSeek summary + factual flags on an ALREADY-extracted item "
        "(no re-transcription)",
    )
    p.add_argument(
        "--out",
        default=str(config.PIPELINE_INBOX),
        help=f"output root (default {config.PIPELINE_INBOX} — vault Inbox)",
    )
    p.add_argument("--verbose", action="store_true", help="debug logging to stderr")
    a = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    return run(a)
