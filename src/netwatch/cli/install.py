"""Install wizard — writes tmux config, registers hooks, starts daemon."""

from __future__ import annotations

import typer


def run_install(dry_run: bool) -> None:
    """Interactive setup wizard."""
    typer.echo(f"TODO: run_install(dry_run={dry_run}) — not yet implemented")
