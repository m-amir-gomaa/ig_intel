# Sonaweft — audio to source-linked notes

[Open Sonaweft](https://m-amir-gomaa--sonaweft-web-app.us-east.modal.run) · [Product contract](docs/PRODUCT.md) · [Operations](docs/OPERATIONS.md) · [Release evidence](docs/RELEASE.md)

Turn authorized recordings into timestamped transcripts, editable drafts, subtitles and portable Markdown. Hear each segment while correcting it. Original speech recognition, your corrections and optional AI notes remain separate. Formerly instaScript / Transcript Studio; existing commands, Python imports and GitHub URLs remain compatible.

## Hosted workflow

1. Upload English audio/video, up to **64 MiB / 60 minutes**; inspection returns a quote without starting transcription.
2. Confirm media rights, then request a bounded **30-second** sample or paid processing when commercial access opens.
3. Optionally consent to sending transcript text to DeepSeek for standard/deeper review. Audio is not sent to DeepSeek.
4. Follow the job, hear timestamped segments, search text and save separate corrections with revision checks.
5. Export original Markdown/text/JSON/SRT/VTT, corrected Markdown/JSON, optional summary/research questions and a hashed `instascript-export/v1` manifest.

AI suggestions never silently replace the original. Source questions quote actual segments; explicit Crossref lookup returns scholarly metadata candidates, not factual verdicts. Hosted URL downloads, diarization, speaker identification and certified transcription are not implemented; use an authorized upload or the local CLI.

The sample is once per workspace/IP hash, subject to three global samples/day, twenty/month and additional admission/storage caps. Sources/results expire after 48 hours with hourly cleanup. Paid packs remain **closed** pending Paddle seller/website approval and real payment acceptance tests. No card is needed for an available sample.

## Service pricing

One-time **$5 / $10 processing packs**, no recurring access fee. Credit is reserved before dispatch and consumed only when the complete selected result succeeds; failure returns the full reservation. Explicit retries get a fresh quote and can reuse retained ASR.

| Processing | Per job | Per started minute | 60 minutes |
|---|---:|---:|---:|
| Transcription | $0.15 | $0.015 | $1.05 |
| With standard review | $0.25 | $0.020 | $1.45 |
| With advanced review | $0.35 | $0.025 | $1.85 |

Applicable tax is handled at checkout. These are service tariffs, not exact provider reimbursements or guaranteed margins. Sonaweft/Pageweft balances are independent processing entitlements.

## Local CLI

Python **3.13** is the tested pip environment. Install FFmpeg/FFprobe and yt-dlp separately. Local recognition uses CPU/int8; downloaded models and optional provider charges are the operator's responsibility.

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install .
bin/sonaweft recording.mp3 --out ./out
bin/sonaweft 'https://example.org/authorized-media' --out ./out
bin/sonaweft --queue ./queue.md --out ./out
bin/sonaweft recording.mp3 --review --review-model standard --out ./out
bin/sonaweft --export-item ./out/ITEM --format vtt
```

The launchers resolve NixOS wheel libraries dynamically, prefer an existing tested `.venv-web`, otherwise `.venv`; `SONAWEFT_PYTHON` overrides. Export `DEEPSEEK_API_KEY` only for review. `.env` files are not automatically loaded; see [.env.example](.env.example). `SONAWEFT_VAULT` takes precedence over legacy `IG_INTEL_VAULT`; the old `~/ig_intel/Inbox` default is preserved.

Private `.pending` checkpoints support retry without repeating successful ASR. Complete exports publish atomically; hashes detect modified/incomplete output, which is preserved. Source/model/review identity suppresses repeats. Cross-path perceptual deduplication is not promised. A killed process may leave `running.lock`; verify it has stopped before removing only that lock.

Local yt-dlp may explicitly use configured browser cookies when a source requires login. Hosted uploads never use the owner's browser session. Live site access depends on permissions and upstream changes; metadata fixtures do not certify platform downloads.

## Deployment and development

FastAPI, an on-demand Modal L4 speech worker, separate optional LLM processing and a serialized SQLite ledger use independent Sonaweft volumes/secrets. Workers scale to zero; storage, schedules and requests still consume resources. Large model weights are cached in the cloud, not on the laptop's 2 GB GPU.

```sh
.venv/bin/python -m pip install '.[web,cloud]'
# Configure your own account and three secrets described in OPERATIONS.md.
.venv/bin/python -m modal deploy app.py

python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -q
ruff check --select E9,F63,F7,F82,F401 app.py instascript sonaweft_web scripts tests
node --check sonaweft_web/static/app.js
node --check sonaweft_web/static/checkout.js
```

FFmpeg is required by boundary tests. Tests use real temporary SQLite/files/FFprobe with fake model dispatch and mocked payment APIs. Actual model/cloud/browser evidence is recorded separately. [requirements-web.lock](requirements-web.lock) records the tested Linux development environment; [app.py](app.py) pins cloud dependencies and an immutable model revision. No sibling repository is needed. Nix files have a separate verification status in RELEASE.md. New self-hosters need their own credentials, products and approvals.

MIT application code; upstream tools/models have their own licenses. No speech model guarantees accuracy across accents, noise or long recordings.
