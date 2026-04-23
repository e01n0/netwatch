"""Pick -- interactive agent picker."""

from __future__ import annotations

import libtmux
import typer

from netwatch.common.socket_client import get_state_sync


def run_pick() -> None:
    """Launch interactive agent picker."""
    try:
        state = get_state_sync()
    except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
        typer.echo(
            typer.style("Error: daemon not running", fg=typer.colors.RED) + f" -- {exc}",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    panes: dict[str, dict] = state.get("data", {}).get("panes", {})
    if not panes:
        typer.echo("No panes tracked. Is the daemon scanning?")
        return

    # --- build numbered list ---
    entries: list[tuple[str, dict]] = sorted(
        panes.items(),
        key=lambda kv: (not kv[1].get("is_agent"), kv[1].get("window_name", "")),
    )

    typer.echo("")
    for idx, (pane_id, info) in enumerate(entries, start=1):
        is_agent = info.get("is_agent", False)
        status = info.get("agent_status", "")
        window = info.get("window_name", "?")
        cwd = info.get("cwd", "")

        if is_agent:
            tag = typer.style("[agent]", fg=typer.colors.GREEN)
            status_str = typer.style(status, fg=typer.colors.GREEN)
        else:
            tag = typer.style("[shell]", dim=True)
            status_str = typer.style(info.get("command", ""), dim=True)

        pid_styled = typer.style(pane_id, fg=typer.colors.CYAN)
        typer.echo(f"  {idx:>3}  {pid_styled}  {window:20s}  {tag} {status_str}  {cwd}")

    typer.echo("")

    # --- prompt for selection ---
    try:
        choice = typer.prompt("Pick a pane number", type=int)
    except typer.Abort:
        return

    if choice < 1 or choice > len(entries):
        typer.echo(typer.style("Invalid selection.", fg=typer.colors.RED), err=True)
        raise typer.Exit(code=1)

    target_id = entries[choice - 1][0]

    # --- jump via libtmux ---
    server = libtmux.Server()
    targets = server.panes.filter(pane_id=target_id)
    if not targets:
        typer.echo(
            typer.style("Error:", fg=typer.colors.RED) + f" pane {target_id} no longer exists.",
            err=True,
        )
        raise typer.Exit(code=1)

    targets[0].select_pane()
    window = targets[0].window
    if window:
        window.select_window()

    name = entries[choice - 1][1].get("window_name", "?")
    typer.echo("Jumped to " + typer.style(target_id, fg=typer.colors.CYAN) + f" ({name})")
