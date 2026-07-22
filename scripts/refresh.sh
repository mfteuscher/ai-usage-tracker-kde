#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"

# Validate every packaged QML, SVG, and XML resource before replacing the live widget.
find package -type f -name '*.qml' -print0 | xargs -0 -r qmllint
find package -type f -name '*.svg' -print0 | xargs -0 -r xmllint --noout
xmllint --noout package/metadata.json package/contents/config/main.xml

# install.sh updates the complete package plus both local helper executables.
./scripts/install.sh
systemctl --user restart plasma-plasmashell.service
echo "AI Usage Tracker refreshed."
