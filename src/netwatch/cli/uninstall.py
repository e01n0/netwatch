"""Uninstall — revert all changes made by `netwatch install`."""

from __future__ import annotations

import typer


def run_uninstall(force: bool) -> None:
    """Cleanly revert install artefacts."""
    typer.echo(f"TODO: run_uninstall(force={force}) — not yet implemented")
