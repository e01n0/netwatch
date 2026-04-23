"""Watch tmux for pane/window/session changes via libtmux."""

from __future__ import annotations

import asyncio
import logging

import libtmux

from netwatch.daemon.state import PaneState

logger = logging.getLogger(__name__)

AGENT_COMMANDS = {"claude", "codex", "gemini", "amp", "opencode", "aider", "cursor-agent"}


def snapshot_panes(
    server: libtmux.Server, session_filter: str | None = None
) -> dict[str, PaneState]:
    panes: dict[str, PaneState] = {}
    for session in server.sessions:
        if session_filter and session.name != session_filter:
            continue
        for window in session.windows:
            for pane in window.panes:
                cmd = pane.pane_current_command or ""
                pane_id = pane.pane_id or ""
                panes[pane_id] = PaneState(
                    pane_id=pane_id,
                    session_name=session.name or "",
                    window_index=int(window.window_index or 0),
                    window_name=window.name or "",
                    pane_index=int(pane.pane_index or 0),
                    tty=pane.pane_tty or "",
                    command=cmd,
                    cwd=pane.pane_current_path or "",
                    is_agent=cmd.lower() in AGENT_COMMANDS,
                )
    return panes


class TmuxWatcher:
    def __init__(self, queue: asyncio.Queue, poll_interval: float = 2.0) -> None:
        self._queue = queue
        self._poll_interval = poll_interval
        self._server: libtmux.Server | None = None
        self._prev_pane_ids: set[str] = set()

    async def run(self) -> None:
        while True:
            try:
                self._server = libtmux.Server()
                logger.info("Connected to tmux server")
                await self._poll_loop()
            except libtmux.exc.LibTmuxException:
                logger.warning("tmux server not available, retrying in 5s")
                await asyncio.sleep(5)
            except Exception:
                logger.exception("TmuxWatcher error, retrying in 5s")
                await asyncio.sleep(5)

    async def _poll_loop(self) -> None:
        while True:
            assert self._server is not None
            try:
                panes = snapshot_panes(self._server)
                current_ids = set(panes.keys())
                added = current_ids - self._prev_pane_ids
                removed = self._prev_pane_ids - current_ids

                if added or removed:
                    logger.debug("Pane changes: +%d -%d", len(added), len(removed))

                await self._queue.put(("tmux_snapshot", panes))
                self._prev_pane_ids = current_ids
            except libtmux.exc.LibTmuxException:
                raise
            except Exception:
                logger.exception("Poll error")
            await asyncio.sleep(self._poll_interval)
