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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_VERSION = 1
STALE_AFTER_SECONDS = 600
CLAUDE_QUOTA_CACHE_SECONDS = 300
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


def unavailable(message: str, cli_available: bool = True) -> dict[str, Any]:
    return {"state": "unavailable", "message": message, "cliAvailable": cli_available,
            "lastUpdatedAt": None, "primary": None, "secondary": None}


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


def claude_status_line() -> dict[str, Any]:
    if not shutil.which("claude"):
        return unavailable("Claude Code CLI was not found in PATH.", cli_available=False)
    path = RUNTIME_DIR / "claude.json"
    try:
        data = json.loads(path.read_text())
        updated = int(data["updatedAt"])
        age = int(time.time()) - updated
        state = "fresh" if age <= STALE_AFTER_SECONDS else "stale"
        stale_message = f"Claude usage was last synced {max(1, age // 60)} minutes ago. Send a prompt in Claude Code to refresh it."
        primary = window(data.get("fiveHour", {}).get("usedPercent"), data.get("fiveHour", {}).get("resetsAt"), 300, "Session (5 hours)")
        secondary = window(data.get("sevenDay", {}).get("usedPercent"), data.get("sevenDay", {}).get("resetsAt"), 10080, "Weekly (7 days)")
        if not primary or not secondary:
            return unavailable("Claude Code has not supplied quota data yet. Complete a response or use the /usage scraper.")
        return {"state": state, "source": "Claude Code status line", "cliAvailable": True, "lastUpdatedAt": updated,
                "message": stale_message if state == "stale" else "",
                "primary": primary, "secondary": secondary}
    except FileNotFoundError:
        return unavailable("Open Claude Code and complete one response to sync its usage.")
    except (ValueError, KeyError, OSError):
        return unavailable("Claude usage data could not be read.")


def claude_quota_scraper() -> Path | None:
    installed = shutil.which("ai-usage-tracker-claude-quota")
    if installed:
        return Path(installed)
    bundled = Path(__file__).with_name("ai-usage-tracker-claude-quota")
    return bundled if bundled.is_file() else None


def quota_reset_timestamp(value: Any, now: datetime | None = None) -> int | None:
    """Translate claude-quota's local, human-readable reset string to epoch seconds."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    timezone = "America/Denver"
    if text.endswith(")") and "(" in text:
        text, timezone = text.rsplit("(", 1)
        text, timezone = text.strip(), timezone[:-1].strip()
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = datetime.now().astimezone().tzinfo
    current = now.astimezone(zone) if now else datetime.now(zone)
    normalized = text.upper().replace(" ", "")
    formats = ("%I:%M%p", "%I%p")
    for pattern in formats:
        try:
            parsed = datetime.strptime(normalized, pattern)
            result = current.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            if result <= current:
                result += timedelta(days=1)
            return int(result.timestamp())
        except ValueError:
            pass
    for pattern in ("%b%d,%I:%M%p", "%b%d,%I%p"):
        try:
            parsed = datetime.strptime(f"{current.year} {normalized}", "%Y " + pattern)
            result = current.replace(month=parsed.month, day=parsed.day, hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            if result < current - timedelta(days=1):
                result = result.replace(year=result.year + 1)
            return int(result.timestamp())
        except ValueError:
            pass
    return None


def quota_window(data: dict[str, Any], key: str, duration: int, label: str) -> dict[str, Any] | None:
    item = data.get(key) or {}
    return window(item.get("pct"), quota_reset_timestamp(item.get("resets")), duration, label)


def claude_usage(force: bool = False) -> dict[str, Any]:
    scraper = claude_quota_scraper()
    if not scraper:
        return unavailable("The optional Claude /usage scraper is not installed.")
    if not shutil.which("screen"):
        return unavailable("The Claude /usage scraper needs GNU screen.")
    cache_path = STATE_DIR / "claude-quota.json"
    data: dict[str, Any] | None = None
    captured = None
    try:
        cached = json.loads(cache_path.read_text())
        captured = int(cached["capturedAt"])
        if not force and time.time() - captured < CLAUDE_QUOTA_CACHE_SECONDS:
            data = cached["data"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if data is None:
        try:
            result = subprocess.run(["bash", str(scraper)], capture_output=True, text=True, timeout=45, check=True)
            data = json.loads(result.stdout)
            captured = int(time.time())
            STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"capturedAt": captured, "data": data}))
            os.chmod(temporary, 0o600)
            temporary.replace(cache_path)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return unavailable(f"Claude /usage refresh failed: {error}")
    return {"state": "fresh", "source": "Claude Code /usage scraper", "cliAvailable": True,
            "lastUpdatedAt": captured, "message": "",
            "primary": quota_window(data, "session", 300, "Session (5 hours)"),
            "secondary": quota_window(data, "week_all", 10080, "Weekly (7 days)"),
            "additional": [quota_window(data, key, 10080, "Weekly (" + key.removeprefix("week_").replace("_", " ").title() + ")")
                           for key in data if key.startswith("week_") and key != "week_all"]}


def claude(source: str = "statusline", force_usage: bool = False) -> dict[str, Any]:
    if source == "usage":
        quota = claude_usage(force_usage)
        if quota["state"] != "unavailable":
            return quota
        fallback = claude_status_line()
        if fallback["state"] != "unavailable":
            fallback["state"] = "stale"
            fallback["message"] = quota["message"] + " Showing the last status-line update instead."
            return fallback
        return quota
    return claude_status_line()


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
        return unavailable("Codex CLI was not found in PATH.", cli_available=False)
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
        return {"state": "fresh", "source": "Codex app-server", "cliAvailable": True, "lastUpdatedAt": int(time.time()), "message": "",
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
    parser.add_argument("--providers", default="claude,codex", help="Comma-separated providers to collect")
    parser.add_argument("--claude-source", choices=("statusline", "usage"), default="statusline")
    parser.add_argument("--force-claude-usage", action="store_true", help="Bypass the /usage scraper cache")
    args = parser.parse_args()
    selected = {name.strip() for name in args.providers.split(",") if name.strip() in {"claude", "codex"}}
    providers = {}
    if "claude" in selected:
        providers["claude"] = claude(args.claude_source, args.force_claude_usage)
    if "codex" in selected:
        providers["codex"] = codex()
    notify(providers, args.notifications == "on")
    print(json.dumps({"schemaVersion": SCHEMA_VERSION, "collectedAt": int(time.time()), "providers": providers}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
