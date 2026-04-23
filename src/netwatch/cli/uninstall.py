"""Uninstall — revert all changes made by `netwatch install`."""

from __future__ import annotations

import json
import os
import shutil
import signal

import typer

from netwatch.common.paths import (
    claude_settings_file,
    config_dir,
    install_manifest,
    pid_file,
    socket_path,
)

_CYAN = typer.colors.CYAN
_GREEN = typer.colors.GREEN
_YELLOW = typer.colors.YELLOW
_RED = typer.colors.RED
_DIM = typer.colors.BRIGHT_BLACK

_TMUX_MARKER_START = "# ── netwatch ──"
_TMUX_MARKER_END = "# ── /netwatch ──"


def _ok(msg: str) -> None:
    typer.echo(f"  {typer.style('✓', fg=_GREEN)} {msg}")


def _skip(msg: str) -> None:
    typer.echo(f"  {typer.style('-', fg=_DIM)} {msg}")


def _warn(msg: str) -> None:
    typer.echo(f"  {typer.style('⚠', fg=_YELLOW)} {msg}")


# ── removal helpers ────────────────────────────────────────────


def _remove_tmux_snippet(manifest: dict) -> None:
    """Remove the netwatch block from ~/.tmux.conf between markers."""
    info = manifest.get("tmux_conf")
    if not info:
        _skip("No tmux.conf entry in manifest — skipping")
        return

    from pathlib import Path

    tmux_conf = Path(info.get("path", Path.home() / ".tmux.conf")).expanduser()
    if not tmux_conf.exists():
        _skip(f"{tmux_conf} not found — nothing to remove")
        return

    original = tmux_conf.read_text()
    if _TMUX_MARKER_START not in original:
        _skip("No netwatch snippet found in tmux.conf")
        return

    lines = original.splitlines(keepends=True)
    cleaned: list[str] = []
    inside_block = False

    for line in lines:
        if _TMUX_MARKER_START in line:
            inside_block = True
            continue
        if _TMUX_MARKER_END in line:
            inside_block = False
            continue
        if not inside_block:
            cleaned.append(line)

    # Strip trailing blank lines left over from the removed block
    text = "".join(cleaned).rstrip("\n")
    if text:
        text += "\n"
    tmux_conf.write_text(text)
    _ok(f"Removed netwatch snippet from {tmux_conf}")


def _remove_claude_hooks(manifest: dict) -> None:
    """Remove netwatch hook entries from Claude settings.json."""
    if not manifest.get("claude_hooks"):
        _skip("No Claude hooks in manifest — skipping")
        return

    sf = claude_settings_file()
    if not sf.exists():
        _skip(f"{sf} not found — nothing to remove")
        return

    try:
        settings = json.loads(sf.read_text())
    except json.JSONDecodeError:
        _warn(f"Could not parse {sf} — leaving hooks in place")
        return

    hooks: dict = settings.get("hooks", {})
    modified = False

    for event in list(hooks.keys()):
        entries = hooks[event]
        filtered = [
            e for e in entries
            if not (isinstance(e, dict) and "netwatch" in str(e.get("command", "")))
        ]
        if len(filtered) < len(entries):
            modified = True
        if filtered:
            hooks[event] = filtered
        else:
            del hooks[event]

    if not hooks:
        settings.pop("hooks", None)

    if modified:
        sf.write_text(json.dumps(settings, indent=2) + "\n")
        _ok(f"Removed netwatch hooks from {sf}")
    else:
        _skip("No netwatch hooks found in Claude settings")


def _stop_daemon() -> None:
    """Stop the daemon if it's running."""
    pf = pid_file()
    if not pf.exists():
        _skip("Daemon not running (no pidfile)")
        return
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        _ok(f"Stopped daemon (pid {pid})")
    except (ValueError, ProcessLookupError, PermissionError):
        _skip("Daemon pidfile exists but process already gone")
    pf.unlink(missing_ok=True)


def _remove_runtime_files() -> None:
    """Remove socket and pid files."""
    sp = socket_path()
    if sp.exists():
        sp.unlink(missing_ok=True)
        _ok(f"Removed socket: {sp}")

    pf = pid_file()
    if pf.exists():
        pf.unlink(missing_ok=True)
        _ok(f"Removed pidfile: {pf}")

    # Clean up the runtime dir if empty
    runtime_dir = sp.parent
    if runtime_dir.exists() and not any(runtime_dir.iterdir()):
        runtime_dir.rmdir()


def _remove_config_dir() -> None:
    """Remove ~/.config/netwatch/ entirely."""
    d = config_dir()
    if not d.exists():
        _skip("Config dir already gone")
        return
    shutil.rmtree(d)
    _ok(f"Removed {d}")


# ── main ───────────────────────────────────────────────────────


def run_uninstall(force: bool) -> None:
    """Cleanly revert install artefacts."""
    typer.echo()
    typer.echo(typer.style("  NETWATCH UNINSTALL", fg=_CYAN, bold=True))
    typer.echo(typer.style("  ──────────────────", fg=_CYAN))
    typer.echo()

    # Read manifest
    mf = install_manifest()
    if not mf.exists():
        typer.echo(typer.style("  Nothing to uninstall — no install manifest found.", fg=_DIM))
        typer.echo(typer.style(f"  (looked for {mf})", fg=_DIM))
        typer.echo()
        return

    try:
        manifest = json.loads(mf.read_text())
    except json.JSONDecodeError:
        _warn(f"Manifest at {mf} is corrupted — will attempt full cleanup anyway")
        manifest = {}

    # Show what will be removed
    typer.echo("  Will remove:")
    if manifest.get("tmux_conf"):
        typer.echo("    • netwatch snippet from ~/.tmux.conf")
    if manifest.get("claude_hooks"):
        typer.echo(f"    • Claude Code hook entries from {claude_settings_file()}")
    typer.echo("    • Daemon process (if running)")
    typer.echo(f"    • Config directory: {config_dir()}")
    typer.echo("    • Runtime files (socket, pidfile)")
    typer.echo()

    if not force and not typer.confirm("  Proceed with uninstall?", default=False):
        typer.echo()
        typer.echo(typer.style("  Aborted — nothing changed.", fg=_DIM))
        return

    typer.echo()

    # 1. tmux.conf snippet
    _remove_tmux_snippet(manifest)

    # 2. Claude hooks
    _remove_claude_hooks(manifest)

    # 3. Stop daemon
    _stop_daemon()

    # 4. Runtime files (socket, pid)
    _remove_runtime_files()

    # 5. Config dir (includes manifest itself)
    _remove_config_dir()

    typer.echo()
    typer.echo(typer.style("  ╔═══════════════════════════════════════════════════╗", _CYAN))
    typer.echo(typer.style("  ║  netwatch uninstalled. Farewell, choom.          ║", _CYAN))
    typer.echo(typer.style("  ╚═══════════════════════════════════════════════════╝", _CYAN))
    typer.echo()
