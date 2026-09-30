#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
package_dir="$project_dir/package"
helper_dir="$HOME/.local/bin"
settings="$HOME/.claude/settings.json"

mkdir -p "$helper_dir"
install -m 0755 "$project_dir/helpers/ai_usage_tracker_collect.py" "$helper_dir/ai-usage-tracker-collect"

# Earlier versions fed Claude usage through a status-line relay and a /usage
# scraper. Remove both, and the statusLine entry only if it is still ours.
legacy_relay="$helper_dir/ai-usage-tracker-claude-relay"
rm -f "$legacy_relay" "$helper_dir/ai-usage-tracker-claude-quota"
if [[ -f "$settings" ]] && jq -e --arg command "$legacy_relay" '.statusLine.command == $command' "$settings" >/dev/null; then
  backup="$settings.ai-usage-tracker.$(date +%Y%m%d-%H%M%S).bak"
  cp "$settings" "$backup"
  tmp=$(mktemp)
  jq 'del(.statusLine)' "$settings" > "$tmp"
  mv "$tmp" "$settings"
  echo "Removed the old AI Usage Tracker status-line relay from Claude settings (backup: $backup)."
fi

kpackagetool6 --type Plasma/Applet --upgrade "$package_dir" >/dev/null || kpackagetool6 --type Plasma/Applet --install "$package_dir" >/dev/null
echo "Installed AI Usage Tracker. In Plasma, open Add Widgets and add AI Usage Tracker to your panel."
