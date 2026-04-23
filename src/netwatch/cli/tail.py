"""Tail -- live stream of state change events (ndjson)."""

from __future__ import annotations

import asyncio
import json
import sys

import typer

from netwatch.common.socket_client import NetwatchClient


async def _stream() -> None:
    """Connect and stream events until cancelled."""
    client = NetwatchClient()
    try:
        await client.connect()
    except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
        typer.echo(
            typer.style("Error: daemon not running", fg=typer.colors.RED) + f" -- {exc}",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    try:
        async for event in client.subscribe():
            line = json.dumps(event, default=str)
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
    except asyncio.CancelledError:
        pass
    finally:
        await client.close()


def run_tail() -> None:
    """Stream daemon events to stdout."""
    try:
        asyncio.run(_stream())
    except KeyboardInterrupt:
        typer.echo(typer.style("\nStream closed.", dim=True))
