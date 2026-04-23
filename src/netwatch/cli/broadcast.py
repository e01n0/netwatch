"""Broadcast -- send text to all running agent panes."""

from __future__ import annotations

import libtmux
import typer

from netwatch.common.socket_client import get_state_sync


def run_broadcast(message: str) -> None:
    """Send text to all agent panes."""
    try:
        state = get_state_sync()
    except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
        typer.echo(
            typer.style("Error: daemon not running", fg=typer.colors.RED) + f" -- {exc}",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    panes: dict[str, dict] = state.get("data", {}).get("panes", {})
    agent_panes = {pid: info for pid, info in panes.items() if info.get("is_agent")}

    if not agent_panes:
        typer.echo("No agent panes found. Nothing to broadcast.")
        return

    server = libtmux.Server()
    sent = 0
    for pane_id in agent_panes:
        targets = server.panes.filter(pane_id=pane_id)
        if not targets:
            typer.echo(
                typer.style(f"  skip {pane_id}", dim=True) + " -- pane gone",
            )
            continue
        targets[0].send_keys(message + "\n", suppress_history=False)
        name = agent_panes[pane_id].get("window_name", "?")
        typer.echo("  sent -> " + typer.style(pane_id, fg=typer.colors.CYAN) + f"  ({name})")
        sent += 1

    colour = typer.colors.GREEN if sent else typer.colors.YELLOW
    typer.echo(typer.style(f"Broadcast to {sent} agent pane(s).", fg=colour))
