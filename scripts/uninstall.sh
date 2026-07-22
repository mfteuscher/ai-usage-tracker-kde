#!/usr/bin/env bash
set -euo pipefail

widget_id="com.michaelteuscher.aiusagetracker"
relay_command="$HOME/.local/bin/ai-usage-tracker-claude-relay"
settings="$HOME/.claude/settings.json"

read -r -p "Remove AI Usage Tracker widget, helpers, and its Claude status-line relay? [y/N] " reply
[[ "$reply" =~ ^[Yy]$ ]] || exit 0

kpackagetool6 --type Plasma/Applet --remove "$widget_id" >/dev/null 2>&1 || true
if [[ -f "$settings" ]] && jq -e --arg command "$relay_command" '.statusLine.command == $command' "$settings" >/dev/null; then
  tmp=$(mktemp)
  jq 'del(.statusLine)' "$settings" > "$tmp"
  mv "$tmp" "$settings"
fi
rm -f "$HOME/.local/bin/ai-usage-tracker-collect" "$HOME/.local/bin/ai-usage-tracker-claude-relay" "$HOME/.local/bin/ai-usage-tracker-claude-quota"
rm -rf "${XDG_RUNTIME_DIR:-/tmp}/ai-usage-tracker" "$HOME/.local/state/ai-usage-tracker"
echo "AI Usage Tracker removed."
