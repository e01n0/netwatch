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

_STATUS_CLASSES = {"--agent-active", "--agent-idle", "--agent-error"}


def _format_row(pane: PaneState, index: int) -> tuple[str, str]:
    """Return (label, css_class) for a pane row."""
    icon = STATUS_ICONS.get(pane.agent_status, " ") if pane.is_agent else " "
    cwd = pane.cwd.replace(str(Path.home()), "~")
    if len(cwd) > 20:
        cwd = "…" + cwd[-19:]
    label = f"{index:2d}│ {icon} {pane.command:<8s} {cwd}"
    cls = ""
    if pane.is_agent:
        match pane.agent_status:
            case AgentStatus.THINKING | AgentStatus.TOOL_USE:
                cls = "--agent-active"
            case AgentStatus.ERROR:
                cls = "--agent-error"
            case _:
                cls = "--agent-idle"
    return label, cls


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
        label, cls = _format_row(pane, index)
        super().__init__(label)
        if cls:
            self.add_class(cls)

    def refresh_from(self, pane: PaneState, index: int) -> None:
        """Update label and classes in-place — no DOM rebuild, no-op if unchanged."""
        self.target_pane_id = pane.pane_id
        label, cls = _format_row(pane, index)
        current = self._content  # type: ignore[attr-defined]
        if str(current) != label:
            self.update(label)
        current_classes = self.classes & _STATUS_CLASSES
        wanted = {cls} if cls else set()
        if current_classes != wanted:
            for old in current_classes - wanted:
                self.remove_class(old)
            for new in wanted - current_classes:
                self.add_class(new)

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


class WindowHeader(Static):
    """Group header for a tmux window."""

    DEFAULT_CSS = """
    WindowHeader { color: #2D6E57; padding: 1 0 0 1; height: auto; }
    """


class OfflineBanner(Static):
    """Shown when daemon is unreachable."""

    DEFAULT_CSS = """
    OfflineBanner { height: auto; padding: 1 2; color: #FFD600; text-style: italic; }
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
    _last_pane_key: str = ""

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, id="header")
        yield ScrollableContainer(id="pane-list")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.0, self._poll_state)

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

    def _build_pane_key(self, snap: SessionSnapshot) -> str:
        """Fingerprint of which panes exist, to detect structural changes."""
        ids = sorted(snap.panes.keys())
        return "|".join(ids)

    def watch_snapshot(self, snap: SessionSnapshot | None) -> None:
        container = self.query_one("#pane-list", ScrollableContainer)

        if not self._daemon_online or snap is None:
            if not self.query(OfflineBanner):
                container.remove_children()
                self._pane_rows = []
                container.mount(OfflineBanner())
            self._update_status_bar(0, 0)
            return

        # Remove offline banner if present
        for banner in self.query(OfflineBanner):
            banner.remove()

        new_key = self._build_pane_key(snap)
        structural_change = new_key != self._last_pane_key

        if structural_change:
            # Panes added or removed — full rebuild (rare)
            container.remove_children()
            self._pane_rows = []
            idx = 1
            for window_key, panes in snap.by_window().items():
                filtered = [p for p in panes if "NETWATCH" not in p.pane_id]
                if not filtered:
                    continue
                parts = window_key.split(":")
                win_name = parts[2] if len(parts) > 2 else window_key
                container.mount(WindowHeader(f"[W:{win_name}]"))
                for pane in filtered:
                    row = PaneRow(pane, idx)
                    container.mount(row)
                    self._pane_rows.append(row)
                    idx += 1
            self._last_pane_key = new_key
        else:
            # Same panes — update labels in-place (no flicker)
            all_panes = []
            for panes in snap.by_window().values():
                all_panes.extend(p for p in panes if "NETWATCH" not in p.pane_id)
            for i, (row, pane) in enumerate(zip(self._pane_rows, all_panes, strict=False)):
                row.refresh_from(pane, i + 1)

        if self._pane_rows:
            self._focus_index = min(self._focus_index, len(self._pane_rows) - 1)
            if not any(r.has_focus for r in self._pane_rows):
                self._pane_rows[self._focus_index].focus()

        self._update_status_bar(len(snap.panes), len(snap.agents()))

    _last_status_text: str = ""

    def _update_status_bar(self, pane_count: int, agent_count: int) -> None:
        text = (
            f"─ {pane_count} panes │ {agent_count} agents"
            if self._daemon_online
            else "─ daemon offline"
        )
        if text != self._last_status_text:
            self.query_one("#status-bar", Static).update(text)
            self._last_status_text = text

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
