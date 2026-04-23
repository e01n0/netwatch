# netwatch

> *Cyberpunk-themed tmux agent dashboard for Claude Code and friends.*

A persistent sidebar and CLI toolkit for monitoring, navigating, and controlling multiple AI coding agents running across tmux panes and git worktrees.

**Replaces `ps`-scanning and bash scripts with proper APIs:** Claude Code hooks, JSONL session transcripts, and tmux control mode.

## Features

- **Persistent HUD sidebar** — left-pane Textual TUI showing every pane, agent state, and working directory. Click a row to jump.
- **Real agent state** — reads Claude Code JSONL transcripts for ground-truth status (thinking / tool-use / waiting / error), not `ps aux` guessing.
- **Push, don't poll** — Claude Code hooks push state changes to a local daemon. tmux control mode delivers pane events. No 2-second polling loops.
- **12 CLI commands** — `install`, `uninstall`, `doctor`, `pick`, `peek`, `jump`, `broadcast`, `spawn`, `status`, `tail`, `hud`, `daemon`.
- **Cyberpunk Netrunner theme** — cyan/green HUD aesthetic with Nerd Font glyphs. Configurable via TOML.
- **User-friendly** — interactive install wizard, manifest-tracked uninstall, actionable `doctor` diagnostics.

## Requirements

- Python 3.12+
- tmux 3.0+
- Claude Code CLI (for agent monitoring)
- A Nerd Font (for glyphs — optional, degrades gracefully)

## Install

```bash
# Clone and install with uv
git clone https://github.com/e01n0/netwatch.git
cd netwatch
uv sync

# Interactive setup — writes tmux config, registers Claude hooks, starts daemon
uv run netwatch install
```

## Quick start

```bash
# Attach HUD to all windows in current tmux session
uv run netwatch hud           # in a pane — becomes the sidebar
# Or via tmux keybind (after install):
# C-a C-n   attach to all windows
# C-a N     attach to current window
# C-a M-n   detach all

# Pick an agent (fzf-like)
uv run netwatch pick

# Spawn a new Claude instance in a fresh worktree
uv run netwatch spawn --branch feat/my-feature --prompt "implement the auth module"

# Broadcast a message to all running Claude agents
uv run netwatch broadcast "pause and wait for review"

# Check health
uv run netwatch doctor
```

## Architecture

```
netwatchd (daemon)          CLI / HUD clients
  tmux control-mode ──┐
  Claude Code hooks ──┼──► state ──► unix socket ──► subscribers
  JSONL transcripts ──┘
```

Single daemon aggregates state from three sources; thin clients subscribe over a unix socket.

## Configuration

`~/.config/netwatch/config.toml` — created by `netwatch install`.

```toml
[daemon]
port = 7345

[theme]
name = "netrunner"     # or "default"

[hud]
width = 32
position = "left"
refresh_ms = 500
```

## Commands

| Command | Purpose |
|---|---|
| `netwatch install` | Interactive setup wizard |
| `netwatch uninstall` | Clean revert of all changes |
| `netwatch doctor` | Health check with fix suggestions |
| `netwatch daemon start\|stop\|restart\|status\|logs` | Daemon lifecycle |
| `netwatch hud` | Launch Textual sidebar |
| `netwatch pick` | Interactive agent picker |
| `netwatch peek <pane>` | Show last N lines of pane output |
| `netwatch jump <pane>` | Switch tmux focus |
| `netwatch broadcast <msg>` | Send to all agent panes |
| `netwatch spawn` | New worktree + window + agent |
| `netwatch status [--json]` | Machine-readable state |
| `netwatch tail` | Live event stream |

## License

MIT

## Credits

Built by [Eoin O'Flanagan](https://github.com/e01n0) with Claude Code.
