"""Daemon control — start / stop / restart / status / logs."""

from __future__ import annotations

import os
import signal
import subprocess
import sys

import typer

from netwatch.common.paths import log_file, pid_file


def _read_pid() -> int | None:
    """Read the daemon PID from the pidfile, or None if missing/stale."""
    pf = pid_file()
    if not pf.exists():
        return None
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, 0)  # existence check
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        pf.unlink(missing_ok=True)
        return None


def start(if_not_running: bool) -> None:
    """Start the netwatchd daemon as a detached subprocess."""
    existing = _read_pid()
    if existing is not None:
        if if_not_running:
            typer.echo(f"Daemon already running (pid {existing})")
            return
        typer.echo(f"Daemon already running (pid {existing}). Use 'restart' instead.", err=True)
        raise typer.Exit(code=1)

    pf = pid_file()
    pf.parent.mkdir(parents=True, exist_ok=True)

    lf = log_file()
    lf.parent.mkdir(parents=True, exist_ok=True)

    with lf.open("a") as log_fh:
        proc = subprocess.Popen(
            [sys.executable, "-m", "netwatch.daemon"],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    pf.write_text(str(proc.pid))
    typer.echo(f"Daemon started (pid {proc.pid})")


def stop() -> None:
    """Read pidfile and send SIGTERM."""
    pid = _read_pid()
    if pid is None:
        typer.echo("Daemon is not running.")
        return
    os.kill(pid, signal.SIGTERM)
    pid_file().unlink(missing_ok=True)
    typer.echo(f"Daemon stopped (pid {pid})")


def restart() -> None:
    """Stop then start."""
    stop()
    start(if_not_running=False)


def daemon_status_cmd() -> None:
    """Print whether the daemon is alive."""
    pid = _read_pid()
    if pid is None:
        typer.echo("Daemon is not running.")
        raise typer.Exit(code=1)
    typer.echo(f"Daemon running (pid {pid})")


def logs(follow: bool) -> None:
    """Tail the daemon log file."""
    lf = log_file()
    if not lf.exists():
        typer.echo("No log file found yet.", err=True)
        raise typer.Exit(code=1)
    cmd = ["tail"]
    if follow:
        cmd.append("-f")
    cmd.append(str(lf))
    os.execvp("tail", cmd)
