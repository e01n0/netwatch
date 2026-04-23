"""Install wizard — writes tmux config, registers hooks, starts daemon."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

import typer

from netwatch.common.paths import (
    claude_settings_file,
    config_dir,
    config_file,
    install_manifest,
    port_file,
)

_CYAN = typer.colors.CYAN
_GREEN = typer.colors.GREEN
_YELLOW = typer.colors.YELLOW
_RED = typer.colors.RED
_DIM = typer.colors.BRIGHT_BLACK

_BANNER = r"""
  ╔══════════════════════════════════════════╗
  ║   ░█▀█░█▀▀░▀█▀░█░█░█▀█░▀█▀░█▀▀░█░█░   ║
  ║   ░█░█░█▀▀░░█░░█▄█░█▀█░░█░░█░░░█▀█░   ║
  ║   ░▀░▀░▀▀▀░░▀░░▀░▀░▀░▀░░▀░░▀▀▀░▀░▀░   ║
  ║                                          ║
  ║     tmux agent dashboard for claude      ║
  ╚══════════════════════════════════════════╝
"""

_TMUX_MARKER_START = "# ── netwatch ──"
_TMUX_MARKER_END = "# ── /netwatch ──"

_DEFAULT_CONFIG = """\
[daemon]
port = 0

[theme]
name = "netrunner"

[hud]
width = 32
position = "left"
"""

_HOOK_EVENTS = ["SessionStart", "Stop", "PreToolUse", "PostToolUse"]


def _styled(text: str, colour: str | None = None, bold: bool = False) -> str:
    return typer.style(text, fg=colour, bold=bold)


def _ok(msg: str) -> None:
    typer.echo(f"  {_styled('✓', _GREEN)} {msg}")


def _skip(msg: str) -> None:
    typer.echo(f"  {_styled('-', _DIM)} {msg}")


def _info(msg: str) -> None:
    typer.echo(f"  {_styled('→', _CYAN)} {msg}")


def _warn(msg: str) -> None:
    typer.echo(f"  {_styled('⚠', _YELLOW)} {msg}")


def _fail(msg: str) -> None:
    typer.echo(f"  {_styled('✗', _RED)} {msg}")


# ── prerequisite checks ────────────────────────────────────────


def _check_tmux() -> bool:
    """Verify tmux is on PATH and >= 3.0."""
    tmux = shutil.which("tmux")
    if not tmux:
        _fail("tmux not found on PATH — install via brew or your package manager")
        return False
    try:
        out = subprocess.check_output(["tmux", "-V"], text=True).strip()
        version_str = out.split()[-1]  # e.g. "tmux 3.4" → "3.4"
        major = int(version_str.split(".")[0])
        if major < 3:
            _fail(f"tmux {version_str} found — need >= 3.0 (run `brew upgrade tmux`)")
            return False
    except (subprocess.CalledProcessError, ValueError, IndexError):
        _warn("Could not parse tmux version — proceeding anyway")
        return True
    _ok(f"tmux {version_str}")
    return True


def _check_claude() -> bool:
    """Verify `claude` CLI is on PATH."""
    if shutil.which("claude"):
        _ok("claude CLI found")
        return True
    _fail("claude not found on PATH — install from https://claude.ai/download")
    return False


def _check_python() -> bool:
    """Verify Python >= 3.12."""
    v = sys.version_info
    if v >= (3, 12):
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    _fail(f"Python {v.major}.{v.minor} — need >= 3.12")
    return False


# ── config dir / file ──────────────────────────────────────────


def _ensure_config_dir(dry_run: bool) -> None:
    d = config_dir()
    if d.exists():
        _ok(f"Config dir exists: {d}")
        return
    if dry_run:
        _info(f"Would create {d}")
        return
    d.mkdir(parents=True, exist_ok=True)
    _ok(f"Created {d}")


def _ensure_config_file(dry_run: bool) -> None:
    cf = config_file()
    if cf.exists():
        _ok(f"Config file exists: {cf}")
        return
    if dry_run:
        _info(f"Would write default config to {cf}")
        return
    cf.write_text(_DEFAULT_CONFIG)
    _ok(f"Wrote default config to {cf}")


# ── tmux snippet ───────────────────────────────────────────────


def _load_tmux_snippet() -> str:
    """Load the tmux snippet from the examples dir bundled with the package."""
    try:
        ref = resources.files("netwatch").joinpath("../../examples/tmux.conf.snippet")
        # resources.files may not resolve correctly for editable installs,
        # so fall back to a path relative to the source tree.
        snippet_path = Path(ref) if Path(ref).exists() else None
    except (TypeError, FileNotFoundError):
        snippet_path = None

    if snippet_path is None:
        # Walk up from this file to the project root
        candidate = Path(__file__).resolve().parents[3] / "examples" / "tmux.conf.snippet"
        if candidate.exists():
            snippet_path = candidate

    if snippet_path and snippet_path.exists():
        return snippet_path.read_text()

    # Absolute last resort — minimal inline version
    return (
        '# Auto-start daemon when tmux server boots (idempotent)\n'
        'run-shell -b "netwatch daemon start --if-not-running"\n'
        '\n'
        '# Attach HUD sidebar to current window (prefix + N)\n'
        'bind-key N run-shell "tmux split-window -bh -l 32 \'netwatch hud\'"\n'
        '\n'
        '# Agent picker (prefix + n)\n'
        'bind-key n display-popup -E -w 90 -h 25 -T " 󰚩 NETWATCH PICK " "netwatch pick"\n'
    )


def _install_tmux_snippet(dry_run: bool, manifest: dict) -> None:
    tmux_conf = Path.home() / ".tmux.conf"
    snippet = _load_tmux_snippet()

    # Already installed?
    if tmux_conf.exists() and _TMUX_MARKER_START in tmux_conf.read_text():
        _ok("tmux.conf already contains netwatch snippet")
        manifest["tmux_conf"] = {"path": str(tmux_conf), "marker": _TMUX_MARKER_START}
        return

    typer.echo()
    typer.echo(_styled("  tmux snippet to add:", _CYAN, bold=True))
    for line in snippet.strip().splitlines():
        typer.echo(f"    {_styled(line, _DIM)}")
    typer.echo()

    if not typer.confirm("  Add this snippet to ~/.tmux.conf?", default=True):
        _skip("Skipped tmux.conf — you can paste it manually later")
        return

    if dry_run:
        _info(f"Would append snippet to {tmux_conf}")
        manifest["tmux_conf"] = {"path": str(tmux_conf), "marker": _TMUX_MARKER_START}
        return

    block = f"\n{_TMUX_MARKER_START}\n{snippet.strip()}\n{_TMUX_MARKER_END}\n"
    with tmux_conf.open("a") as fh:
        fh.write(block)
    _ok(f"Appended netwatch snippet to {tmux_conf}")
    manifest["tmux_conf"] = {"path": str(tmux_conf), "marker": _TMUX_MARKER_START}


# ── Claude hooks ───────────────────────────────────────────────


def _build_hook_entry(event: str) -> dict:
    """Build a single Claude Code hook entry that POSTs to the daemon."""
    return {
        "type": "command",
        "command": (
            f"curl -s -X POST http://localhost:$(cat {port_file()})"
            f'/hook/{event} -H "Content-Type: application/json" -d @-'
        ),
    }


def _install_claude_hooks(dry_run: bool, manifest: dict) -> None:
    settings_path = claude_settings_file()

    typer.echo()
    typer.echo(_styled("  Claude Code hooks:", _CYAN, bold=True))
    typer.echo(f"    Events: {', '.join(_HOOK_EVENTS)}")
    typer.echo(f"    Target: {settings_path}")
    typer.echo()

    if not typer.confirm("  Register Claude Code hooks?", default=True):
        _skip("Skipped hook registration")
        return

    # Read existing settings
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            _warn(f"Existing {settings_path} has invalid JSON — will overwrite hooks key")

    hooks: dict = settings.get("hooks", {})

    for event in _HOOK_EVENTS:
        entry = _build_hook_entry(event)
        existing_hooks: list = hooks.get(event, [])
        # Don't double-add — check if we already have a netwatch curl entry
        already = any(
            "netwatch" in str(h.get("command", ""))
            for h in existing_hooks
            if isinstance(h, dict)
        )
        if already:
            _ok(f"Hook already registered: {event}")
            continue
        existing_hooks.append(entry)
        hooks[event] = existing_hooks
        if dry_run:
            _info(f"Would register hook: {event}")
        else:
            _ok(f"Registered hook: {event}")

    settings["hooks"] = hooks

    if dry_run:
        _info(f"Would write {settings_path}")
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        _ok(f"Updated {settings_path}")

    manifest["claude_hooks"] = True


# ── main install flow ──────────────────────────────────────────


def run_install(dry_run: bool) -> None:
    """Interactive setup wizard."""
    # Banner
    for line in _BANNER.strip().splitlines():
        typer.echo(_styled(line, _CYAN, bold=True))
    typer.echo()

    if dry_run:
        typer.echo(_styled("  ▸ DRY RUN — nothing will be written\n", _YELLOW, bold=True))

    # Prerequisites
    typer.echo(_styled("  Checking prerequisites...\n", _CYAN, bold=True))
    prereqs_ok = all([_check_tmux(), _check_claude(), _check_python()])
    typer.echo()

    if not prereqs_ok:
        _warn("Some prerequisites are missing — install may be incomplete")
        typer.echo()

    # Config directory and file
    typer.echo(_styled("  Setting up config...\n", _CYAN, bold=True))
    _ensure_config_dir(dry_run)
    _ensure_config_file(dry_run)

    # Manifest tracks everything we touch for clean uninstall
    manifest: dict = {}

    # tmux snippet
    _install_tmux_snippet(dry_run, manifest)

    # Claude hooks
    _install_claude_hooks(dry_run, manifest)

    # Write manifest
    typer.echo()
    mf = install_manifest()
    if dry_run:
        _info(f"Would write manifest to {mf}")
    else:
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text(json.dumps(manifest, indent=2) + "\n")
        _ok(f"Manifest saved to {mf}")

    # Start daemon
    typer.echo()
    if dry_run:
        _info("Would start daemon via `netwatch daemon start`")
    else:
        typer.echo(_styled("  Starting daemon...\n", _CYAN, bold=True))
        result = subprocess.run(
            ["netwatch", "daemon", "start", "--if-not-running"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            _ok(result.stdout.strip() or "Daemon started")
        else:
            _warn(f"Daemon start returned code {result.returncode}: {result.stderr.strip()}")

    # Run doctor
    typer.echo()
    typer.echo(_styled("  Running health check...\n", _CYAN, bold=True))

    from netwatch.cli.doctor import run_doctor

    run_doctor()

    typer.echo()
    typer.echo(_styled("  ╔═══════════════════════════════════════╗", _CYAN))
    typer.echo(_styled("  ║  Installation complete. Jack in.      ║", _CYAN))
    typer.echo(_styled("  ╚═══════════════════════════════════════╝", _CYAN))
    typer.echo()
