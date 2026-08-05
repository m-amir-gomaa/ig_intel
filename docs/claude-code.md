# instaScript + Claude Code — setup & daily driver

> **Optional layer.** The `instascript` CLI is fully standalone — every command
> in this doc merely drives that same CLI. Claude Code adds *judgment* on top:
> organizing, linking, researching, and fact-checking the transcript vault. It
> never replaces the pipeline.

This guide covers:

1. API keys (DeepSeek, both for `--review` and for headless Claude Code).
2. Installing the project's Claude Code tools (UTCP bridge).
3. Verifying headless sessions work.
4. Managing an Obsidian vault with the scripts.
5. A daily-driver routine.

---

## 1. API keys

One DeepSeek key serves two purposes:

- **`DEEPSEEK_API_KEY`** — used directly by `instascript --review` /
  `--review-item` (REST calls to `https://api.deepseek.com`).
- **`ANTHROPIC_AUTH_TOKEN`** + **`ANTHROPIC_BASE_URL`** — lets Claude Code
  authenticate and route through DeepSeek's Anthropic-compatible endpoint, so
  headless sessions (`claude -p`), including the UTCP tools, run on DeepSeek.

Export in your shell profile (`~/.bashrc`, `~/.zshrc`, or NixOS
`environment.sessionVariables`):

```sh
export DEEPSEEK_API_KEY="sk-..."                 # DeepSeek
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"  # same key, Anthropic-format endpoint
export ANTHROPIC_MODEL="deepseek-chat"           # default model
# Claude Code resolves opus/sonnet/haiku → map them to DeepSeek tiers:
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-flash"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
```

> Model names are examples — set whatever DeepSeek exposes for your account.
> `claude` must be installed and on `PATH` (npm/global install, or your distro).

---

## 2. Install the project's Claude Code tools (UTCP)

The repo ships the tool definitions under `utcp/` (portable templates — no
absolute paths, no secrets). They register six headless tools with the UTCP
bridge (`~/.utcp/`), each of which fires a `claude -p` session in your vault:

| tool | what it does |
|---|---|
| `ig_process_queue` | batch-extract every `- [ ]` link in `Inbox/queue.md` → Inbox, delete verified lines |
| `ig_ingest` | ingest one source (URL or file) → transcript in Inbox |
| `ig_review` | summary + factual flags on an item, then organize it |
| `ig_organize_inbox` | organize all Inbox items into management classes, link notes |
| `ig_research` | live web research on a claim/topic → provenance-tagged findings in the note |
| `ig_vault_task` | freeform: study, connect, fact-check, answer from the knowledge base |

Install (idempotent):

```sh
IG_INTEL_VAULT="$HOME/ig_intel" TAVILY_API_KEY="tvly-..." ./utcp/install.sh
```

- `IG_INTEL_VAULT` — your Obsidian vault root (where transcripts + notes live).
- `TAVILY_API_KEY` — optional; only `ig_research` needs it. No key → other tools
  still work.

What the script does: substitutes the placeholders into
`~/.utcp/manuals/igintel.json`, writes the headless MCP config
(`~/.utcp/igintel-mcp.json` — tavily for research sessions), and registers the
manual in `~/.utcp/.utcp_config.json`.

**Restart your Claude Code session** so the bridge loads the new tools, then
verify:

```
mcp__utcp__list_tools        → expect ig_process_queue, ig_ingest, ig_review,
                               ig_organize_inbox, ig_research, ig_vault_task
```

---

## 3. Verify headless sessions

Smoke test that `claude -p` talks to DeepSeek and that the bridge sees the tools:

```sh
claude -p "reply with exactly: HEADSHELL_OK" --dangerously-skip-permissions
# → HEADSHELL_OK
```

Then confirm the tool surface inside a headless session:

```sh
claude -p "Call mcp__utcp__list_tools and report the tool names." \
  --dangerously-skip-permissions --mcp-config ~/.utcp/igintel-mcp.json
```

> `--mcp-config ~/.utcp/igintel-mcp.json` gives the headless session the same
> tavily web-search tools used interactively. The `ig_*` tools already pass it
> for you.

---

## 4. Managing an Obsidian vault with the scripts

The mechanical pipeline (`instascript`) and the intelligence layer (Claude Code)
have a clean boundary:

```
Inbox/queue.md (links) ── instascript --queue ──► Inbox/<slug>/ transcripts
                                                        │
   ig_process_queue / ig_ingest  (headless, optional)  │
                                                        ▼
   summary.md + flags.md  (DeepSeek, advisory)
                                                        │
   ig_organize_inbox  → Classes/*.md, item notes, links │
   ig_review          → review + organize one item      │
   ig_research        → live research, provenance       │
   ig_vault_task      → study / connect / answer        │
                                                        ▼
   Obsidian vault: linked notes, verified claims, second brain
```

Claude Code *reads and edits notes*; it never re-transcribes or alters
transcripts. Each `ig_*` tool reads `.ai/WORKFLOW.md` (and friends) in the vault
first, so behavior stays consistent across sessions.

### The loop

1. **Extract** — `ig_process_queue` (or `instascript --queue`) turns new links
   into transcripts.
2. **Review** — `ig_review` / `instascript --review-item` writes summary + flags.
3. **Organize** — `ig_organize_inbox` files items into management classes and
   links notes.
4. **Research** — `ig_research` verifies flagged claims against primary sources,
   tagging findings with URLs and confidence.

### Concrete examples (call the tools, or say the same thing to Claude Code)

```sh
# Batch-extract everything in the queue
# → ig_process_queue

# Ingest one reel
# → ig_ingest  source="https://www.instagram.com/reel/DY-iZeGgYjj/"

# Review + organize one item
# → ig_review  slug="video-by-justxashton"

# Organize the whole Inbox into classes
# → ig_organize_inbox

# Verify a flagged claim live, with sources
# → ig_research  topic="can EM waves be converted to gravitational waves?"

# Freeform: "summarize what this vault knows about scalar physics"
# → ig_vault_task  task="study scalar physics using the vault; connect related items"
```

### Interactive mode

Inside the vault directory:

```sh
cd "$IG_INTEL_VAULT" && claude
# "process the queue"
# "review video-by-justxashton"
# "organize the inbox"
# "research the EGR1 claim from myopiasolution"
# "what do I know about X? gaps?"
```

The session reads `.ai/CLAUDE.md` + `.ai/WORKFLOW.md` automatically and
operates the vault consistently.

---

## 5. Daily-driver routine

A suggested cadence. Everything is optional; even skipping the whole Claude Code
layer, `instascript --queue` keeps working.

**Morning (5 min)**

1. Drop links you saved overnight into `Inbox/queue.md` (or use the share button
   → append).
2. `claude` in the vault → `"process the queue"` (or `instascript --queue`).
3. Skim the report: what ingested, what failed (retry failures).

**Midday (10 min)**

4. `"review the new items"` — summaries + flags land; suspicious claims flagged.
5. `"organize the inbox"` — items filed into classes, notes linked.

**Evening (optional, as needed)**

6. `ig_research` on the highest-confidence/weight flagged claims — provenance
   lands in the note.
7. `ig_vault_task` for anything you want studied or connected.

**Periodic hygiene**

- `instascript --queue` from cron/systemd for fully unattended ingestion.
- Review `flags.md` files; verify before you trust or publish any claim.

---

## Troubleshooting

| symptom | fix |
|---|---|
| `review unavailable: DEEPSEEK_API_KEY not set` | export the key, restart session |
| `claude -p` errors / model not found | check `ANTHROPIC_BASE_URL` + `ANTHROPIC_MODEL`; DeepSeek endpoint must be `/anthropic` |
| `mcp__utcp__list_tools` missing `ig_*` | re-run `./utcp/install.sh`, restart the Claude Code session |
| headless research has no web tools | confirm `--mcp-config ~/.utcp/igintel-mcp.json` and `TAVILY_API_KEY` |
| Instagram "empty media response" | log into the browser used by `YTDLP_COOKIES_FROM_BROWSER` (default `firefox`) |
