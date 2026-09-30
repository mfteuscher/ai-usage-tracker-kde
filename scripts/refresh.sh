#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"

# Validate every packaged QML, SVG, and XML resource before replacing the live widget.
find package -type f -name '*.qml' -print0 | xargs -0 -r qmllint
find package -type f -name '*.svg' -print0 | xargs -0 -r xmllint --noout
jq empty package/metadata.json
xmllint --noout package/contents/config/main.xml

# install.sh updates the complete package plus the local collector executable.
./scripts/install.sh
systemctl --user restart plasma-plasmashell.service
echo "AI Usage Tracker refreshed."
