#!/usr/bin/env python3
"""Receive Claude Code status-line JSON and write a safe quota-only snapshot."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "ai-usage-tracker"

try:
    payload = json.load(sys.stdin)
    limits = payload.get("rate_limits") or {}
    five_hour = limits.get("five_hour") or {}
    seven_day = limits.get("seven_day") or {}
    snapshot = {
        "schemaVersion": 1,
        "updatedAt": int(time.time()),
        "fiveHour": {"usedPercent": five_hour.get("used_percentage"), "resetsAt": five_hour.get("resets_at")},
        "sevenDay": {"usedPercent": seven_day.get("used_percentage"), "resetsAt": seven_day.get("resets_at")},
    }
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = runtime / "claude.json"
    temporary = runtime / "claude.json.tmp"
    temporary.write_text(json.dumps(snapshot))
    os.chmod(temporary, 0o600)
    temporary.replace(target)
except (OSError, ValueError, TypeError):
    pass
# Deliberately leave Claude's status line visually empty.
