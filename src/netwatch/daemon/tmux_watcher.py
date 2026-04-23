"""Watch tmux for pane/window/session changes via libtmux."""

from __future__ import annotations

import asyncio
import logging
import subprocess

import libtmux

from netwatch.daemon.state import PaneState

logger = logging.getLogger(__name__)

AGENT_BINARIES = {"claude", "codex", "gemini", "amp", "opencode", "aider", "cursor-agent"}


def _find_agent_panes_by_tty() -> dict[str, str]:
    """Scan ps for agent processes and return {tty: agent_name}."""
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "tty,comm"],
            text=True,
            timeout=3,
        )
        tty_to_agent: dict[str, str] = {}
        for line in out.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            tty, comm = parts[0], parts[1]
            binary = comm.split("/")[-1].lower()
            if binary in AGENT_BINARIES:
                tty_to_agent[tty] = binary
        return tty_to_agent
    except Exception:
        return {}


def snapshot_panes(
    server: libtmux.Server, session_filter: str | None = None
) -> dict[str, PaneState]:
    agent_ttys = _find_agent_panes_by_tty()

    panes: dict[str, PaneState] = {}
    for session in server.sessions:
        if session_filter and session.name != session_filter:
            continue
        for window in session.windows:
            for pane in window.panes:
                cmd = pane.pane_current_command or ""
                pane_id = pane.pane_id or ""
                tty = pane.pane_tty or ""
                cwd = pane.pane_current_path or ""

                # Detect agent by checking if this pane's TTY has an agent process
                tty_short = tty.replace("/dev/", "")
                is_agent = tty_short in agent_ttys
                agent_name = agent_ttys.get(tty_short, cmd)

                # Use meaningful display name
                display_cmd = agent_name if is_agent else cmd

                # Window name: use cwd basename if tmux auto-named it something useless
                win_name = window.name or ""
                if _is_auto_name(win_name):
                    win_name = cwd.split("/")[-1] if cwd else win_name

                panes[pane_id] = PaneState(
                    pane_id=pane_id,
                    session_name=session.name or "",
                    window_index=int(window.window_index or 0),
                    window_name=win_name,
                    pane_index=int(pane.pane_index or 0),
                    tty=tty,
                    command=display_cmd,
                    cwd=cwd,
                    is_agent=is_agent,
                )
    return panes


def _is_auto_name(name: str) -> bool:
    """Detect tmux auto-generated window names (process names, version strings)."""
    if not name:
        return True
    # Version-like strings (2.1.118, python3.12, node22)
    if any(c.isdigit() for c in name) and "." in name:
        return True
    # Common process names that aren't useful window labels
    auto_names = {
        "zsh",
        "bash",
        "sh",
        "fish",
        "python",
        "python3",
        "python3.12",
        "node",
        "ruby",
        "perl",
        "vim",
        "nvim",
    }
    return name.lower() in auto_names


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
