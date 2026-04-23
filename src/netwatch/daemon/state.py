"""Core state models — the single source of truth for all agent/pane tracking."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentStatus(StrEnum):
    IDLE = "idle"
    THINKING = "thinking"
    TOOL_USE = "tool-use"
    WAITING = "waiting"
    ERROR = "error"
    UNKNOWN = "unknown"


class PaneState(BaseModel):
    pane_id: str
    session_name: str
    window_index: int
    window_name: str
    pane_index: int
    tty: str = ""
    command: str = ""
    cwd: str = ""
    is_agent: bool = False
    agent_status: AgentStatus = AgentStatus.UNKNOWN
    agent_tool: str | None = None
    claude_session_id: str | None = None
    branch: str | None = None
    last_event_ts: datetime | None = None
    token_usage: int | None = None

    @property
    def display_status(self) -> str:
        if not self.is_agent:
            return self.command
        return f"{self.command} ({self.agent_status})"


class SessionSnapshot(BaseModel):
    """Full state snapshot sent to subscribers."""

    panes: dict[str, PaneState] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    daemon_uptime_s: float = 0.0

    def agents(self) -> list[PaneState]:
        return [p for p in self.panes.values() if p.is_agent]

    def by_window(self) -> dict[str, list[PaneState]]:
        groups: dict[str, list[PaneState]] = {}
        for p in self.panes.values():
            key = f"{p.session_name}:{p.window_index}:{p.window_name}"
            groups.setdefault(key, []).append(p)
        for v in groups.values():
            v.sort(key=lambda x: x.pane_index)
        return groups

    def to_event(self, event_type: str = "snapshot") -> dict[str, Any]:
        return {
            "type": event_type,
            "data": self.model_dump(mode="json"),
        }
