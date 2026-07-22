#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
package_dir="$project_dir/package"
helper_dir="$HOME/.local/bin"
claude_dir="$HOME/.claude"
settings="$claude_dir/settings.json"
backup=""

mkdir -p "$helper_dir" "$claude_dir"
install -m 0755 "$project_dir/helpers/ai_usage_tracker_collect.py" "$helper_dir/ai-usage-tracker-collect"
install -m 0755 "$project_dir/helpers/claude_usage_relay.py" "$helper_dir/ai-usage-tracker-claude-relay"
install -m 0755 "$project_dir/helpers/ai-usage-tracker-claude-quota" "$helper_dir/ai-usage-tracker-claude-quota"

if [[ -f "$settings" ]]; then
  jq empty "$settings" >/dev/null
  backup="$settings.ai-usage-tracker.$(date +%Y%m%d-%H%M%S).bak"
  cp "$settings" "$backup"
else
  printf '{}\n' > "$settings"
fi

relay_command="$helper_dir/ai-usage-tracker-claude-relay"
existing_command=$(jq -r '.statusLine.command // empty' "$settings")
if [[ -n "$existing_command" && "$existing_command" != "$relay_command" ]]; then
  echo "Existing Claude statusLine found; not replacing it: $existing_command" >&2
  echo "Install aborted. Restore unchanged settings${backup:+ from $backup} and configure the relay manually." >&2
  exit 2
fi

tmp=$(mktemp)
jq --arg command "$relay_command" '.statusLine = {type: "command", command: $command}' "$settings" > "$tmp"
mv "$tmp" "$settings"

kpackagetool6 --type Plasma/Applet --upgrade "$package_dir" >/dev/null || kpackagetool6 --type Plasma/Applet --install "$package_dir" >/dev/null
echo "Installed AI Usage Tracker. In Plasma, open Add Widgets and add AI Usage Tracker to your panel."
[[ -n "$backup" ]] && echo "Claude settings backup: $backup"
