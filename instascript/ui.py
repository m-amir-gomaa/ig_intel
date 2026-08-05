"""Terminal UI — the human face of the pipeline.

Everything a user sees in manual mode goes through this module. The pipeline
itself (cli.py) stays print-free; callers render here. Colors auto-disable when
stdout is not a TTY or NO_COLOR is set, so piped/CI output stays clean.
"""

import os
import sys
from pathlib import Path

_USE_COLOR = (
    sys.stdout.isatty()
    and not os.environ.get("NO_COLOR")
    and os.environ.get("TERM") != "dumb"
)

# ANSI SGR codes (bold/dim are attributes; the rest are fg colors).
_BOLD, _DIM = 1, 2
_GREEN, _YELLOW, _RED, _CYAN = 32, 33, 31, 36
_PREFIX = {"success": "✓", "skip": "⏭", "error": "✗", "warn": "!", "info": "·"}


def _c(code: int, s: str) -> str:
    if not _USE_COLOR:
        return s
    return f"\033[{code}m{s}\033[0m"


def _rule(width: int = 72) -> str:
    return _c(_DIM, "─" * width)


def banner(title: str) -> None:
    print(f"\n{_c(_BOLD, title)}")
    print(_rule())
    print()


def step(n: int, total: int, name: str, detail: str) -> None:
    tag = _c(_CYAN, f"[{n}/{total}]")
    print(f"{tag} {_c(_BOLD, name):<10} {_c(_DIM, detail)}")


def success(text: str) -> None:
    print(f"{_c(_GREEN, _PREFIX['success'])} {text}")


def skip(text: str, detail: str = "") -> None:
    print(f"{_c(_YELLOW, _PREFIX['skip'])} {text}"
          + (f" {_c(_DIM, detail)}" if detail else ""))


def error(text: str) -> None:
    print(f"{_c(_RED, _PREFIX['error'])} {text}")


def warn(text: str) -> None:
    print(f"{_c(_YELLOW, _PREFIX['warn'])} {text}")


def info(text: str) -> None:
    print(f"{_c(_DIM, _PREFIX['info'])} {text}")


def file_line(name: str, desc: str) -> None:
    print(f"   {_c(_BOLD, name):<18} {_c(_DIM, desc)}")


def done_block(slug_dir: Path) -> None:
    print()
    success(f"saved → {_c(_BOLD, str(slug_dir))}")
    print(_rule(40))
    file_line("transcript.json", "verbatim segments + word timestamps")
    file_line("transcript.txt", "plain text")
    file_line("audio.wav", "16 kHz mono PCM")
    file_line("source.json", "metadata + dedup hashes")
    if (slug_dir / "summary.md").is_file():
        file_line("summary.md", "DeepSeek summary")
    if (slug_dir / "flags.md").is_file():
        file_line("flags.md", "advisory factual flags")
    print()


def compact(i: int, total: int, label: str, status: str, detail: str = "") -> None:
    """One line per item, used by --queue. status: done|dup|error."""
    idx = _c(_CYAN, f"[{i}/{total}]")
    if status == "done":
        mark = _c(_GREEN, _PREFIX["success"])
    elif status == "dup":
        mark = _c(_YELLOW, _PREFIX["skip"])
    else:
        mark = _c(_RED, _PREFIX["error"])
    print(f"{idx} {label:<40} {mark}"
          + (f" {_c(_DIM, detail)}" if detail else ""))


def summary(ok_count: int, dup_count: int, fail_count: int, detail: str = "") -> None:
    parts = [
        f"{ok_count} done" if ok_count else None,
        f"{dup_count} already ingested" if dup_count else None,
        f"{fail_count} failed" if fail_count else None,
    ]
    line = ", ".join(p for p in parts if p) or "nothing processed"
    print(_rule())
    print(f"summary: {line}" + (f" — {detail}" if detail else ""))
    print()
