"""Tests for state models and aggregator."""

from __future__ import annotations

from netwatch.daemon.state import AgentStatus, PaneState, SessionSnapshot


def test_agent_state_roundtrip(sample_pane: PaneState) -> None:
    data = sample_pane.model_dump(mode="json")
    restored = PaneState.model_validate(data)
    assert restored.pane_id == sample_pane.pane_id
    assert restored.agent_status == AgentStatus.THINKING
    assert restored.agent_tool == "Bash"


def test_snapshot_by_window(sample_snapshot: SessionSnapshot) -> None:
    groups = sample_snapshot.by_window()
    assert len(groups) == 2
    for panes in groups.values():
        assert all(isinstance(p, PaneState) for p in panes)


def test_snapshot_agents(sample_snapshot: SessionSnapshot) -> None:
    agents = sample_snapshot.agents()
    assert len(agents) == 1
    assert agents[0].pane_id == "%1"


def test_snapshot_to_event(sample_snapshot: SessionSnapshot) -> None:
    event = sample_snapshot.to_event()
    assert event["type"] == "snapshot"
    assert "panes" in event["data"]
