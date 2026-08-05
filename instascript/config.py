"""Config — env-driven, environment-agnostic.

No OS or directory structure is hardcoded. Override via environment variables;
defaults are neutral so the repo works anywhere. Locally, point IG_INTEL_VAULT
at your vault (e.g. set it in your shell profile or a wrapper).

    IG_INTEL_VAULT   Obsidian vault root (pipeline output + knowledge)
    DEEPSEEK_API_KEY DeepSeek API key (for --review / --review-item)
    OPENROUTER_API_KEY  reserved for the RAG phase
"""

import os
from pathlib import Path

HOME = Path.home()

# Single home for pipeline output + knowledge (defaults to ~/ig_intel).
IG_INTEL_VAULT = Path(os.environ.get("IG_INTEL_VAULT", HOME / "ig_intel"))

# Pipeline output root — the vault Inbox is the transcript entry point.
PIPELINE_INBOX = IG_INTEL_VAULT / "Inbox"

# Standard batch queue: a markdown checklist of links. `instascript --queue`
# processes every `- [ ]` line through the pipeline into Inbox, then deletes it.
QUEUE_FILE = PIPELINE_INBOX / "queue.md"

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# Browser to source login cookies from when a platform (e.g. Instagram) needs
# a logged-in session. Comma-separated list = retry order. Empty disables.
YTDLP_COOKIES_FROM_BROWSER = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "firefox")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

WHISPER_MODEL_DEFAULT = "small"
