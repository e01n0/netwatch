"""Peek — capture and display recent output from a tmux pane."""

from __future__ import annotations

import libtmux
import typer

_CAPTURE_LINES = 40


def run_peek(pane: str) -> None:
    """Show last N lines of a pane's output."""
    server = libtmux.Server()
    target = server.panes.filter(pane_id=pane)
    if not target:
        typer.echo(f"Error: pane {pane} not found", err=True)
        raise typer.Exit(code=1)
    lines: list[str] = target[0].capture_pane(start=-_CAPTURE_LINES)
    typer.echo("\n".join(lines))
