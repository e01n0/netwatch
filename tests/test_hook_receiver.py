"""Tests for the Claude Code hook HTTP receiver."""

from __future__ import annotations

from netwatch.daemon.hook_receiver import status_from_hook
from netwatch.daemon.state import AgentStatus


def test_sessionstart_returns_idle() -> None:
    assert status_from_hook("SessionStart", {}) == AgentStatus.IDLE


def test_stop_returns_idle() -> None:
    assert status_from_hook("Stop", {}) == AgentStatus.IDLE


def test_pretooluse_returns_tool_use() -> None:
    assert status_from_hook("PreToolUse", {"tool_name": "Bash"}) == AgentStatus.TOOL_USE


def test_posttooluse_returns_thinking() -> None:
    assert status_from_hook("PostToolUse", {}) == AgentStatus.THINKING


def test_unknown_event_returns_unknown() -> None:
    assert status_from_hook("SomeNewEvent", {}) == AgentStatus.UNKNOWN


def test_notification_returns_unknown() -> None:
    assert status_from_hook("Notification", {"type": "info"}) == AgentStatus.UNKNOWN
