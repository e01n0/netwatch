"""Textual HUD app — the persistent sidebar that replaces the bash NETWATCH."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.reactive import reactive
from textual.widgets import Footer, Static

from netwatch.common.socket_client import NetwatchClient
from netwatch.daemon.state import AgentStatus, PaneState, SessionSnapshot

STYLES_PATH = Path(__file__).parent / "styles" / "netrunner.tcss"

STATUS_ICONS = {
    AgentStatus.THINKING: "⚡",
    AgentStatus.TOOL_USE: "⚡",
    AgentStatus.IDLE: "◆",
    AgentStatus.WAITING: "◆",
    AgentStatus.ERROR: "✗",
    AgentStatus.UNKNOWN: " ",
}


class PaneRow(Static, can_focus=True):
    """A single pane entry — clickable and focusable."""

    DEFAULT_CSS = """
    PaneRow { height: 1; }
    PaneRow:focus { background: #0A291F; color: #00FFF7; text-style: bold; }
    PaneRow:hover { background: #0A291F; color: #D9FFF7; }
    PaneRow.--agent-active { color: #00FF66; }
    PaneRow.--agent-idle { color: #00FFF7; }
    PaneRow.--agent-error { color: #FF3C50; }
    """

    def __init__(self, pane: PaneState, index: int) -> None:
        self.target_pane_id = pane.pane_id
        icon = STATUS_ICONS.get(pane.agent_status, " ") if pane.is_agent else " "
        cwd = pane.cwd.replace(str(Path.home()), "~")
        if len(cwd) > 20:
            cwd = "…" + cwd[-19:]
        label = f"{index:2d}│ {icon} {pane.command:<8s} {cwd}"
        super().__init__(label)
        if pane.is_agent:
            match pane.agent_status:
                case AgentStatus.THINKING | AgentStatus.TOOL_USE:
                    self.add_class("--agent-active")
                case AgentStatus.ERROR:
                    self.add_class("--agent-error")
                case _:
                    self.add_class("--agent-idle")

    async def _do_jump(self) -> None:
        try:
            client = NetwatchClient()
            await client.connect()
            await client.jump(self.target_pane_id)
            await client.close()
        except OSError:
            pass

    async def on_click(self) -> None:
        await self._do_jump()

    async def action_select(self) -> None:
        await self._do_jump()


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


class OfflineBanner(Static):
    """Shown when daemon is unreachable."""

    DEFAULT_CSS = """
    OfflineBanner {
        height: auto;
        padding: 1 2;
        color: #FFD600;
        text-style: italic;
    }
    """

    def __init__(self) -> None:
        super().__init__("daemon offline\nrun: netwatch daemon start")


class NetwatchApp(App):
    CSS_PATH = str(STYLES_PATH) if STYLES_PATH.exists() else None
    TITLE = "\U000f06a9 NETWATCH"

    BINDINGS = [  # noqa: RUF012
        Binding("j", "cursor_down", "Down", show=True),
        Binding("k", "cursor_up", "Up", show=True),
        Binding("enter", "select_pane", "Jump", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    snapshot: reactive[SessionSnapshot | None] = reactive(None)
    _daemon_online: bool = False
    _pane_rows: list[PaneRow] = []  # noqa: RUF012
    _focus_index: int = 0

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, id="header")
        yield ScrollableContainer(id="pane-list")
        yield Static("", id="status-bar")
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
            self._daemon_online = True
        except OSError:
            self._daemon_online = False
            self.snapshot = None
        except Exception:
            pass

    def watch_snapshot(self, snap: SessionSnapshot | None) -> None:
        container = self.query_one("#pane-list", ScrollableContainer)
        container.remove_children()
        self._pane_rows = []

        if not self._daemon_online or snap is None:
            container.mount(OfflineBanner())
            self._update_status_bar(0, 0)
            return

        idx = 1
        for window_key, panes in snap.by_window().items():
            filtered = [p for p in panes if "NETWATCH" not in p.pane_id]
            if not filtered:
                continue
            group = WindowGroup(window_key, filtered, idx)
            container.mount(group)
            idx += len(filtered)

        self._pane_rows = list(self.query(PaneRow))
        if self._pane_rows:
            self._focus_index = min(self._focus_index, len(self._pane_rows) - 1)
            self._pane_rows[self._focus_index].focus()

        self._update_status_bar(len(snap.panes), len(snap.agents()))

    def _update_status_bar(self, pane_count: int, agent_count: int) -> None:
        bar = self.query_one("#status-bar", Static)
        if self._daemon_online:
            bar.update(f"─ {pane_count} panes │ {agent_count} agents")
        else:
            bar.update("─ daemon offline")

    def action_cursor_down(self) -> None:
        if not self._pane_rows:
            return
        self._focus_index = min(self._focus_index + 1, len(self._pane_rows) - 1)
        self._pane_rows[self._focus_index].focus()

    def action_cursor_up(self) -> None:
        if not self._pane_rows:
            return
        self._focus_index = max(self._focus_index - 1, 0)
        self._pane_rows[self._focus_index].focus()

    async def action_select_pane(self) -> None:
        if self._pane_rows and 0 <= self._focus_index < len(self._pane_rows):
            await self._pane_rows[self._focus_index]._do_jump()

    async def action_refresh(self) -> None:
        await self._poll_state()
