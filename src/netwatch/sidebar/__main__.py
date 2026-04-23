"""Persistent tmux sidebar — raw ANSI renderer, no Textual.

Connects to the netwatchd socket, renders pane list with ANSI escapes,
redraws only when state changes. Click-to-jump handled at tmux level.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from netwatch.common.paths import socket_path
from netwatch.daemon.state import AgentStatus, PaneState, SessionSnapshot

# ── Netrunner palette ─────────────────────────────────────
CYAN = "\033[38;2;0;255;247m"
GREEN = "\033[38;2;0;255;102m"
DIM = "\033[38;2;45;110;87m"
DIM2 = "\033[38;2;150;233;218m"
YEL = "\033[38;2;255;214;0m"
RED = "\033[38;2;255;80;100m"
BOLD = "\033[1m"
RESET = "\033[0m"
BG_WARN = "\033[48;2;30;30;0m"

SELF_PANE_ID = os.environ.get("TMUX_PANE", "")
HOME = str(Path.home())
MAP_FILE = Path("/tmp/netwatch-sidebar-map.txt")
PANE_TITLE = "NETWATCH"


def _get_netwatch_pane_ids() -> set[str]:
    """Ask tmux which panes have title NETWATCH."""
    try:
        out = subprocess.check_output(
            ["tmux", "list-panes", "-a", "-F", "#{pane_id}\t#{pane_title}"],
            text=True,
            timeout=2,
        )
        return {
            line.split("\t")[0]
            for line in out.strip().split("\n")
            if "\t" in line and line.split("\t")[1] == PANE_TITLE
        }
    except Exception:
        return set()


def _shorten_path(p: str, maxlen: int = 22) -> str:
    p = p.replace(HOME, "~")
    parts = p.split("/")
    if len(parts) > 2:
        short = "/".join(parts[-2:])
        if len(short) <= maxlen:
            return short
    if len(p) > maxlen:
        p = "…" + p[-(maxlen - 1) :]
    return p


def _render_pane(pane: PaneState, idx: int, width: int) -> list[str]:
    """Render one pane as 1-3 lines: main row + optional branch + optional alert."""
    lines = []

    # ── Main row: number, status icon, command, path ──
    if pane.is_agent:
        match pane.agent_status:
            case AgentStatus.THINKING | AgentStatus.TOOL_USE:
                icon = f"{GREEN}⚡{RESET}"
                cmd_col = GREEN
            case AgentStatus.ERROR:
                icon = f"{RED}✗{RESET}"
                cmd_col = RED
            case AgentStatus.WAITING:
                icon = f"{YEL}⏳{RESET}"
                cmd_col = YEL
            case _:
                icon = f"{CYAN}◆{RESET}"
                cmd_col = CYAN
    else:
        icon = " "
        cmd_col = DIM2

    short = _shorten_path(pane.cwd)
    lines.append(f" {YEL}{idx:2d}{DIM}│{icon} {cmd_col}{pane.command:<7s} {DIM2}{short}{RESET}")

    # ── Branch line (if in a git repo) ──
    if pane.branch:
        wt_flag = f" {DIM}[wt]{RESET}" if pane.is_worktree else ""
        branch_display = pane.branch
        max_branch = width - 10
        if len(branch_display) > max_branch:
            branch_display = "…" + branch_display[-(max_branch - 1) :]
        lines.append(f"    {DIM}  {branch_display}{wt_flag}{RESET}")

    # ── Waiting alert (agent needs attention) ──
    if pane.is_agent and pane.agent_status == AgentStatus.WAITING:
        lines.append(f"    {BG_WARN}{YEL} NEEDS INPUT{RESET}")

    return lines


def render(snap: SessionSnapshot, width: int = 32) -> tuple[str, str]:
    """Render sidebar. Returns (screen_content, map_content)."""
    hidden = _get_netwatch_pane_ids()
    out: list[str] = []
    map_lines: list[str] = []

    # ── Header ──
    out.append(f"{CYAN}{BOLD} \U000f06a9 NETWATCH{RESET}")
    sep = "─" * (width - 1)
    out.append(f"{CYAN}{sep}{RESET}")

    # ── Count waiting agents for header alert ──
    waiting = [
        p
        for p in snap.panes.values()
        if p.is_agent and p.agent_status == AgentStatus.WAITING and p.pane_id not in hidden
    ]
    if waiting:
        out.append(f" {BG_WARN}{YEL}{BOLD} {len(waiting)} agent(s) waiting{RESET}")
    active = [
        p
        for p in snap.panes.values()
        if p.is_agent
        and p.agent_status in (AgentStatus.THINKING, AgentStatus.TOOL_USE)
        and p.pane_id not in hidden
    ]
    if active:
        tools = [p.agent_tool or "working" for p in active]
        out.append(f" {GREEN}⚡ {len(active)} active: {', '.join(tools)}{RESET}")

    # ── Pane list grouped by window ──
    idx = 1
    row = len(out)
    for window_key, panes in snap.by_window().items():
        filtered = [p for p in panes if p.pane_id not in hidden]
        if not filtered:
            continue

        parts = window_key.split(":")
        win_name = parts[2] if len(parts) > 2 else window_key
        out.append("")
        out.append(f" {DIM}━━ {CYAN}{win_name}{RESET}")
        row += 2

        for pane in filtered:
            pane_lines = _render_pane(pane, idx, width)
            out.extend(pane_lines)
            map_lines.append(
                f"{row}|{pane.pane_id}|{pane.session_name}:{pane.window_index}.{pane.pane_index}"
            )
            idx += 1
            row += len(pane_lines)

    # ── Footer ──
    agents = snap.agents()
    n_active = sum(
        1 for a in agents if a.agent_status in (AgentStatus.THINKING, AgentStatus.TOOL_USE)
    )
    n_idle = sum(1 for a in agents if a.agent_status in (AgentStatus.IDLE, AgentStatus.UNKNOWN))
    n_wait = len(waiting)
    out.append("")
    out.append(f" {DIM}{sep}{RESET}")
    footer_parts = []
    if n_active:
        footer_parts.append(f"{GREEN}{n_active}⚡{RESET}")
    if n_wait:
        footer_parts.append(f"{YEL}{n_wait}⏳{RESET}")
    if n_idle:
        footer_parts.append(f"{DIM}{n_idle}◆{RESET}")
    agent_str = " ".join(footer_parts) if footer_parts else f"{DIM}no agents{RESET}"
    out.append(f" {agent_str}  {DIM}│ {len(snap.panes)} panes{RESET}")

    return "\n".join(out), "\n".join(map_lines)


def render_offline(width: int = 32) -> str:
    sep = "─" * (width - 1)
    return "\n".join(
        [
            f"{CYAN}{BOLD} \U000f06a9 NETWATCH{RESET}",
            f"{CYAN}{sep}{RESET}",
            "",
            f" {YEL}  daemon offline{RESET}",
            f" {DIM}  netwatch daemon start{RESET}",
        ]
    )


def snap_fingerprint(snap: SessionSnapshot) -> str:
    parts = []
    for pid in sorted(snap.panes):
        p = snap.panes[pid]
        parts.append(f"{pid}:{p.command}:{p.cwd}:{p.agent_status}:{p.branch}:{p.is_worktree}")
    return "|".join(parts)


async def run() -> None:
    if SELF_PANE_ID:
        os.system(f"tmux select-pane -t {SELF_PANE_ID} -T {PANE_TITLE}")

    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()

    def cleanup(*_: object) -> None:
        sys.stdout.write("\033[?1049l\033[?25h")
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
