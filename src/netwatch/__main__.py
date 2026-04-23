"""CLI entrypoint — `netwatch <command>`."""

import typer

from netwatch import __version__

app = typer.Typer(
    name="netwatch",
    help="Cyberpunk-themed tmux agent dashboard for Claude Code and friends.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"netwatch {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, is_eager=True
    ),
) -> None:
    pass


@app.command()
def install(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without writing"),
) -> None:
    """Interactive setup wizard — writes tmux config, registers Claude hooks, starts daemon."""
    from netwatch.cli.install import run_install

    run_install(dry_run=dry_run)


@app.command()
def uninstall(force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation")) -> None:
    """Cleanly revert all changes made by `netwatch install`."""
    from netwatch.cli.uninstall import run_uninstall

    run_uninstall(force=force)


@app.command()
def doctor() -> None:
    """Health check — verify tmux, daemon, hooks, and socket are working."""
    from netwatch.cli.doctor import run_doctor

    run_doctor()


@app.command()
def hud() -> None:
    """Launch the Textual HUD sidebar in the current pane."""
    from netwatch.hud.__main__ import main as hud_main

    hud_main()


@app.command()
def pick() -> None:
    """Interactive agent picker (fzf-like)."""
    from netwatch.cli.pick import run_pick

    run_pick()


@app.command()
def peek(pane: str = typer.Argument(help="Pane ID (e.g. %5)")) -> None:
    """Show last N lines of a pane's output."""
    from netwatch.cli.peek import run_peek

    run_peek(pane)


@app.command()
def jump(pane: str = typer.Argument(help="Pane ID (e.g. %5)")) -> None:
    """Switch tmux focus to a specific pane."""
    from netwatch.cli.jump import run_jump

    run_jump(pane)


@app.command()
def broadcast(message: str = typer.Argument(help="Text to send to all agent panes")) -> None:
    """Send text to all running Claude agent panes."""
    from netwatch.cli.broadcast import run_broadcast

    run_broadcast(message)


@app.command()
def spawn(
    branch: str = typer.Option(..., "--branch", "-b", help="Git branch name (new or existing)"),
    prompt: str = typer.Option("", "--prompt", "-p", help="Kickoff prompt for Claude"),
) -> None:
    """Create a new worktree + tmux window + Claude agent."""
    from netwatch.cli.spawn import run_spawn

    run_spawn(branch=branch, prompt=prompt)


@app.command()
def status(json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON")) -> None:
    """Show current agent state across all panes."""
    from netwatch.cli.status import run_status

    run_status(json_output=json_output)


@app.command()
def tail() -> None:
    """Live stream of state change events (ndjson)."""
    from netwatch.cli.tail import run_tail

    run_tail()


daemon_app = typer.Typer(help="Manage the netwatch daemon.")
app.add_typer(daemon_app, name="daemon")


@daemon_app.command("start")
def daemon_start(
    if_not_running: bool = typer.Option(False, "--if-not-running", help="No-op if already running"),
) -> None:
    """Start the netwatchd daemon."""
    from netwatch.cli.daemon_ctl import start

    start(if_not_running=if_not_running)


@daemon_app.command("stop")
def daemon_stop() -> None:
    """Stop the running daemon."""
    from netwatch.cli.daemon_ctl import stop

    stop()


@daemon_app.command("restart")
def daemon_restart() -> None:
    """Restart the daemon."""
    from netwatch.cli.daemon_ctl import restart

    restart()


@daemon_app.command("status")
def daemon_status() -> None:
    """Show daemon status."""
    from netwatch.cli.daemon_ctl import daemon_status_cmd

    daemon_status_cmd()


@daemon_app.command("logs")
def daemon_logs(follow: bool = typer.Option(True, "--follow/--no-follow", "-f")) -> None:
    """Tail daemon logs."""
    from netwatch.cli.daemon_ctl import logs

    logs(follow=follow)


if __name__ == "__main__":
    app()
