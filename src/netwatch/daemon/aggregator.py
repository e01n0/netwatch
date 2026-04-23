"""Correlates tmux pane state with JSONL / hook events into a unified snapshot."""

from __future__ import annotations

import logging
from datetime import datetime

from netwatch.daemon.state import AgentStatus, PaneState, SessionSnapshot

logger = logging.getLogger(__name__)


class Aggregator:
    def __init__(self) -> None:
        self._panes: dict[str, PaneState] = {}
        self._cwd_status: dict[str, tuple[AgentStatus, str | None]] = {}
        self._start_time = datetime.now()

    def apply_tmux_snapshot(self, panes: dict[str, PaneState]) -> bool:
        changed = False
        old_ids = set(self._panes.keys())
        new_ids = set(panes.keys())

        for removed_id in old_ids - new_ids:
            del self._panes[removed_id]
            changed = True

        for pane_id, pane in panes.items():
            existing = self._panes.get(pane_id)
            if existing is None or existing.cwd != pane.cwd or existing.command != pane.command:
                changed = True

            if pane.is_agent:
                cwd_key = pane.cwd
                if cwd_key in self._cwd_status:
                    status, tool = self._cwd_status[cwd_key]
                    pane.agent_status = status
                    pane.agent_tool = tool
                else:
                    pane.agent_status = AgentStatus.UNKNOWN

            self._panes[pane_id] = pane

        return changed

    def apply_jsonl_update(self, cwd: str, status: AgentStatus, tool: str | None) -> bool:
        self._cwd_status[cwd] = (status, tool)
        changed = False
        for pane in self._panes.values():
            if pane.is_agent and pane.cwd and cwd in pane.cwd:
                pane.agent_status = status
                pane.agent_tool = tool
                pane.last_event_ts = datetime.now()
                changed = True
        return changed

    def apply_hook_event(self, session_id: str, status: AgentStatus, tool: str | None) -> bool:
        changed = False
        for pane in self._panes.values():
            if pane.is_agent and pane.claude_session_id == session_id:
                pane.agent_status = status
                pane.agent_tool = tool
                pane.last_event_ts = datetime.now()
                changed = True
        return changed

    def snapshot(self) -> SessionSnapshot:
        uptime = (datetime.now() - self._start_time).total_seconds()
        return SessionSnapshot(
            panes=dict(self._panes),
            timestamp=datetime.now(),
            daemon_uptime_s=uptime,
        )
