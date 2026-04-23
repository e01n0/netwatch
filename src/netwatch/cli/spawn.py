"""Spawn -- create a new worktree + tmux window + Claude agent."""

from __future__ import annotations

import subprocess
from pathlib import Path

import libtmux
import typer


def _git(*args: str, cwd: Path | None = None) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout.strip()


def run_spawn(branch: str, prompt: str) -> None:
    """Create a new worktree, tmux window, and Claude agent."""
    # --- locate repo root ---
    try:
        repo_root = Path(_git("rev-parse", "--show-toplevel"))
    except RuntimeError:
        typer.echo(
            typer.style("Error:", fg=typer.colors.RED) + " not inside a git repository.",
            err=True,
        )
        raise typer.Exit(code=1) from None

    repo_name = repo_root.name
    safe_branch = branch.replace("/", "-")
    worktree_base = repo_root.parent / f"{repo_name}-worktrees"
    worktree_path = worktree_base / safe_branch

    # --- create or reuse worktree ---
    if worktree_path.exists():
        typer.echo(typer.style("Reusing", dim=True) + f" existing worktree at {worktree_path}")
    else:
        worktree_base.mkdir(parents=True, exist_ok=True)
        try:
            _git("worktree", "add", str(worktree_path), branch, cwd=repo_root)
        except RuntimeError:
            # branch might not exist yet -- create it
            try:
                _git(
                    "worktree",
                    "add",
                    "-b",
                    branch,
                    str(worktree_path),
                    "HEAD",
                    cwd=repo_root,
                )
            except RuntimeError as exc:
                typer.echo(
                    typer.style("Error:", fg=typer.colors.RED)
                    + f" failed to create worktree -- {exc}",
                    err=True,
                )
                raise typer.Exit(code=1) from exc
        typer.echo(typer.style("Created", fg=typer.colors.GREEN) + f" worktree at {worktree_path}")

    # --- create tmux window ---
    server = libtmux.Server()
    try:
        session = server.attached_sessions[0]
    except (IndexError, Exception):
        typer.echo(
            typer.style("Error:", fg=typer.colors.RED) + " no attached tmux session found.",
            err=True,
        )
        raise typer.Exit(code=1) from None

    window_name = f"agent-{safe_branch}"
    window = session.new_window(
        window_name=window_name,
        start_directory=str(worktree_path),
    )
    pane = window.active_pane

    # --- launch claude ---
    cmd = f"claude '{prompt}'" if prompt else "claude"
    pane.send_keys(cmd, enter=True)

    typer.echo(
        typer.style("Spawned", fg=typer.colors.GREEN, bold=True)
        + f"  window={typer.style(window_name, fg=typer.colors.CYAN)}"
        + f"  worktree={worktree_path}"
    )
