"""Tests for JSONL transcript parsing."""

from __future__ import annotations

from netwatch.daemon.jsonl_watcher import classify_jsonl_line
from netwatch.daemon.state import AgentStatus


def test_classify_tool_use() -> None:
    line = (
        '{"type":"assistant","message":{"content":'
        '[{"type":"tool_use","name":"Bash","input":{"command":"ls"}}]}}'
    )
    status, tool = classify_jsonl_line(line)
    assert status == AgentStatus.TOOL_USE
    assert tool == "Bash"


def test_classify_thinking() -> None:
    line = '{"type":"assistant","message":{"content":[{"type":"thinking","thinking":"hmm"}]}}'
    status, tool = classify_jsonl_line(line)
    assert status == AgentStatus.THINKING
    assert tool is None


def test_classify_user_message() -> None:
    line = '{"type":"user","message":{"content":"hello"}}'
    status, _ = classify_jsonl_line(line)
    assert status == AgentStatus.THINKING


def test_classify_error() -> None:
    line = '{"type":"result","is_error":true,"error":"rate_limit"}'
    status, _ = classify_jsonl_line(line)
    assert status == AgentStatus.ERROR


def test_classify_assistant_idle() -> None:
    line = '{"type":"assistant","message":{"content":[{"type":"text","text":"done"}]}}'
    status, _ = classify_jsonl_line(line)
    assert status == AgentStatus.IDLE


def test_classify_garbage() -> None:
    status, tool = classify_jsonl_line("not json at all")
    assert status == AgentStatus.UNKNOWN
    assert tool is None
