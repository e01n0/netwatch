"""Textual HUD app — the persistent sidebar that replaces the bash NETWATCH."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Static

from netwatch.common.socket_client import NetwatchClient
from netwatch.daemon.state import AgentStatus, PaneState, SessionSnapshot

STYLES_PATH = Path(__file__).parent / "styles" / "netrunner.tcss"

STATUS_ICONS = {
    AgentStatus.THINKING: "⚡",  # ⚡
    AgentStatus.TOOL_USE: "⚡",  # ⚡
    AgentStatus.IDLE: "◆",  # ◆
    AgentStatus.WAITING: "◆",  # ◆
    AgentStatus.ERROR: "✗",  # ✗
    AgentStatus.UNKNOWN: " ",
}


class PaneRow(Static):
    """A single pane entry — clickable to jump."""

    pane_id: str = ""

    def __init__(self, pane: PaneState, index: int) -> None:
        self.pane_id = pane.pane_id
        icon = STATUS_ICONS.get(pane.agent_status, " ") if pane.is_agent else " "
        cwd = pane.cwd.replace(str(Path.home()), "~")
        if len(cwd) > 20:
            cwd = "…" + cwd[-19:]
        label = f"{index:2d}│ {icon} {pane.command:<8s} {cwd}"
        super().__init__(label, classes="pane-row")
        if pane.is_agent:
            match pane.agent_status:
                case AgentStatus.THINKING | AgentStatus.TOOL_USE:
                    self.add_class("--agent-active")
                case AgentStatus.ERROR:
                    self.add_class("--agent-error")
                case _:
                    self.add_class("--agent-idle")

    async def on_click(self) -> None:
        try:
            client = NetwatchClient()
            await client.connect()
            await client.jump(self.pane_id)
            await client.close()
        except OSError:
            pass


class WindowGroup(Static):
    """Group header + pane rows for one tmux window."""

    def __init__(self, window_key: str, panes: list[PaneState], start_index: int) -> None:
        super().__init__()
        self._window_key = window_key
        self._panes = panes
        self._start_index = start_index

    def compose(self) -> ComposeResult:
        parts = self._window_key.split(":")
        win_name = parts[2] if len(parts) > 2 else self._window_key
        yield Static(f"[W:{win_name}]", classes="window-header")
        for i, pane in enumerate(self._panes):
            yield PaneRow(pane, self._start_index + i)


class NetwatchApp(App):
    CSS_PATH = str(STYLES_PATH) if STYLES_PATH.exists() else None
    TITLE = "\U000f06a9 NETWATCH"  # 󰚩

    snapshot: reactive[SessionSnapshot | None] = reactive(None)

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, id="header")
        yield Vertical(id="pane-list")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.5, self._poll_state)

    async def _poll_state(self) -> None:
        try:
            client = NetwatchClient()
            await client.connect()
            raw = await client.get_state()
            await client.close()
            data = raw.get("data", {})
            self.snapshot = SessionSnapshot.model_validate(data)
        except (OSError, Exception):
            pass

    def watch_snapshot(self, snap: SessionSnapshot | None) -> None:
        if snap is None:
            return
        container = self.query_one("#pane-list", Vertical)
        container.remove_children()
        idx = 1
        for window_key, panes in snap.by_window().items():
            filtered = [p for p in panes if not p.pane_id.startswith("NETWATCH")]
            if not filtered:
                continue
            container.mount(WindowGroup(window_key, filtered, idx))
            idx += len(filtered)

        self.query_one("#footer", Static).update(
            f"─ {len(snap.panes)} panes │ {len(snap.agents())} agents"
        )
