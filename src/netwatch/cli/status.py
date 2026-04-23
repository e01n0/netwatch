"""Status — show current agent state across all panes."""

from __future__ import annotations

import json

import typer

from netwatch.common.socket_client import get_state_sync


def run_status(json_output: bool = False, bar: bool = False) -> None:
    """Connect to daemon socket, get state, and print."""
    try:
        state = get_state_sync()
    except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
        if bar:
            typer.echo("?")
            return
        typer.echo(f"Error: cannot reach daemon — {exc}", err=True)
        raise typer.Exit(code=1) from exc

    panes = state.get("data", {}).get("panes", {})
    agents = [p for p in panes.values() if p.get("is_agent")]
    active = sum(1 for a in agents if a.get("agent_status") in ("thinking", "tool-use"))
    idle = len(agents) - active

    if bar:
        typer.echo(f"\U000f06a9 {len(agents)} [{active}⚡{idle}◆]")
        return

    if json_output:
        typer.echo(json.dumps(state, indent=2, default=str))
        return

    if not panes:
        typer.echo("No panes tracked yet.")
        return

    for pane_id, info in panes.items():
        agent_flag = " [agent]" if info.get("is_agent") else ""
        status = info.get("agent_status", "")
        typer.echo(
            f"  {pane_id}  {info.get('window_name', '?'):20s}  {status:12s}{agent_flag}"
        )
