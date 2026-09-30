#!/usr/bin/env bash
set -euo pipefail

widget_id="com.michaelteuscher.aiusagetracker"

read -r -p "Remove AI Usage Tracker widget, collector, and its saved state? [y/N] " reply
[[ "$reply" =~ ^[Yy]$ ]] || exit 0

kpackagetool6 --type Plasma/Applet --remove "$widget_id" >/dev/null 2>&1 || true
rm -f "$HOME/.local/bin/ai-usage-tracker-collect"
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/ai-usage-tracker"
echo "AI Usage Tracker removed."
