"""Jump — switch tmux focus to a specific pane."""

from __future__ import annotations

import libtmux
import typer


def run_jump(pane: str) -> None:
    """Select and focus a tmux pane by ID."""
    server = libtmux.Server()
    target = server.panes.filter(pane_id=pane)
    if not target:
        typer.echo(f"Error: pane {pane} not found", err=True)
        raise typer.Exit(code=1)
    target[0].select_pane()
    window = target[0].window
    if window:
        window.select_window()
    typer.echo(f"Jumped to pane {pane}")
