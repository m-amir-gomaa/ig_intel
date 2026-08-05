#!/usr/bin/env bash
# Install the ig_intel UTCP tools (headless Claude Code drivers) for this repo.
#
#   UTCP_DIR          utcp bridge home            (default: $HOME/.utcp)
#   IG_INTEL_VAULT    Obsidian vault root          (required)
#   TAVILY_API_KEY    key for live web research    (optional; needed by ig_research)
#
# Example:
#   IG_INTEL_VAULT=~/ig_intel TAVILY_API_KEY=tvly-... ./utcp/install.sh
#
# Idempotent. After running, restart the Claude Code session so the bridge loads
# the new tools. Verify with:  mcp__utcp__list_tools  (expect ig_* tools).
set -euo pipefail

UTCP_DIR="${UTCP_DIR:-$HOME/.utcp}"
VAULT="${IG_INTEL_VAULT:?set IG_INTEL_VAULT to your vault root}"
KEY="${TAVILY_API_KEY:-}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T1="$REPO/utcp/igintel.json.template"
T2="$REPO/utcp/igintel-mcp.json.template"

mkdir -p "$UTCP_DIR/manuals"

# 1. Tool definitions — paths in the template are placeholders; inject real ones.
sed \
  -e "s|{{IG_INTEL_VAULT}}|$VAULT|g" \
  -e "s|{{UTCP_DIR}}|$UTCP_DIR|g" \
  "$T1" > "$UTCP_DIR/manuals/igintel.json"
echo "→ wrote $UTCP_DIR/manuals/igintel.json"

# 2. MCP config for headless research sessions (tavily). Key never committed.
if [ -n "$KEY" ]; then
  sed -e "s|{{TAVILY_API_KEY}}|$KEY|g" "$T2" > "$UTCP_DIR/igintel-mcp.json"
  echo "→ wrote $UTCP_DIR/igintel-mcp.json"
else
  sed -e "s|{{TAVILY_API_KEY}}|REPLACE_ME|g" "$T2" > "$UTCP_DIR/igintel-mcp.json"
  echo "⚠ no TAVILY_API_KEY set — wrote $UTCP_DIR/igintel-mcp.json with a placeholder."
  echo "  (ig_research needs a real key; everything else works without it.)"
fi

# 3. Register the manual in the utcp bridge config (idempotent).
python3 - "$UTCP_DIR" <<'EOF'
import json, sys, os
utcp = sys.argv[1]
cfg_path = os.path.join(utcp, ".utcp_config.json")
cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
entries = cfg.setdefault("manual_call_templates", [])
entry = {
    "name": "igintel",
    "call_template_type": "file",
    "file_path": os.path.join(utcp, "manuals", "igintel.json"),
    "allowed_communication_protocols": ["cli"],
}
if not any(e.get("name") == "igintel" for e in entries):
    entries.append(entry)
    json.dump(cfg, open(cfg_path, "w"), indent=2)
    print(f"→ registered igintel manual in {cfg_path}")
else:
    print(f"· igintel already registered in {cfg_path}")
EOF

echo
echo "Done. Restart your Claude Code session, then confirm the tools loaded:"
echo "  mcp__utcp__list_tools   → expect: ig_process_queue, ig_ingest, ig_review,"
echo "                              ig_organize_inbox, ig_research, ig_vault_task"
echo
echo "Headless sessions need ANTHROPIC_* env vars routed to your LLM endpoint"
echo "(DeepSeek here) — see docs/claude-code.md → 'API keys'."
