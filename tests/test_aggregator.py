"""Tests for the state aggregator."""

from __future__ import annotations

from netwatch.daemon.aggregator import Aggregator
from netwatch.daemon.state import AgentStatus, PaneState


def _make_pane(
    pane_id: str, cmd: str = "zsh", cwd: str = "/tmp", is_agent: bool = False
) -> PaneState:
    return PaneState(
        pane_id=pane_id,
        session_name="test",
        window_index=1,
        window_name="test-win",
        pane_index=0,
        command=cmd,
        cwd=cwd,
        is_agent=is_agent,
    )


def test_apply_tmux_snapshot_detects_new_panes() -> None:
    agg = Aggregator()
    panes = {"%1": _make_pane("%1")}
    changed = agg.apply_tmux_snapshot(panes)
    assert changed is True
    assert "%1" in agg.snapshot().panes


def test_apply_tmux_snapshot_detects_removed_panes() -> None:
    agg = Aggregator()
    agg.apply_tmux_snapshot({"%1": _make_pane("%1"), "%2": _make_pane("%2")})
    changed = agg.apply_tmux_snapshot({"%1": _make_pane("%1")})
    assert changed is True
    assert "%2" not in agg.snapshot().panes


def test_apply_tmux_snapshot_no_change() -> None:
    agg = Aggregator()
    pane = _make_pane("%1")
    agg.apply_tmux_snapshot({"%1": pane})
    changed = agg.apply_tmux_snapshot({"%1": pane})
    assert changed is False


def test_apply_jsonl_update_correlates_by_cwd() -> None:
    agg = Aggregator()
    pane = _make_pane("%1", cmd="claude", cwd="/home/user/brickify", is_agent=True)
    agg.apply_tmux_snapshot({"%1": pane})
    changed = agg.apply_jsonl_update("/home/user/brickify", AgentStatus.TOOL_USE, "Bash")
    assert changed is True
    snap = agg.snapshot()
    assert snap.panes["%1"].agent_status == AgentStatus.TOOL_USE
    assert snap.panes["%1"].agent_tool == "Bash"


def test_apply_jsonl_no_match() -> None:
    agg = Aggregator()
    agg.apply_tmux_snapshot({"%1": _make_pane("%1", cmd="zsh", cwd="/tmp")})
    changed = agg.apply_jsonl_update("/somewhere/else", AgentStatus.TOOL_USE, "Bash")
    assert changed is False
