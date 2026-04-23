"""Health check — verify tmux, daemon, hooks, and socket."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable

import typer

from netwatch.common.paths import (
    claude_settings_file,
    config_dir,
    config_file,
    pid_file,
    socket_path,
)

_GREEN = typer.colors.GREEN
_RED = typer.colors.RED
_YELLOW = typer.colors.YELLOW
_CYAN = typer.colors.CYAN
_DIM = typer.colors.BRIGHT_BLACK

_TMUX_MARKER = "# ── netwatch ──"


def _pass(msg: str) -> None:
    typer.echo(f"  {typer.style('✓', fg=_GREEN)} {msg}")


def _fail(msg: str, hint: str = "") -> None:
    typer.echo(f"  {typer.style('✗', fg=_RED)} {msg}")
    if hint:
        typer.echo(f"    {typer.style(hint, fg=_DIM)}")


def _warn(msg: str, hint: str = "") -> None:
    typer.echo(f"  {typer.style('⚠', fg=_YELLOW)} {msg}")
    if hint:
        typer.echo(f"    {typer.style(hint, fg=_DIM)}")


# ── individual checks ──────────────────────────────────────────


def _check_tmux() -> bool:
    """tmux installed and version >= 3.0."""
    tmux = shutil.which("tmux")
    if not tmux:
        _fail("tmux not found on PATH", "brew install tmux")
        return False
    try:
        out = subprocess.check_output(["tmux", "-V"], text=True).strip()
        version_str = out.split()[-1]
        major = int(version_str.split(".")[0])
        if major < 3:
            _fail(f"tmux {version_str} — need >= 3.0", "brew upgrade tmux")
            return False
        _pass(f"tmux {version_str}")
        return True
    except (subprocess.CalledProcessError, ValueError, IndexError):
        _warn("tmux found but version could not be parsed")
        return True


def _check_claude() -> bool:
    """claude CLI found on PATH."""
    if shutil.which("claude"):
        _pass("claude CLI found")
        return True
    _fail("claude not found on PATH", "https://claude.ai/download")
    return False


def _check_python() -> bool:
    """Python >= 3.12."""
    v = sys.version_info
    if v >= (3, 12):
        _pass(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    _fail(f"Python {v.major}.{v.minor} — need >= 3.12", "pyenv install 3.12")
    return False


def _check_config_dir() -> bool:
    """Config dir exists."""
    d = config_dir()
    if d.is_dir():
        _pass(f"Config dir: {d}")
        return True
    _fail(f"Config dir missing: {d}", "run `netwatch install`")
    return False


def _check_config_file() -> bool:
    """Config file exists and is valid TOML."""
    cf = config_file()
    if not cf.exists():
        _fail(f"Config file missing: {cf}", "run `netwatch install`")
        return False
    try:
        import tomllib

        with cf.open("rb") as fh:
            tomllib.load(fh)
        _pass(f"Config file valid: {cf}")
        return True
    except Exception as exc:
        _fail(f"Config file invalid: {exc}", "check {cf} for syntax errors")
        return False


def _check_daemon() -> bool:
    """Daemon is running (pidfile exists, PID alive)."""
    pf = pid_file()
    if not pf.exists():
        _fail("Daemon not running — no pidfile", "run `netwatch daemon start`")
        return False
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, 0)
        _pass(f"Daemon running (pid {pid})")
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        _fail("Daemon pidfile exists but process is dead", "run `netwatch daemon restart`")
        pf.unlink(missing_ok=True)
        return False


def _check_socket() -> bool:
    """Socket exists and is connectable."""
    sp = socket_path()
    if not sp.exists():
        _fail(f"Socket missing: {sp}", "run `netwatch daemon restart`")
        return False

    async def _try_connect() -> bool:
        try:
            _reader, writer = await asyncio.open_unix_connection(str(sp))
            writer.close()
            await writer.wait_closed()
            return True
        except (ConnectionRefusedError, OSError):
            return False

    if asyncio.run(_try_connect()):
        _pass(f"Socket connectable: {sp}")
        return True
    _fail(f"Socket exists but connection refused: {sp}", "run `netwatch daemon restart`")
    return False


def _check_claude_hooks() -> bool:
    """netwatch plugin enabled (hooks are declared in the plugin manifest)."""
    sf = claude_settings_file()
    if not sf.exists():
        _fail(f"Claude settings missing: {sf}", "enable the netwatch plugin")
        return False
    try:
        settings = json.loads(sf.read_text())
    except json.JSONDecodeError:
        _fail(f"Claude settings invalid JSON: {sf}", "check file syntax")
        return False

    plugins = settings.get("enabledPlugins", {})
    # Check for any key containing "netwatch" that's enabled
    enabled = any(v is True for k, v in plugins.items() if "netwatch" in k.lower())
    if enabled:
        _pass("netwatch plugin enabled (hooks via plugin manifest)")
        return True
    _fail(
        "netwatch plugin not enabled",
        "add netwatch to enabledPlugins in settings.json or register as a local marketplace",
    )
    return False


def _check_tmux_conf() -> bool:
    """tmux.conf has netwatch snippet."""
    tmux_conf = __import__("pathlib").Path.home() / ".tmux.conf"
    if not tmux_conf.exists():
        _fail("~/.tmux.conf not found", "run `netwatch install`")
        return False
    if _TMUX_MARKER in tmux_conf.read_text():
        _pass("tmux.conf contains netwatch snippet")
        return True
    _fail("tmux.conf missing netwatch snippet", "run `netwatch install`")
    return False


# ── main ───────────────────────────────────────────────────────

_CHECKS: list[tuple[str, Callable[[], bool]]] = [
    ("tmux", _check_tmux),
    ("claude CLI", _check_claude),
    ("Python version", _check_python),
    ("config directory", _check_config_dir),
    ("config file", _check_config_file),
    ("daemon", _check_daemon),
    ("socket", _check_socket),
    ("Claude hooks", _check_claude_hooks),
    ("tmux.conf snippet", _check_tmux_conf),
]


def run_doctor() -> None:
    """Run diagnostic checks."""
    typer.echo()
    typer.echo(typer.style("  NETWATCH DIAGNOSTICS", fg=_CYAN, bold=True))
    typer.echo(typer.style("  ─────────────────────", fg=_CYAN))
    typer.echo()

    passed = 0
    total = len(_CHECKS)

    for _name, check_fn in _CHECKS:
        try:
            if check_fn():
                passed += 1
        except Exception as exc:
            _fail(f"{_name}: unexpected error — {exc}")

    typer.echo()
    colour = _GREEN if passed == total else _YELLOW if passed >= total - 2 else _RED
    typer.echo(typer.style(f"  {passed}/{total} checks passed", fg=colour, bold=True))
    typer.echo()

    if passed < total:
        raise typer.Exit(code=1)
