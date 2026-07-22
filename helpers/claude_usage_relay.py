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
    five_used = five_hour.get("used_percentage")
    five_reset = five_hour.get("resets_at")
    seven_used = seven_day.get("used_percentage")
    seven_reset = seven_day.get("resets_at")
    # Claude also invokes status-line commands for events that contain no
    # quota data. Never let one of those erase a usable previous snapshot.
    if None in (five_used, five_reset, seven_used, seven_reset):
        raise ValueError("status-line payload did not include both quota windows")
    snapshot = {
        "schemaVersion": 1,
        "updatedAt": int(time.time()),
        "fiveHour": {"usedPercent": five_used, "resetsAt": five_reset},
        "sevenDay": {"usedPercent": seven_used, "resetsAt": seven_reset},
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
