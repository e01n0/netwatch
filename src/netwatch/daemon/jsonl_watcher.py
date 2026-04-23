"""Watch Claude Code JSONL session transcripts for agent state changes."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from netwatch.common.paths import claude_projects_dir
from netwatch.daemon.state import AgentStatus

logger = logging.getLogger(__name__)


def classify_jsonl_line(line: str) -> tuple[AgentStatus, str | None]:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return AgentStatus.UNKNOWN, None

    msg_type = obj.get("type", "")

    if msg_type == "assistant":
        content = obj.get("message", {}).get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    return AgentStatus.TOOL_USE, tool_name
                if isinstance(block, dict) and block.get("type") == "thinking":
                    return AgentStatus.THINKING, None
        return AgentStatus.IDLE, None

    if msg_type == "user":
        return AgentStatus.THINKING, None

    if msg_type == "result" and obj.get("is_error"):
        return AgentStatus.ERROR, None

    return AgentStatus.UNKNOWN, None


class _JsonlHandler(FileSystemEventHandler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        self._queue = queue
        self._loop = loop
        self._file_positions: dict[str, int] = {}

    def on_modified(self, event: FileModifiedEvent | object) -> None:  # type: ignore[override]
        if not isinstance(event, FileModifiedEvent):
            return
        path = Path(str(event.src_path))
        if path.suffix != ".jsonl":
            return
        self._process_new_lines(path)

    def _process_new_lines(self, path: Path) -> None:
        key = str(path)
        pos = self._file_positions.get(key, 0)
        try:
            with open(path) as f:
                f.seek(pos)
                lines = f.readlines()
                self._file_positions[key] = f.tell()
        except OSError:
            return

        if not lines:
            return

        last_line = lines[-1].strip()
        if not last_line:
            return

        status, tool = classify_jsonl_line(last_line)
        cwd = self._cwd_from_path(path)

        asyncio.run_coroutine_threadsafe(
            self._queue.put(
                ("jsonl_update", {"cwd": cwd, "status": status, "tool": tool, "path": str(path)})
            ),
            self._loop,
        )

    @staticmethod
    def _cwd_from_path(path: Path) -> str:
        parts = path.parent.name
        return parts.replace("-", "/").lstrip("/")


class JsonlWatcher:
    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._observer: Observer | None = None

    async def run(self) -> None:
        projects = claude_projects_dir()
        if not projects.exists():
            logger.warning("Claude projects dir not found at %s", projects)
            return

        loop = asyncio.get_running_loop()
        handler = _JsonlHandler(self._queue, loop)
        self._observer = Observer()
        self._observer.schedule(handler, str(projects), recursive=True)
        self._observer.start()
        logger.info("JSONL watcher started on %s", projects)

        try:
            while True:
                await asyncio.sleep(1)
        finally:
            if self._observer:
                self._observer.stop()
                self._observer.join()
