# netwatch

> *Cyberpunk-themed tmux agent dashboard for Claude Code and friends.*

A persistent sidebar and CLI toolkit for monitoring, navigating, and controlling multiple AI coding agents running across tmux panes and git worktrees.

**Replaces `ps`-scanning and bash scripts with proper APIs:** Claude Code hooks (via plugin), JSONL session transcripts, and tmux control mode.

## Features

- **Claude Code plugin** — hooks declared in `plugin.json`, auto-registered when enabled. No manual settings.json edits.
- **Persistent HUD sidebar** — left-pane Textual TUI showing every pane, agent state, and working directory. Click or `j/k/Enter` to jump.
- **Real agent state** — reads Claude Code JSONL transcripts for ground-truth status (thinking / tool-use / waiting / error), not `ps aux` guessing.
- **Push, don't poll** — Claude Code hooks push state changes to a local daemon. tmux control mode delivers pane events.
- **12 CLI commands** — `install`, `uninstall`, `doctor`, `pick`, `peek`, `jump`, `broadcast`, `spawn`, `status`, `tail`, `hud`, `daemon`.
- **Cyberpunk Netrunner theme** — cyan/green HUD aesthetic. Configurable via TOML.
- **User-friendly** — interactive install wizard, manifest-tracked uninstall, actionable `doctor` diagnostics (9-point health check).

## Requirements

- Python 3.12+
- tmux 3.0+
- Claude Code CLI (for agent monitoring)

## Install

```bash
# Clone and install globally with uv
git clone https://github.com/e01n0/netwatch.git
cd netwatch
uv tool install .

# Enable the Claude Code plugin (hooks auto-register)
# Add to ~/.claude/settings.json under enabledPlugins:
#   "netwatch@netwatch-local": true
# And under extraKnownMarketplaces:
#   "netwatch-local": { "source": { "source": "directory", "path": "/path/to/netwatch" } }

# Start daemon + verify everything
netwatch daemon start
netwatch doctor
```

## Quick start

```bash
# Launch HUD sidebar in a tmux pane
netwatch hud

# Pick an agent (interactive numbered list)
netwatch pick

# Spawn a new Claude instance in a fresh git worktree
netwatch spawn --branch feat/my-feature --prompt "implement the auth module"

# Broadcast a message to all running Claude agents
netwatch broadcast "pause and wait for review"

# Peek at what an agent is doing
netwatch peek %5

# Check health (9 checks: tmux, claude, python, config, daemon, socket, plugin, tmux.conf)
netwatch doctor
```

## tmux keybindings

After adding the snippet from `examples/tmux.conf.snippet`:

| Binding | Action |
|---|---|
| `C-a n` | Agent picker (replaces BLACKWALL) |
| `C-a k` | Peek at agent output (replaces KIROSHI) |
| `C-a s` | Broadcast to all agents (replaces SYNAPSE LINK) |
| `C-a S` | Spawn new agent in worktree (replaces NEW-CONSTRUCT) |
| `C-a N` | Launch HUD sidebar in current window |

Daemon auto-starts with tmux via `run-shell -b "netwatch daemon start --if-not-running"`.

## Architecture

```
                  ┌─────────────────────────────────┐
                  │ netwatchd (Python, long-lived)   │
                  │                                  │
  tmux control ──►│  tmux_watcher (libtmux)          │
  mode events     │  jsonl_watcher (watchdog/fsevents)│──► unix socket ──► HUD / CLI / pick
  Claude Code  ──►│  hook_receiver (aiohttp)          │                    subscribers
  plugin hooks    │  aggregator (pydantic state)      │
                  └─────────────────────────────────┘
```

Single daemon aggregates state from three sources; thin clients subscribe over a unix socket.

## Claude Code Plugin

netwatch ships as a Claude Code plugin (`.claude-plugin/plugin.json`). When enabled, it declares hooks for `SessionStart`, `Stop`, `PreToolUse`, and `PostToolUse` that forward events to the local daemon. No manual `curl` entries in settings.json required.

```
.claude-plugin/plugin.json  ← plugin manifest
hooks/hooks.json            ← hook declarations (4 events)
bin/netwatch-hook.sh        ← thin bridge: reads stdin, POSTs to daemon
```

## Configuration

`~/.config/netwatch/config.toml` — created by `netwatch install` or manually.

```toml
[daemon]
port = 0          # 0 = random port (written to ~/.config/netwatch/port)

[theme]
name = "netrunner" # or "default"

[hud]
width = 32
position = "left"
```

## Commands

| Command | Purpose |
|---|---|
| `netwatch install` | Interactive setup wizard |
| `netwatch uninstall` | Clean revert of all changes |
| `netwatch doctor` | 9-point health check with fix suggestions |
| `netwatch daemon start\|stop\|restart\|status\|logs` | Daemon lifecycle |
| `netwatch hud` | Launch Textual HUD sidebar |
| `netwatch pick` | Interactive agent picker |
| `netwatch peek <pane>` | Show last N lines of pane output |
| `netwatch jump <pane>` | Switch tmux focus |
| `netwatch broadcast <msg>` | Send to all agent panes |
| `netwatch spawn --branch X` | New worktree + window + agent |
| `netwatch status [--json\|--bar]` | Agent state (or compact for tmux status bar) |
| `netwatch tail` | Live ndjson event stream |

## Development

```bash
git clone https://github.com/e01n0/netwatch.git
cd netwatch
uv sync --dev
uv run pytest -v          # 25 tests
uv run ruff check src/    # lint
```

## License

MIT

## Credits

Built by [Eoin O'Flanagan](https://github.com/e01n0) with Claude Code.
