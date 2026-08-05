# instaScript — Demo script + Upwork walkthrough

Live demo runs on this reel:
`https://www.instagram.com/reel/DY-iZeGgYjj/`
(28.6 s, 540×960 — a "scalar physics / gravitational waves" clip.)

Everything below was verified end-to-end on 2026-08-05 with the exact commands.

---

## What the demo shows (3 takeaways)

1. **One command, local-first** — paste any reel / YouTube / TikTok / podcast
   link (or a local file) → verbatim, timestamped transcript. No cloud, no API
   key for transcription, runs on CPU.
2. **Built-in dedup** — run the same link twice and it *never* re-downloads or
   re-transcribes. Reel re-shared under a different URL, or re-downloaded in
   another format? Still caught, via a content hash of the audio.
3. **Optional AI review** — DeepSeek writes a summary and *flags* claims that
   look non-factual, each with the verbatim quote + confidence. Advisory; the
   raw transcript is never altered. (This clip is a perfect target — it claims
   physics that mainstream sources would flag.)

---

## One-time setup

```sh
git clone https://github.com/m-amir-gomaa/ig_intel.git
cd ig_intel
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # faster-whisper, requests
# ffmpeg + yt-dlp required (README → Installation)
```

Instagram needs a logged-in session. `instaScript` auto-retries with browser
cookies when a platform demands login:

```sh
# default browser for cookies — set to yours if not Firefox:
echo 'YTDLP_COOKIES_FROM_BROWSER=firefox' >> .env
# log into Instagram in Firefox once — then you're set
```

---

## The demo script — record this, top to bottom

Run each block in the terminal, slowly. Expected output is shown — narrate
what's happening as you go.

### 1. Ingest the reel from the link

```sh
bin/instascript "https://www.instagram.com/reel/DY-iZeGgYjj/?utm_source=ig_web_copy_link&igsh=MzRlODBiNWFlZA=="
```

Expected:

```
instaScript · reel/audio → local transcript
────────────────────────────────────────────────────────────────────────

[1/3] source     Video by justxashton (Ashton Forbes · 28.6s)
[2/3] audio      16 kHz mono → audio.wav
[3/3] transcribe faster-whisper small (CPU int8)

✓ saved → ~/ig_intel/Inbox/video-by-justxashton
────────────────────────────────────────
   transcript.json    verbatim segments + word timestamps
   transcript.txt     plain text
   audio.wav          16 kHz mono PCM
   source.json        metadata + dedup hashes
```

> Narrate: *"The full share link, tracking params and all — downloaded,
> normalized, transcribed locally. Nothing uploaded."*

Show the outputs:

```sh
cat ~/ig_intel/Inbox/video-by-justxashton/transcript.txt
cat ~/ig_intel/Inbox/video-by-justxashton/source.json   # note url_sha256 + content_sha256
```

### 2. Run it again — dedup, no re-download

```sh
bin/instascript "https://www.instagram.com/reel/DY-iZeGgYjj/?utm_source=ig_web_copy_link&igsh=MzRlODBiNWFlZA=="
```

Expected:

```
instaScript · reel/audio → local transcript
────────────────────────────────────────────────────────────────────────

⏭ already ingested — same link (url_sha256)
· existing: ~/ig_intel/Inbox/video-by-justxashton
```

> Narrate: *"Same link again — recognized instantly by the URL hash. No download,
> no re-transcription."*

### 3. Same audio, different source — still deduped

```sh
bin/instascript assets/demo/instascript-demo-reel.mp4
```

Expected:

```
⏭ already ingested — identical audio (content_sha256)
· existing: ~/ig_intel/Inbox/video-by-justxashton
```

> Narrate: *"This is the same reel I downloaded earlier as a full video file.
> Different container, different URL — but the audio hash matches, so it points
> to the existing transcript instead of duplicating."*

### 4. (Optional) AI review — summary + factual flags

Needs a DeepSeek key:

```sh
echo 'DEEPSEEK_API_KEY=sk-...' >> .env
bin/instascript --review-item video-by-justxashton
```

Expected:

```
instaScript · review video-by-justxashton
────────────────────────────────────────────────────────────────────────

✓ summary written → ~/ig_intel/Inbox/video-by-justxashton/summary.md
✓ flags written  → ~/ig_intel/Inbox/video-by-justxashton/flags.md
```

Then:

```sh
cat ~/ig_intel/Inbox/video-by-justxashton/summary.md
cat ~/ig_intel/Inbox/video-by-justxashton/flags.md
```

> Narrate: *"The same pipeline adds a faithful summary and flags the claims that
> don't hold up — the 'convert electromagnetic waves into gravitational waves'
> one, for example. Advisory only."*

### 5. (Optional) Batch — many links, one command

```sh
cat >> ~/ig_intel/Inbox/queue.md <<'EOF'
- [ ] https://www.youtube.com/watch?v=dQw4w9WgXcQ
EOF
bin/instascript --queue
```

---

## How to record it yourself

### Option A — OBS Studio (already installed, gives a video file)

1. Open OBS → Settings → **Video**: 1920×1080, 30 fps.
2. **Sources** → `+` → **Display Capture** (whole screen) or **Window Capture**
   (just the terminal).
3. Set terminal font large (Ctrl+Shift+= in most terminals) — readability first.
4. **Start Recording**, run the demo script above, **Stop Recording**.
5. Video lands in the OBS recordings folder; that's your `.mp4` for GitHub/Upwork.

### Option B — asciinema (clean terminal-only .cast, embeddable in README)

```sh
nix profile install nixpkgs#asciinema      # or: pipx install asciinema
asciinema rec instascript-demo.cast        # runs a shell — do the demo, then exit
# playable anywhere: https://asciinema.org/a/<id>  or  asciinema play instascript-demo.cast
```

### Recording tips

- Clear the transcript output first: `rm -rf ~/ig_intel/Inbox/*` before the
  first take (keeps the recording clean, hashes start fresh).
- Big font, no minimap clutter, `--verbose` off (default output is clean).
- Pause between commands; let each expected line appear before moving on.
- Re-record if a command hiccups — a clean 2-minute take beats a confusing one.

---

## What you get (the pitch = the artifacts)

```
<vault>/Inbox/<slug>/
  transcript.json    # verbatim ground truth — segments, words, timestamps
  transcript.txt     # plain text
  audio.wav          # normalized 16 kHz mono
  source.json        # input, title, duration, url_sha256, content_sha256
  summary.md         # --review — concise, faithful (hash frontmatter)
  flags.md           # --review — advisory non-factual-claim list (hash frontmatter)
```

Word-level timestamps in `transcript.json` feed search, captioning, or RAG.

---

## Real transcript (this reel)

```
[    0.00-    6.06] We can convert normal electromagnetic waves into gravitational waves.
[    6.36-    9.16] They're actually formulating it mathematically.
[    9.70-   16.68] Now we have the math to go along with Tom Bearden's scalar physics.
[   17.02-   22.08] I guarantee you this is just another version of Tom Bearden's scalar physics.
[   22.66-   27.84] This is the math that allows us to literally manipulate spacetime.
```

---

## Video file for your GitHub README

Already saved at `assets/demo/instascript-demo-reel.mp4` (2.4 MB). Media is
`.gitignore`d — force-add it:

```sh
git add -f assets/demo/instascript-demo-reel.mp4
```

Embed (renders on GitHub):

```html
<video controls width="360" src="assets/demo/instascript-demo-reel.mp4"></video>
```

Or: `[Watch the demo reel](assets/demo/instascript-demo-reel.mp4)`

---

## Upwork proposal pitch

- Reel / podcast / meeting audio → searchable, timestamped transcripts — 100 %
  local, zero per-minute cost, CPU-only.
- One command handles Instagram, YouTube, TikTok, or a local file.
- **Dedup built in** — links and audio are content-hashed; nothing is ever
  transcribed twice.
- Optional AI pass (DeepSeek) summarizes and *flags* non-factual claims with the
  exact quote — built-in fact-check handoff for research and journalism.
- Verbatim JSON with word-level timestamps → feed your own search, captions, or
  RAG pipeline.
