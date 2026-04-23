"""Textual HUD app — the persistent sidebar that replaces the bash NETWATCH."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
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


def _snap_fingerprint(snap: SessionSnapshot) -> str:
    """Full content fingerprint — pane IDs + statuses + cwds."""
    parts = []
    for pid in sorted(snap.panes):
        p = snap.panes[pid]
        parts.append(f"{pid}:{p.command}:{p.cwd}:{p.agent_status}")
    return "|".join(parts)


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
        """Update in-place — no-op if unchanged."""
        self.target_pane_id = pane.pane_id
        label, cls = _format_row(pane, index)
        if str(self.renderable) != label:
            self.update(label)
        current_classes = self.classes & _STATUS_CLASSES
        wanted = {cls} if cls else set()
        if current_classes != wanted:
            for old in current_classes - wanted:
                self.remove_class(old)
            for new in wanted - current_classes:
                self.add_class(new)

    def _do_jump(self) -> None:
        try:
            import libtmux

            server = libtmux.Server()
            for session in server.sessions:
                for window in session.windows:
                    for pane in window.panes:
                        if pane.pane_id == self.target_pane_id:
                            window.select()
                            pane.select()
                            return
        except Exception:
            pass

    def on_click(self) -> None:
        self._do_jump()

    def action_select(self) -> None:
        self._do_jump()


class WindowHeader(Static):
    DEFAULT_CSS = "WindowHeader { color: #2D6E57; padding: 1 0 0 1; height: auto; }"


class OfflineBanner(Static):
    DEFAULT_CSS = (
        "OfflineBanner { height: auto; padding: 1 2; color: #FFD600; text-style: italic; }"
    )

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

    def __init__(self) -> None:
        super().__init__()
        self._daemon_online: bool = False
        self._pane_rows: list[PaneRow] = []
        self._focus_index: int = 0
        self._last_fingerprint: str = ""
        self._last_status_text: str = ""
        self._showing_offline: bool = False

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
            snap = SessionSnapshot.model_validate(data)
            self._daemon_online = True
        except OSError:
            self._daemon_online = False
            snap = None
        except Exception:
            return

        self._apply_state(snap)

    def _apply_state(self, snap: SessionSnapshot | None) -> None:
        container = self.query_one("#pane-list", ScrollableContainer)

        # Offline
        if not self._daemon_online or snap is None:
            if not self._showing_offline:
                container.remove_children()
                self._pane_rows = []
                container.mount(OfflineBanner())
                self._showing_offline = True
                self._last_fingerprint = ""
            self._set_status("─ daemon offline")
            return

        # Back online after offline
        if self._showing_offline:
            for banner in self.query(OfflineBanner):
                banner.remove()
            self._showing_offline = False

        # Fingerprint everything — if identical, do absolutely nothing
        fp = _snap_fingerprint(snap)
        if fp == self._last_fingerprint:
            return
        self._last_fingerprint = fp

        # Check if pane SET changed (structural) or just content
        pane_ids = sorted(snap.panes.keys())
        existing_ids = [r.target_pane_id for r in self._pane_rows]
        structural = pane_ids != sorted(existing_ids)

        if structural:
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
        else:
            all_panes = []
            for panes in snap.by_window().values():
                all_panes.extend(p for p in panes if "NETWATCH" not in p.pane_id)
            for i, (row, pane) in enumerate(zip(self._pane_rows, all_panes, strict=False)):
                row.refresh_from(pane, i + 1)

        if self._pane_rows:
            self._focus_index = min(self._focus_index, len(self._pane_rows) - 1)
            if not any(r.has_focus for r in self._pane_rows):
                self._pane_rows[self._focus_index].focus()

        n_panes = len(snap.panes)
        n_agents = len(snap.agents())
        self._set_status(f"─ {n_panes} panes │ {n_agents} agents")

    def _set_status(self, text: str) -> None:
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
