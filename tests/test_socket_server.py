"""Tests for the unix socket pub/sub server."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

import pytest

from netwatch.daemon.socket_server import SocketServer


@pytest.fixture
def socket_path() -> Path:
    # AF_UNIX has a 104-byte limit on macOS; pytest tmp_path is too long
    import uuid

    p = Path(f"/tmp/nw-test-{uuid.uuid4().hex[:8]}.sock")
    yield p
    p.unlink(missing_ok=True)


@pytest.fixture
def server(socket_path: Path) -> SocketServer:
    srv = SocketServer(path=socket_path)
    srv.set_state_callback(lambda: {"type": "snapshot", "data": {"panes": {}}})
    return srv


async def _connect(socket_path: Path) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.open_unix_connection(str(socket_path))


async def _send_recv(
    writer: asyncio.StreamWriter,
    reader: asyncio.StreamReader,
    msg: dict,
) -> dict:
    writer.write((json.dumps(msg) + "\n").encode())
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=2.0)
    return json.loads(line)


@pytest.mark.asyncio
async def test_get_state(server: SocketServer, socket_path: Path) -> None:
    task = asyncio.create_task(server.run())
    await asyncio.sleep(0.1)
    try:
        reader, writer = await _connect(socket_path)
        resp = await _send_recv(writer, reader, {"cmd": "GET_STATE"})
        assert resp["type"] == "snapshot"
        assert "panes" in resp["data"]
        writer.close()
        await writer.wait_closed()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_subscribe_gets_initial_state(server: SocketServer, socket_path: Path) -> None:
    task = asyncio.create_task(server.run())
    await asyncio.sleep(0.1)
    try:
        reader, writer = await _connect(socket_path)
        writer.write((json.dumps({"cmd": "SUBSCRIBE"}) + "\n").encode())
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        resp = json.loads(line)
        assert resp["type"] == "snapshot"
        writer.close()
        await writer.wait_closed()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_publish_reaches_subscriber(server: SocketServer, socket_path: Path) -> None:
    task = asyncio.create_task(server.run())
    await asyncio.sleep(0.1)
    try:
        reader, writer = await _connect(socket_path)
        writer.write((json.dumps({"cmd": "SUBSCRIBE"}) + "\n").encode())
        await writer.drain()
        # Read initial state
        await asyncio.wait_for(reader.readline(), timeout=2.0)

        # Publish an event
        await server.publish({"type": "update", "data": "test"})

        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        event = json.loads(line)
        assert event["type"] == "update"
        assert event["data"] == "test"
        writer.close()
        await writer.wait_closed()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_unknown_command_returns_error(server: SocketServer, socket_path: Path) -> None:
    task = asyncio.create_task(server.run())
    await asyncio.sleep(0.1)
    try:
        reader, writer = await _connect(socket_path)
        resp = await _send_recv(writer, reader, {"cmd": "NONSENSE"})
        assert "error" in resp
        writer.close()
        await writer.wait_closed()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
