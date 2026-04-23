"""Thin client for talking to the netwatchd unix socket."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from netwatch.common.paths import socket_path


class NetwatchClient:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or socket_path()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_unix_connection(str(self._path))

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    async def send(self, msg: dict[str, Any]) -> None:
        assert self._writer is not None
        data = json.dumps(msg) + "\n"
        self._writer.write(data.encode())
        await self._writer.drain()

    async def recv(self) -> dict[str, Any]:
        assert self._reader is not None
        line = await self._reader.readline()
        return json.loads(line)

    async def get_state(self) -> dict[str, Any]:
        await self.send({"cmd": "GET_STATE"})
        return await self.recv()

    async def subscribe(self):
        await self.send({"cmd": "SUBSCRIBE"})
        while True:
            msg = await self.recv()
            yield msg

    async def jump(self, pane_id: str) -> None:
        await self.send({"cmd": "JUMP", "pane_id": pane_id})

    async def broadcast(self, text: str) -> None:
        await self.send({"cmd": "BROADCAST", "text": text})


def get_state_sync() -> dict[str, Any]:
    async def _inner():
        client = NetwatchClient()
        await client.connect()
        state = await client.get_state()
        await client.close()
        return state

    return asyncio.run(_inner())
