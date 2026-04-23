"""HTTP server that receives Claude Code hook events."""

from __future__ import annotations

import asyncio
import json
import logging

from aiohttp import web

from netwatch.daemon.state import AgentStatus

logger = logging.getLogger(__name__)


def status_from_hook(event_name: str, payload: dict) -> AgentStatus:
    match event_name:
        case "SessionStart":
            return AgentStatus.IDLE
        case "SessionEnd" | "Stop":
            return AgentStatus.IDLE
        case "PreToolUse":
            return AgentStatus.TOOL_USE
        case "PostToolUse":
            return AgentStatus.THINKING
        case "Notification":
            return AgentStatus.UNKNOWN
        case _:
            return AgentStatus.UNKNOWN


class HookReceiver:
    def __init__(self, queue: asyncio.Queue, host: str = "127.0.0.1", port: int = 0) -> None:
        self._queue = queue
        self._host = host
        self._port = port
        self.actual_port: int | None = None

    async def run(self) -> None:
        app = web.Application()
        app.router.add_post("/hook/{event_name}", self._handle_hook)
        app.router.add_get("/health", self._handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        await site.start()

        sockets = site._server.sockets  # type: ignore[union-attr]
        if sockets:
            self.actual_port = sockets[0].getsockname()[1]

        logger.info("Hook receiver listening on %s:%d", self._host, self.actual_port)

        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    async def _handle_hook(self, request: web.Request) -> web.Response:
        event_name = request.match_info["event_name"]
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            payload = {}

        status = status_from_hook(event_name, payload)
        tool_name = payload.get("tool_name")
        session_id = payload.get("session_id", "")

        await self._queue.put(
            (
                "hook_event",
                {
                    "event": event_name,
                    "session_id": session_id,
                    "status": status,
                    "tool": tool_name,
                    "payload": payload,
                },
            )
        )

        return web.json_response({"ok": True})

    async def _handle_health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "healthy"})
