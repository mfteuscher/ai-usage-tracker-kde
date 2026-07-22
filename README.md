# AI Usage Tracker

A personal KDE Plasma 6 panel widget for displaying Claude Code and OpenAI Codex subscription usage.

It installs as `com.michaelteuscher.aiusagetracker`. The widget reads Claude's official status-line quota payload by default and asks the locally installed Codex CLI for rate limits; it never stores provider credentials.

![AI Usage Tracker popup](docs/images/ai-usage-tracker.png)

![AI Usage Tracker in the KDE panel](docs/images/ai-usage-tracker-panel.png)

## Install

```sh
./scripts/install.sh
```

Then open **Add Widgets** in KDE Plasma and add **AI Usage Tracker** to the bottom panel.

The installer creates a timestamped backup before adding the Claude status-line relay. Its status line intentionally prints nothing, so it does not add text to Claude Code's terminal UI.

### Requirements

- KDE Plasma 6 with `kpackagetool6`
- Python 3, `jq`, and `xmllint`
- `notify-send` for optional desktop warnings
- Claude Code and/or Codex CLI, signed in with a supported subscription
- GNU Screen when using the optional accurate Claude `/usage` scraper

The widget detects which CLIs are available. A missing CLI hides that provider and disables its corresponding setting.

## Refresh and limits

The widget refreshes Codex every minute by default. Claude updates whenever Claude Code refreshes its status line, so its card shows a last-updated timestamp and becomes stale after ten minutes.

For session values that match Claude Code's `/usage` panel, enable **Use accurate /usage scraper (slower)** in widget settings. It opens `/usage` in an isolated, temporary GNU Screen session and parses the displayed limits—no prompt is sent and no credentials are read. Results are cached for five minutes during automatic refreshes; **Refresh now** always gets a fresh reading. This is intentionally optional because it depends on Claude Code's TUI format. The bundled helper is based on [`hiinaspace/claude-quota`](https://github.com/hiinaspace/claude-quota), licensed MIT.

The yellow dot beside a provider logo means its data is stale; hover it for the last-sync explanation. A red dot means the provider is unavailable or reported an error.

## Settings

Right-click the panel widget and select **Configure AI Usage Tracker…** to choose:

- Codex refresh interval
- Desktop warning toggle (warnings use 75% and 90% thresholds)
- Compact, standard, or wide panel width
- Whether to show Claude Code and/or OpenAI Codex
- Claude's official status-line feed or the optional accurate `/usage` scraper

## GitHub Releases

For releases, download the source archive, verify its published SHA-256 checksum, extract it, and run `./scripts/install.sh`. Release archives must contain the complete repository: the Plasma package, Python helpers, and install scripts are all required.

For local development, run `./scripts/refresh.sh` to validate packaged QML/SVG/XML files, reinstall the widget, and restart Plasma.

Run `./scripts/uninstall.sh` to remove the installed widget and helper files.
