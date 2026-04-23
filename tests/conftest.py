"""Shared fixtures for netwatch tests."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from netwatch.daemon.state import AgentStatus, PaneState, SessionSnapshot


@pytest.fixture
def sample_pane() -> PaneState:
    return PaneState(
        pane_id="%1",
        session_name="work",
        window_index=1,
        window_name="brickify",
        pane_index=0,
        tty="/dev/ttys001",
        command="claude",
        cwd="/Users/test/git/brickify",
        is_agent=True,
        agent_status=AgentStatus.THINKING,
        agent_tool="Bash",
    )


@pytest.fixture
def sample_snapshot(sample_pane: PaneState) -> SessionSnapshot:
    idle_pane = PaneState(
        pane_id="%2",
        session_name="work",
        window_index=1,
        window_name="brickify",
        pane_index=1,
        command="git",
        cwd="/Users/test/git/brickify",
    )
    shell_pane = PaneState(
        pane_id="%3",
        session_name="work",
        window_index=2,
        window_name="dotfiles",
        pane_index=0,
        command="zsh",
        cwd="/Users/test/dotfiles",
    )
    return SessionSnapshot(
        panes={"%1": sample_pane, "%2": idle_pane, "%3": shell_pane},
        timestamp=datetime(2026, 4, 23, 12, 0, 0),
    )


@pytest.fixture
def sample_jsonl_tool_use(tmp_path: Path) -> Path:
    f = tmp_path / "session.jsonl"
    lines = [
        json.dumps({"type": "user", "message": {"content": "run tests"}}),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}
                    ]
                },
            }
        ),
    ]
    f.write_text("\n".join(lines) + "\n")
    return f


@pytest.fixture
def sample_jsonl_error(tmp_path: Path) -> Path:
    f = tmp_path / "session.jsonl"
    lines = [
        json.dumps({"type": "result", "is_error": True, "error": "rate_limit_exceeded"}),
    ]
    f.write_text("\n".join(lines) + "\n")
    return f
