"""DeepSeek summary + factual-flagging — the only LLM automation.

Claude Code manages the vault (organize, connect, research, fact-check) using
its native search + editing. This script does two narrow things:

1. summary.md   — concise, faithful summary.
2. flags.md     — advisory list of claims that seem non-factual / unsupported /
                  overstated / outright wrong. Raw transcript is never altered.
"""

import json
from pathlib import Path

from .llm import LLMProvider


def _transcript_block(transcript: dict) -> str:
    return "\n".join(
        f"[{s['start']:.2f}-{s['end']:.2f}] {s['text']}"
        for s in transcript["segments"]
    )


def _frontmatter(slug_dir: Path) -> str:
    """YAML header tracing the markdown back to its source link + dedup hashes.

    Keys mirror source.json so any note (Obsidian search, grep, scripts) can
    join markdown → link → audio via url_sha256 / content_sha256.
    """
    sj = slug_dir / "source.json"
    if not sj.is_file():
        return ""
    try:
        m = json.loads(sj.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    fields = []
    for key in ("input", "kind", "url_sha256", "content_sha256"):
        if m.get(key):
            fields.append(f"{key}: {m[key]}")
    return "---\n" + "\n".join(fields) + "\n---\n\n" if fields else ""


def summarize_and_flag(
    provider: LLMProvider,
    transcript: dict,
    slug_dir: Path,
) -> dict:
    system = (
        "You analyze a spoken transcript. Produce (1) a concise faithful summary and "
        "(2) a factual flag list. Respond with ONE JSON object only:\n"
        '{"summary_md": "...", "flags": [{"claim": "...", "concern": "...", '
        '"confidence": "high|medium|low"}]}\n'
        "Rules:\n"
        "- summary_md: readable markdown (2-4 sentences + key points). Faithful to "
        "the source. No invention, no new facts.\n"
        "- flags: ONLY claims that seem non-factual, unsupported, overstated, or "
        "outright wrong. For each: quote the claim verbatim, explain the concern, "
        "rate confidence (high/medium/low). Empty array if nothing is flaggable. "
        "Do not flag trivial or subjective statements. This is advisory — the raw "
        "transcript is preserved verbatim regardless."
    )
    user = (
        "Transcript (segments with timecodes):\n"
        "---\n"
        f"{_transcript_block(transcript)}\n"
        "---\n"
        "Produce the JSON."
    )
    raw = provider.complete(system, user, json_mode=True)
    data = json.loads(raw)

    summary = data.get("summary_md", "")
    flags = data.get("flags", []) or []

    slug_dir.mkdir(parents=True, exist_ok=True)
    fm = _frontmatter(slug_dir)
    (slug_dir / "summary.md").write_text(
        fm + summary.rstrip() + "\n", encoding="utf-8"
    )

    if flags:
        lines = []
        if fm:
            lines.append(fm.rstrip())
        lines += [
            "",
            "# Factual Flags",
            "",
            "Claims from this transcript that may be non-factual, unsupported, "
            "overstated, or wrong. **Advisory** — the raw transcript is preserved "
            "verbatim. Verify against primary sources before relying on them.",
            "",
        ]
        for f in flags:
            conf = f.get("confidence", "?")
            lines.append(f"- **[{conf}]** “{f.get('claim', '')}”")
            lines.append(f"  - {f.get('concern', '')}")
        lines.append("")
        (slug_dir / "flags.md").write_text("\n".join(lines), encoding="utf-8")

    return {"summary": summary, "flags": flags, "flags_file": "flags.md" if flags else None}
