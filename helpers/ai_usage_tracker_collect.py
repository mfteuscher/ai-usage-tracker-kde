#!/usr/bin/env python3
"""Collect subscription-limit data without reading provider credentials."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STALE_AFTER_SECONDS = 600
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "ai-usage-tracker"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "ai-usage-tracker"


def window(used: Any, resets_at: Any, duration: Any, label: str) -> dict[str, Any] | None:
    if used is None:
        return None
    try:
        return {"usedPercent": float(used), "resetsAt": int(resets_at) if resets_at else None,
                "durationMinutes": int(duration) if duration else None, "label": label}
    except (TypeError, ValueError):
        return None


def unavailable(message: str) -> dict[str, Any]:
    return {"state": "unavailable", "message": message, "lastUpdatedAt": None, "primary": None, "secondary": None}


def duration_label(minutes: Any, fallback: str) -> str:
    try:
        value = int(minutes)
    except (TypeError, ValueError):
        return fallback
    if abs(value - 300) <= 30:
        return "Session (5 hours)"
    if abs(value - 10080) <= 1440:
        return "Weekly (7 days)"
    if value >= 1440 and value % 1440 == 0:
        return f"{value // 1440}-day window"
    return f"{value}-minute window"


def claude() -> dict[str, Any]:
    path = RUNTIME_DIR / "claude.json"
    try:
        data = json.loads(path.read_text())
        updated = int(data["updatedAt"])
        age = int(time.time()) - updated
        state = "fresh" if age <= STALE_AFTER_SECONDS else "stale"
        return {"state": state, "source": "Claude Code status line", "lastUpdatedAt": updated,
                "message": "Claude Code has not refreshed usage recently." if state == "stale" else "",
                "primary": window(data.get("fiveHour", {}).get("usedPercent"), data.get("fiveHour", {}).get("resetsAt"), 300, "Session (5 hours)"),
                "secondary": window(data.get("sevenDay", {}).get("usedPercent"), data.get("sevenDay", {}).get("resetsAt"), 10080, "Weekly (7 days)")}
    except FileNotFoundError:
        return unavailable("Open Claude Code and complete one response to sync its usage.")
    except (ValueError, KeyError, OSError):
        return unavailable("Claude usage data could not be read.")


def rpc(process: subprocess.Popen[str], request_id: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    assert process.stdin and process.stdout
    process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}) + "\n")
    process.stdin.flush()
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if not line:
            break
        response = json.loads(line)
        if response.get("id") == request_id:
            if "error" in response:
                raise RuntimeError(response["error"].get("message", "Codex app-server error"))
            return response.get("result", {})
    raise RuntimeError("Timed out waiting for Codex app-server")


def codex() -> dict[str, Any]:
    executable = shutil.which("codex")
    if not executable:
        return unavailable("Codex CLI was not found in PATH.")
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen([executable, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        # Codex's stable app-server protocol requires initialization before account RPCs.
        rpc(process, 1, "initialize", {"clientInfo": {"name": "ai-usage-tracker", "version": "0.1.0"}, "capabilities": {}})
        account = rpc(process, 2, "account/read", {"refreshToken": False}).get("account")
        if not account or account.get("type") != "chatgpt":
            return unavailable("Sign in to Codex with your ChatGPT subscription to show limits.")
        limits = rpc(process, 3, "account/rateLimits/read").get("rateLimits") or {}
        primary = limits.get("primary") or {}
        secondary = limits.get("secondary") or {}
        primary_minutes = primary.get("windowDurationMins")
        secondary_minutes = secondary.get("windowDurationMins")
        return {"state": "fresh", "source": "Codex app-server", "lastUpdatedAt": int(time.time()), "message": "",
                "planType": account.get("planType"),
                "primary": window(primary.get("usedPercent"), primary.get("resetsAt"), primary_minutes, duration_label(primary_minutes, "Current window")),
                "secondary": window(secondary.get("usedPercent"), secondary.get("resetsAt"), secondary_minutes, duration_label(secondary_minutes, "Secondary window")),
                "rateLimitReachedType": limits.get("rateLimitReachedType")}
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        return unavailable(f"Codex usage is unavailable: {error}")
    finally:
        if process:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


def notify(providers: dict[str, Any], enabled: bool) -> None:
    if not enabled or not shutil.which("notify-send"):
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    marker_path = STATE_DIR / "notified.json"
    try:
        markers = json.loads(marker_path.read_text())
    except (OSError, ValueError):
        markers = {}
    for provider_name, provider in providers.items():
        if provider.get("rateLimitReachedType"):
            key = f"{provider_name}:reached:{provider['rateLimitReachedType']}"
            if key not in markers:
                subprocess.run(["notify-send", "AI Usage Tracker", f"{provider_name.title()} reports that its usage limit has been reached."], check=False)
                markers[key] = int(time.time())
        for role in ("primary", "secondary"):
            item = provider.get(role)
            if not item:
                continue
            for threshold in (75, 90):
                if item["usedPercent"] < threshold:
                    continue
                key = f"{provider_name}:{role}:{threshold}:{item.get('resetsAt')}"
                if key in markers:
                    continue
                subprocess.run(["notify-send", "AI Usage Tracker", f"{provider_name.title()} {item['label']} is {round(item['usedPercent'])}% used."], check=False)
                markers[key] = int(time.time())
    temporary = marker_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(markers))
    os.chmod(temporary, 0o600)
    temporary.replace(marker_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notifications", choices=("on", "off"), default="on")
    args = parser.parse_args()
    providers = {"claude": claude(), "codex": codex()}
    notify(providers, args.notifications == "on")
    print(json.dumps({"schemaVersion": SCHEMA_VERSION, "collectedAt": int(time.time()), "providers": providers}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
