"""Persistent tmux sidebar — raw ANSI renderer, no Textual.

Connects to the netwatchd socket, renders pane list with ANSI escapes,
redraws only when state changes. Designed to run inside a tmux pane
split off the left side of every window.

Click-to-jump is handled at the tmux level (DoubleClick1Pane binding),
not by this script — tmux mouse events don't pass through reliably
to applications in nested panes.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from netwatch.common.paths import socket_path
from netwatch.daemon.state import AgentStatus, SessionSnapshot

# Netrunner palette
CYAN = "\033[38;2;0;255;247m"
GREEN = "\033[38;2;0;255;102m"
DIM = "\033[38;2;45;110;87m"
DIM2 = "\033[38;2;150;233;218m"
YEL = "\033[38;2;255;214;0m"
RED = "\033[38;2;255;80;100m"
BOLD = "\033[1m"
RESET = "\033[0m"

STATUS_ICONS = {
    AgentStatus.THINKING: f"{GREEN}⚡{RESET}",
    AgentStatus.TOOL_USE: f"{GREEN}⚡{RESET}",
    AgentStatus.IDLE: f"{DIM}◆{RESET}",
    AgentStatus.WAITING: f"{DIM}◆{RESET}",
    AgentStatus.ERROR: f"{RED}✗{RESET}",
    AgentStatus.UNKNOWN: " ",
}

STATUS_COLORS = {
    AgentStatus.THINKING: GREEN,
    AgentStatus.TOOL_USE: GREEN,
    AgentStatus.ERROR: RED,
}

SELF_PANE_ID = os.environ.get("TMUX_PANE", "")
HOME = str(Path.home())
MAP_FILE = Path("/tmp/netwatch-sidebar-map.txt")


def shorten_path(p: str, maxlen: int = 20) -> str:
    p = p.replace(HOME, "~")
    if len(p) > maxlen:
        p = "…" + p[-(maxlen - 1) :]
    return p


def render(snap: SessionSnapshot, width: int = 32) -> tuple[str, str]:
    """Render the sidebar content. Returns (screen_content, map_content)."""
    lines: list[str] = []
    map_lines: list[str] = []

    # Header
    lines.append(f"{CYAN}{BOLD} \U000f06a9 NETWATCH{RESET}")
    lines.append(f"{CYAN}{'─' * (width - 1)}{RESET}")

    idx = 1
    row = 2
    for window_key, panes in snap.by_window().items():
        filtered = [
            p for p in panes if p.pane_id != SELF_PANE_ID and "netwatch" not in p.command.lower()
        ]
        if not filtered:
            continue

        parts = window_key.split(":")
        win_name = parts[2] if len(parts) > 2 else window_key
        lines.append("")
        lines.append(f"{DIM}[W:{win_name}]{RESET}")
        row += 2

        for pane in filtered:
            icon = STATUS_ICONS.get(pane.agent_status, " ") if pane.is_agent else " "
            col = STATUS_COLORS.get(pane.agent_status, DIM2) if pane.is_agent else DIM2
            short = shorten_path(pane.cwd)
            lines.append(f"{YEL}{idx:2d}{DIM}│ {icon} {col}{pane.command:<8s}{DIM2}{short}{RESET}")
            map_lines.append(
                f"{row}|{pane.pane_id}|{pane.session_name}:{pane.window_index}.{pane.pane_index}"
            )
            idx += 1
            row += 1

    # Footer
    n_agents = len(snap.agents())
    n_panes = len(snap.panes)
    lines.append("")
    lines.append(f"{DIM}─ {n_panes} panes │ {n_agents} agents{RESET}")

    return "\n".join(lines), "\n".join(map_lines)


def render_offline(width: int = 32) -> str:
    lines = [
        f"{CYAN}{BOLD} \U000f06a9 NETWATCH{RESET}",
        f"{CYAN}{'─' * (width - 1)}{RESET}",
        "",
        f"{YEL}  daemon offline{RESET}",
        f"{DIM}  run: netwatch daemon start{RESET}",
    ]
    return "\n".join(lines)


def snap_fingerprint(snap: SessionSnapshot) -> str:
    parts = []
    for pid in sorted(snap.panes):
        p = snap.panes[pid]
        parts.append(f"{pid}:{p.command}:{p.cwd}:{p.agent_status}")
    return "|".join(parts)


async def run() -> None:
    # Alt screen + hide cursor
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()

    def cleanup(*_: object) -> None:
        sys.stdout.write("\033[?1049l\033[?25l")
        sys.stdout.flush()
        MAP_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    last_fp = ""

    while True:
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path()))
            writer.write((json.dumps({"cmd": "GET_STATE"}) + "\n").encode())
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
            writer.close()
            await writer.wait_closed()

            raw = json.loads(line)
            data = raw.get("data", {})
            snap = SessionSnapshot.model_validate(data)

            fp = snap_fingerprint(snap)
            if fp != last_fp:
                content, map_content = render(snap)
                sys.stdout.write("\033[H\033[2J")
                sys.stdout.write(content)
                sys.stdout.flush()
                MAP_FILE.write_text(map_content)
                last_fp = fp

        except (OSError, TimeoutError):
            if last_fp != "__offline__":
                sys.stdout.write("\033[H\033[2J")
                sys.stdout.write(render_offline())
                sys.stdout.flush()
                last_fp = "__offline__"
        except Exception:
            pass

        await asyncio.sleep(2.0)


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        sys.stdout.write("\033[?1049l\033[?25h")
        sys.stdout.flush()
        MAP_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
