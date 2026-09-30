#!/usr/bin/env python3
"""Collect subscription-limit data without reading provider credentials."""
from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 2
PROBE_TIMEOUT_SECONDS = 20
SESSION_MINUTES = 5 * 60
WEEK_MINUTES = 7 * 24 * 60
MONTH_MINUTES = 30 * 24 * 60
KIND_ORDER = {"session": 0, "weekly": 1, "monthly": 2, "other": 3}
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "ai-usage-tracker"

# Keep the Claude probe from running the user's hooks, MCP servers, or IDE
# discovery on every refresh, and from leaving a session transcript behind.
CLAUDE_PROBE_ARGS = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                     "--no-session-persistence", "--disable-slash-commands", "--strict-mcp-config",
                     "--mcp-config", '{"mcpServers":{}}', "--settings", '{"disableAllHooks":true}']
CLAUDE_PROBE_ENV = {"ENABLE_CLAUDEAI_MCP_SERVERS": "false", "CLAUDE_CODE_AUTO_CONNECT_IDE": "0",
                    "CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL": "1"}


class ProbeFailed(Exception):
    """A read that failed this time; the last good snapshot stays on screen."""


class Unsupported(Exception):
    """An account that can never report subscription windows, such as an API key."""


def window(window_id: str, kind: str, label: str, used: Any, resets_at: Any, duration: Any) -> dict[str, Any] | None:
    """One rolling quota window. `id` is stable per provider so notifications dedupe across reads."""
    try:
        return {"id": window_id, "kind": kind, "label": label,
                "usedPercent": max(0.0, min(100.0, float(used))),
                "resetsAt": int(resets_at) if resets_at else None,
                "durationMinutes": int(duration) if duration else None}
    except (TypeError, ValueError):
        return None


def sorted_windows(windows: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Drop unreadable windows and order session, weekly, monthly; the first one drives the panel bar."""
    return sorted((item for item in windows if item), key=lambda item: (KIND_ORDER[item["kind"]], item["id"]))


def unavailable(message: str, cli_available: bool = True) -> dict[str, Any]:
    return {"state": "unavailable", "message": message, "cliAvailable": cli_available,
            "lastUpdatedAt": None, "windows": []}


def kind_for_duration(minutes: int) -> str:
    if minutes >= MONTH_MINUTES:
        return "monthly"
    return "weekly" if minutes >= WEEK_MINUTES else "session"


def duration_label(minutes: int) -> str:
    if abs(minutes - SESSION_MINUTES) <= 30:
        return "Session (5 hours)"
    if abs(minutes - WEEK_MINUTES) <= 1440:
        return "Weekly (7 days)"
    if abs(minutes - MONTH_MINUTES) <= 2 * 1440:
        return "Monthly (30 days)"
    if minutes >= 1440 and minutes % 1440 == 0:
        return f"{minutes // 1440}-day window"
    return f"{minutes}-minute window"


def epoch_from_iso(value: Any) -> int | None:
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except (TypeError, ValueError):
        return None


class JsonLinesProcess:
    """A CLI speaking newline-delimited JSON on stdio. Every failure surfaces as a short ProbeFailed."""

    def __init__(self, name: str, args: list[str], env: dict[str, str] | None = None, cwd: Path | None = None):
        self.name = name
        self.lines: queue.Queue[str | None] = queue.Queue()
        try:
            self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                            text=True, env={**os.environ, **(env or {})}, cwd=cwd)
        except OSError as error:
            raise ProbeFailed(f"{name} could not be started to read usage.") from error
        # A reader thread lets waits time out even when the CLI goes quiet mid-line.
        self.reader = threading.Thread(target=self._pump, daemon=True)
        self.reader.start()

    def _pump(self) -> None:
        assert self.process.stdout
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def send(self, message: dict[str, Any]) -> None:
        assert self.process.stdin
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
        except OSError as error:
            raise ProbeFailed(f"{self.name} exited before it could report usage.") from error

    def wait_for(self, matches: Callable[[dict[str, Any]], bool], deadline: float) -> dict[str, Any]:
        while True:
            try:
                line = self.lines.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                raise ProbeFailed(f"{self.name} did not answer the usage request.") from None
            if line is None:
                raise ProbeFailed(f"{self.name} exited before it could report usage.")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and matches(message):
                return message

    def __enter__(self) -> JsonLinesProcess:
        return self

    def __exit__(self, *_: object) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.reader.join(timeout=1)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass


def claude_limits(response: dict[str, Any]) -> dict[str, Any]:
    """Map Claude's `get_usage` control response: percentages are 0-100 and resets are ISO timestamps."""
    rate_limits = response.get("rate_limits")
    if not response.get("rate_limits_available") or not isinstance(rate_limits, dict):
        raise Unsupported("This Claude account has no subscription limits.")
    windows = []
    for window_id, kind, minutes in (("five_hour", "session", SESSION_MINUTES), ("seven_day", "weekly", WEEK_MINUTES)):
        item = rate_limits.get(window_id) or {}
        windows.append(window(window_id, kind, duration_label(minutes), item.get("utilization"),
                              epoch_from_iso(item.get("resets_at")), minutes))
    # Per-model weekly buckets (such as Fable) that count separately from the all-models week.
    for item in rate_limits.get("model_scoped") or []:
        name = item.get("display_name") if isinstance(item, dict) else None
        if isinstance(name, str) and name.strip():
            slug = "".join(char if char.isalnum() else "_" for char in name.strip().lower())
            windows.append(window(f"seven_day_{slug}", "weekly", f"Weekly ({name.strip()})", item.get("utilization"),
                                  epoch_from_iso(item.get("resets_at")), WEEK_MINUTES))
    windows = sorted_windows(windows)
    if not windows:
        raise ProbeFailed("Claude Code did not report any limits.")
    plan = response.get("subscription_type")
    return {"plan": plan.title() if isinstance(plan, str) else None, "windows": windows}


def claude() -> dict[str, Any]:
    """Ask Claude Code for its `/usage` data over the stream-json control protocol, without sending a prompt."""
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
    with JsonLinesProcess("Claude Code", ["claude", *CLAUDE_PROBE_ARGS], env=CLAUDE_PROBE_ENV, cwd=STATE_DIR) as cli:
        cli.send({"type": "control_request", "request_id": "initialize", "request": {"subtype": "initialize"}})
        cli.send({"type": "control_request", "request_id": "usage",
                  "request": {"subtype": "get_usage", "skip_behaviors": True}})
        message = cli.wait_for(lambda message: message.get("type") == "control_response"
                               and (message.get("response") or {}).get("request_id") == "usage", deadline)
    response = message["response"]
    if response.get("subtype") != "success":
        raise ProbeFailed("Claude Code could not read usage.")
    return claude_limits(response.get("response") or {})


def codex_limits(result: dict[str, Any]) -> dict[str, Any]:
    """Map Codex's `account/rateLimits/read` result, keeping only the main `codex` allowance."""
    # The legacy `rateLimits` snapshot can describe a model-specific bucket (such as Spark).
    snapshot = (result.get("rateLimitsByLimitId") or {}).get("codex") or result.get("rateLimits") or {}
    if snapshot.get("limitId") not in (None, "codex"):
        snapshot = {}
    # `primary`/`secondary` are positions, not durations: Free and Go plans have one monthly allowance.
    primary_fallback = MONTH_MINUTES if snapshot.get("planType") in ("free", "go") else SESSION_MINUTES
    windows = []
    for window_id, fallback in (("primary", primary_fallback), ("secondary", WEEK_MINUTES)):
        item = snapshot.get(window_id) or {}
        try:
            minutes = int(item.get("windowDurationMins") or fallback)
        except (TypeError, ValueError):
            minutes = fallback
        windows.append(window(window_id, kind_for_duration(minutes), duration_label(minutes), item.get("usedPercent"),
                              item.get("resetsAt"), minutes))
    windows = sorted_windows(windows)
    if not windows:
        raise ProbeFailed("Codex did not report any limits.")
    return {"windows": windows, "rateLimitReachedType": snapshot.get("rateLimitReachedType")}


def codex() -> dict[str, Any]:
    deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
    with JsonLinesProcess("Codex", ["codex", "app-server"]) as cli:
        def rpc(request_id: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            cli.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
            response = cli.wait_for(lambda message: message.get("id") == request_id, deadline)
            if "error" in response:
                raise ProbeFailed(f"Codex could not read usage (JSON-RPC {response['error'].get('code', 'error')}).")
            return response.get("result") or {}

        # Codex's stable app-server protocol requires initialization before account RPCs.
        rpc(1, "initialize", {"clientInfo": {"name": "ai-usage-tracker", "version": "0.2.0"}, "capabilities": {}})
        account = rpc(2, "account/read", {"refreshToken": False}).get("account")
        if not account or account.get("type") != "chatgpt":
            raise Unsupported("Sign in to Codex with your ChatGPT subscription to show limits.")
        limits = codex_limits(rpc(3, "account/rateLimits/read"))
    plan = account.get("planType")
    return {**limits, "plan": plan.title() if isinstance(plan, str) else None}


def write_private_json(path: Path, data: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data))
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def collect(name: str, executable: str, probe: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run one provider probe and resolve it against the last good snapshot.

    A transient failure keeps the last good windows, marked stale; an unsupported
    account is authoritative and clears them.
    """
    if not shutil.which(executable):
        return unavailable(f"The {executable} CLI was not found in PATH.", cli_available=False)
    last_good_path = STATE_DIR / f"{name}.json"
    try:
        snapshot = {"state": "fresh", "message": "", "cliAvailable": True,
                    "lastUpdatedAt": int(time.time()), **probe()}
    except Unsupported as reason:
        last_good_path.unlink(missing_ok=True)
        return unavailable(str(reason))
    except ProbeFailed as failure:
        try:
            last_good = json.loads(last_good_path.read_text())
        except (OSError, ValueError):
            return unavailable(str(failure))
        return {**last_good, "state": "stale", "message": f"{failure} Showing the last successful reading."}
    write_private_json(last_good_path, snapshot)
    return snapshot


def notify(providers: dict[str, Any], enabled: bool) -> None:
    if not enabled or not shutil.which("notify-send"):
        return
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
        for item in provider.get("windows", []):
            for threshold in (75, 90):
                if item["usedPercent"] < threshold:
                    continue
                key = f"{provider_name}:{item['id']}:{threshold}:{item.get('resetsAt')}"
                if key in markers:
                    continue
                subprocess.run(["notify-send", "AI Usage Tracker", f"{provider_name.title()} {item['label']} is {round(item['usedPercent'])}% used."], check=False)
                markers[key] = int(time.time())
    write_private_json(marker_path, markers)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notifications", choices=("on", "off"), default="on")
    parser.add_argument("--providers", default="claude,codex", help="Comma-separated providers to collect")
    args = parser.parse_args()
    selected = {name.strip() for name in args.providers.split(",")}
    probes = {"claude": ("claude", claude), "codex": ("codex", codex)}
    providers = {name: collect(name, executable, probe) for name, (executable, probe) in probes.items() if name in selected}
    notify(providers, args.notifications == "on")
    print(json.dumps({"schemaVersion": SCHEMA_VERSION, "collectedAt": int(time.time()), "providers": providers}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
