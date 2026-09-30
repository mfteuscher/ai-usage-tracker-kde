#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"

# Validate every packaged QML, SVG, and XML resource before replacing the live widget.
# /usr/bin/qmllint is often the Qt 5 build, which cannot check this Qt 6 widget.
qmllint=$(command -v qmllint6 || echo /usr/lib/qt6/bin/qmllint)
[[ -x "$qmllint" ]] || { echo "Qt 6 qmllint not found; install qt6-declarative." >&2; exit 1; }
find package -type f -name '*.qml' -print0 | xargs -0 -r "$qmllint"
find package -type f -name '*.svg' -print0 | xargs -0 -r xmllint --noout
jq empty package/metadata.json
xmllint --noout package/contents/config/main.xml

# install.sh updates the complete package plus the local collector executable.
./scripts/install.sh
systemctl --user restart plasma-plasmashell.service
echo "AI Usage Tracker refreshed."
