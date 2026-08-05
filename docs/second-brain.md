# ig_intel — AI-Managed Second Brain (Design)

> **Optional add-on.** The core instaScript project is transcript extraction +
> AI verification (`--review`). This document describes the optional Obsidian
> knowledge-system layer that runs on top of the transcript inbox. Point
> `IG_INTEL_VAULT` at an Obsidian vault folder to use it.

The system behind `instascript`: a local, privacy-first knowledge lifecycle that
turns Instagram reels (and other audio) into a connected Obsidian knowledge
base. Two deliberate architectural choices:

1. **Scripts do the mechanical work.** `instascript` extracts audio and
   transcribes locally; a narrow DeepSeek step summarizes and flags
   non-factual claims.
2. **Claude Code does the intelligence.** Organizing, linking, researching,
   and fact-checking run on Claude Code's native search + file editing — not on
   a scripted attempt to emulate an agent. The vault ships `.ai/` instructions
   so any session operates it consistently.

## Why not an agentic script layer?

An automated "classify, place, link" pipeline duplicates what Claude Code
already does better: filesystem search, markdown editing, and judgment about
what deserves a new note versus an edit. Keeping the script surface tiny means:

- no brittle state machines or ad-hoc knowledge-graph code to maintain;
- the intelligence layer is just an LLM with file access (Claude Code), which
  can be prompted, steered, and reviewed;
- the LLM's one scripted role (summary + flagging) is narrow, advisory, and
  cannot destroy source material.

## Pipeline

```
url|file ──► instascript ──► Inbox/<slug>/
                │             transcript.json (canonical, verbatim, read-only)
                │             transcript.txt · audio.wav · source.json
                └─► --review (DeepSeek, opt-in)
                            summary.md — faithful, concise
                            flags.md   — advisory list of suspect claims
                └─► Claude Code (the orchestrator)
                            reads .ai/ rules, organizes into classes,
                            links to existing notes, fact-checks flags
```

## Knowledge layers (never merged)

1. **Transcript** — verbatim ground truth, written once, never replaced.
   Whisper can misrecognize or hallucinate; the raw text is preserved regardless.
2. **Summary** (`--review`) — concise and faithful; derived, cannot add facts.
3. **Flags** (`--review`) — advisory list of claims that seem non-factual,
   unsupported, or overstated, each with the verbatim claim, concern, and
   confidence (high/medium/low). The hand-off to Claude Code for verification.
4. **Research / verification** — done by Claude Code, with external provenance
   clearly tagged. Policy: consequential claims (medical/scientific/financial/
   historical) get checked against primary sources; social posts are claims,
   not truth; trivia is not checked.

## Vault structure

```
ig_intel/                          # Obsidian vault — single home
  Inbox/<slug>/                    # pipeline output, entry point
  Professional/<slug>/             # career / work / business-relevant
  Instructional/<slug>/            # worth actively learning now
  Interesting Later Study/<slug>/  # not urgent, preserved
  Classes/<Domain>.md              # living index notes ([[Medicine]], ...)
  .ai/                             # agent instructions (architecture, workflow, decisions)
  CLAUDE.md                        # auto-loaded operating rules for Claude Code
  MOC.md                           # map of content
```

Design: shallow folders; organization via wikilinks, frontmatter, and tags.
Domains live in frontmatter, indexed by living `Classes/` notes. No vector
database — Markdown is the single source of truth; any index/embedding is
derived data that can be rebuilt. Upgrade path: hybrid keyword + semantic
`vault-search` when retrieval degrades at scale.

## Claude Code operating rules (`.ai/`)

- `CLAUDE.md` — distilled rules: preserve source, distinguish source-claim vs
  research vs inference, no bloat, conservative with irreversible actions.
- `ARCHITECTURE.md` — this document, in-vault.
- `WORKFLOW.md` — exact process for Inbox → review → organize → connect →
  verify → update classes.
- `KNOWLEDGE_MODEL.md` — classes, domains, note schema, claim-verification
  structure.
- `DECISIONS.md` — decisions log.
- `PREFERENCES.md` — owner preferences + research policy.
- `MEMORY.md` — running state.

## Components

| module | duty |
|---|---|
| `instascript/source.py` | yt-dlp URL resolve or local file → media + metadata |
| `instascript/audio.py` | ffmpeg → 16 kHz mono wav |
| `instascript/transcribe.py` | local STT (faster-whisper, CPU int8) → canonical transcript |
| `instascript/summarize.py` | DeepSeek summary + factual flags (the only LLM automation) |
| `instascript/llm.py` | provider seam (DirectDeepSeek; OpenRouter/RAG reserved) |
| `bin/instascript` | OS-agnostic launcher (POSIX); `bin/instascript.cmd` (Windows) |

## Invariants

- `transcript.json` is canonical and byte-identical across runs.
- `--review` never alters the transcript; flags are advisory.
- The vault's intelligence layer (Claude Code) preserves source material and
  distinguishes claims from verification and inference.

## Roadmap

- [x] Local transcription (faster-whisper, CPU)
- [x] URL input via yt-dlp
- [x] DeepSeek summary + factual-flagging (`--review`)
- [x] Claude Code + DeepSeek second brain (`.ai/` instructions)
- [x] OS-agnostic launchers
- [ ] Web-search / RAG research layer (provenance-tagged)
- [ ] Hybrid `vault-search` tool at scale
