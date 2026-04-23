# netwatch

> *Cyberpunk-themed tmux agent dashboard for Claude Code and friends.*

A persistent sidebar and CLI toolkit for monitoring, navigating, and controlling multiple AI coding agents running across tmux panes and git worktrees.

**Replaces `ps`-scanning and bash scripts with proper APIs:** Claude Code hooks (via plugin), JSONL session transcripts, and tmux control mode via libtmux.

## Features

- **Persistent sidebar** — left-pane raw-ANSI HUD in every tmux window showing agent state, git branch, worktree status, and working directory. Double-click a row to jump.
- **Waiting alerts** — agents needing input are highlighted with `NEEDS INPUT` and a header summary.
- **Real agent state** — detects Claude by scanning process trees per TTY, reads JSONL transcripts for ground-truth status (thinking / tool-use / waiting / error).
- **Git-aware** — shows current branch per pane, tags worktrees with `[wt]`.
- **Claude Code plugin** — hooks declared in `plugin.json`, auto-registered when enabled. No manual settings.json edits.
- **12 CLI commands** — `install`, `uninstall`, `doctor`, `pick`, `peek`, `jump`, `broadcast`, `spawn`, `status`, `tail`, `hud`, `daemon`.
- **Cyberpunk Netrunner theme** — cyan/green/yellow colour palette.
- **User-friendly** — interactive install wizard, manifest-tracked uninstall, 9-point `doctor` health check.

## Requirements

- Python 3.12+
- tmux 3.0+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Claude Code CLI (for agent monitoring features)

## Install guide

### Step 1: Clone and install the CLI

```bash
git clone https://github.com/e01n0/netwatch.git ~/git/netwatch
cd ~/git/netwatch
uv tool install .
```

This installs four binaries to `~/.local/bin/`:
- `netwatch` — CLI (12 subcommands)
- `netwatchd` — background daemon
- `netwatch-sidebar` — persistent tmux sidebar
- `netwatch-hud` — Textual TUI (standalone mode)

Verify: `netwatch --version`

### Step 2: Make the hook script executable

```bash
chmod +x ~/git/netwatch/bin/netwatch-hook.sh
```

### Step 3: Register the Claude Code plugin

Add the following to `~/.claude/settings.json`:

```jsonc
{
  // Under "enabledPlugins":
  "netwatch@netwatch-local": true,

  // Under "extraKnownMarketplaces":
  "netwatch-local": {
    "source": {
      "source": "directory",
      "path": "/path/to/netwatch"  // <-- your clone path
    }
  }
}
```

This registers four hooks (`SessionStart`, `Stop`, `PreToolUse`, `PostToolUse`) that push agent state changes to the daemon. No manual curl entries needed.

### Step 4: Create the config file

```bash
mkdir -p ~/.config/netwatch
cat > ~/.config/netwatch/config.toml << 'EOF'
[daemon]
port = 0

[theme]
name = "netrunner"

[hud]
width = 32
position = "left"
EOF
```

### Step 5: Add tmux integration

Append the contents of `examples/tmux.conf.snippet` to your `~/.tmux.conf`, or paste this minimal version:

```tmux
# ── netwatch ──
# Daemon auto-start (idempotent)
run-shell -b "netwatch daemon start --if-not-running"

# Persistent sidebar — auto-attach to every window
set-hook -g after-new-window 'run-shell -b "sleep 0.3 && tmux split-window -bh -l 32 netwatch-sidebar"'

# Manual controls
bind-key N run-shell "tmux split-window -bh -l 32 'netwatch-sidebar'"
bind-key M-n run-shell "tmux list-panes -s -F '#{pane_id} #{pane_current_command}' | awk '/netwatch-sidebar/{print \\$1}' | xargs -I{} tmux kill-pane -t {}"

# Agent picker + tools
bind-key n display-popup -E -w 90 -h 25 -T " NETWATCH PICK " "netwatch pick"
bind-key k display-popup -E -w 110 -h 35 -T " PEEK " "netwatch peek"
bind-key s display-popup -E -w 80 -h 20 -T " BROADCAST " "netwatch broadcast"
bind-key S display-popup -E -w 90 -h 22 -T " SPAWN " "netwatch spawn"

# Double-click sidebar row to jump
bind-key -n DoubleClick1Pane if-shell -F -t = "#{==:#{pane_title},NETWATCH}" \
    "run-shell 'bash ~/git/netwatch/bin/netwatch-sidebar-click.sh #{mouse_y}'" \
    "select-pane -t ="
# ── /netwatch ──
```

Then reload: `tmux source-file ~/.tmux.conf`

### Step 6: Start and verify

```bash
netwatch daemon start
netwatch doctor
```

All 9 checks should pass. Then `C-a N` to open the sidebar.

### Updating

```bash
cd ~/git/netwatch
git pull
uv tool install --force .
netwatch daemon restart
```

### Uninstalling

```bash
netwatch uninstall     # removes config, hooks, tmux snippet
uv tool uninstall netwatch
rm -rf ~/git/netwatch
```

## Quick reference

### tmux keybindings

| Binding | Action |
|---|---|
| `C-a N` | Open sidebar in current window |
| `C-a M-n` | Close all sidebars |
| `C-a n` | Agent picker |
| `C-a k` | Peek at agent output |
| `C-a s` | Broadcast to all agents |
| `C-a S` | Spawn new agent in worktree |
| Double-click | Jump to pane (in sidebar) |

New windows auto-get a sidebar via the `after-new-window` hook.

### Sidebar display

```
 NETWATCH
───────────────────────────────
 ⚡ 1 active: Bash

 ━━ brickify
  1│⚡ claude  git/brickify
      estate-refactor [wt]
  2│  zsh     git/brickify
      main

 ━━ netwatch
  3│◆ claude  git/netwatch
      main
      ⏳ NEEDS INPUT

───────────────────────────────
 1⚡ 1⏳ │ 3 panes
```

- `⚡` active (thinking/tool-use) · `◆` idle · `⏳` waiting for input · `✗` error
- Git branch shown per pane, `[wt]` for worktrees
- Header alerts for agents needing attention

### CLI commands

| Command | Purpose |
|---|---|
| `netwatch install` | Interactive setup wizard |
| `netwatch uninstall` | Clean revert of all changes |
| `netwatch doctor` | 9-point health check |
| `netwatch daemon start\|stop\|restart\|status\|logs` | Daemon lifecycle |
| `netwatch pick` | Interactive agent picker |
| `netwatch peek <pane>` | Last N lines of pane output |
| `netwatch jump <pane>` | Switch tmux focus |
| `netwatch broadcast <msg>` | Send to all agent panes |
| `netwatch spawn --branch X [--prompt Y]` | New worktree + window + agent |
| `netwatch status [--json\|--bar]` | Agent state (or compact for tmux status bar) |
| `netwatch tail` | Live ndjson event stream |

## Architecture

```
                  ┌─────────────────────────────────┐
                  │ netwatchd (Python, long-lived)   │
                  │                                  │
  tmux panes   ──│  tmux_watcher (libtmux + ps)     │
  (libtmux)      │  jsonl_watcher (watchdog/fsevents)│──► unix socket ──► sidebar
  Claude Code  ──│  hook_receiver (aiohttp)          │                    CLI
  plugin hooks    │  aggregator (pydantic state)      │                    pick/peek
                  └─────────────────────────────────┘
```

Single daemon, three input sources, thin clients over a unix socket.

## Configuration

`~/.config/netwatch/config.toml`:

```toml
[daemon]
port = 0          # 0 = random (written to ~/.config/netwatch/port)

[theme]
name = "netrunner" # or "default"

[hud]
width = 32
position = "left"
```

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

Built by [Eoin O'Flanagan](https://github.com/e01n0).
