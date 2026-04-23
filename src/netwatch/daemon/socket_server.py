"""Unix socket pub/sub server — clients subscribe for state updates."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from netwatch.common.paths import socket_path

logger = logging.getLogger(__name__)


class SocketServer:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or socket_path()
        self._subscribers: list[asyncio.StreamWriter] = []
        self._state_callback: Any = None

    def set_state_callback(self, callback: Any) -> None:
        self._state_callback = callback

    async def run(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            self._path.unlink()

        server = await asyncio.start_unix_server(self._handle_client, path=str(self._path))
        logger.info("Socket server listening on %s", self._path)

        async with server:
            await server.serve_forever()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        logger.debug("Client connected")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                cmd = msg.get("cmd", "")
                match cmd:
                    case "GET_STATE":
                        state = self._state_callback() if self._state_callback else {}
                        await self._send(writer, state)
                    case "SUBSCRIBE":
                        self._subscribers.append(writer)
                        state = self._state_callback() if self._state_callback else {}
                        await self._send(writer, state)
                    case "JUMP":
                        await self._broadcast_cmd(msg)
                    case "BROADCAST":
                        await self._broadcast_cmd(msg)
                    case _:
                        await self._send(writer, {"error": f"unknown command: {cmd}"})
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            if writer in self._subscribers:
                self._subscribers.remove(writer)
            writer.close()
            logger.debug("Client disconnected")

    async def publish(self, event: dict[str, Any]) -> None:
        dead: list[asyncio.StreamWriter] = []
        for sub in self._subscribers:
            try:
                await self._send(sub, event)
            except (ConnectionResetError, BrokenPipeError):
                dead.append(sub)
        for d in dead:
            self._subscribers.remove(d)

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, msg: dict[str, Any]) -> None:
        data = json.dumps(msg, default=str) + "\n"
        writer.write(data.encode())
        await writer.drain()

    async def _broadcast_cmd(self, msg: dict[str, Any]) -> None:
        for sub in self._subscribers:
            with contextlib.suppress(ConnectionResetError, BrokenPipeError):
                await self._send(sub, msg)
