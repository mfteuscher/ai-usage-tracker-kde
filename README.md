# AI Usage Tracker

A personal KDE Plasma 6 panel widget for displaying Claude Code and OpenAI Codex subscription usage.

It installs as `com.michaelteuscher.aiusagetracker`. The widget reads Claude's official status-line quota payload and asks the locally installed Codex CLI for rate limits; it never stores provider credentials.

## Install

```sh
./scripts/install.sh
```

Then open **Add Widgets** in KDE Plasma and add **AI Usage Tracker** to the bottom panel.

The installer creates a timestamped backup before adding the Claude status-line relay. Its status line intentionally prints nothing, so it does not add text to Claude Code's terminal UI.

## Refresh and limits

The widget refreshes Codex every minute by default. Claude updates whenever Claude Code refreshes its status line, so its card shows a last-updated timestamp and becomes stale after ten minutes. This deliberately avoids undocumented OAuth endpoints and token copying.

Run `./scripts/uninstall.sh` to remove the installed widget and helper files.
