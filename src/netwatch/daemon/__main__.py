"""netwatchd — the daemon entrypoint. Wires watchers, aggregator, and socket server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys

import structlog

from netwatch.common.paths import log_dir, log_file, pid_file, port_file
from netwatch.daemon.aggregator import Aggregator
from netwatch.daemon.hook_receiver import HookReceiver
from netwatch.daemon.jsonl_watcher import JsonlWatcher
from netwatch.daemon.socket_server import SocketServer
from netwatch.daemon.tmux_watcher import TmuxWatcher

logger = structlog.get_logger()


def write_pid() -> None:
    pf = pid_file()
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(str(os.getpid()))


def write_port(port: int) -> None:
    pf = port_file()
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(str(port))


def cleanup() -> None:
    for f in [pid_file(), port_file()]:
        with contextlib.suppress(OSError):
            f.unlink(missing_ok=True)


async def event_loop(
    queue: asyncio.Queue, aggregator: Aggregator, socket_srv: SocketServer
) -> None:
    while True:
        event_type, data = await queue.get()
        changed = False

        match event_type:
            case "tmux_snapshot":
                changed = aggregator.apply_tmux_snapshot(data)
            case "jsonl_update":
                changed = aggregator.apply_jsonl_update(data["cwd"], data["status"], data["tool"])
            case "hook_event":
                changed = aggregator.apply_hook_event(
                    data["session_id"], data["status"], data["tool"]
                )

        if changed:
            snapshot = aggregator.snapshot()
            await socket_srv.publish(snapshot.to_event())


async def run() -> None:
    log_dir().mkdir(parents=True, exist_ok=True)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(
            file=open(log_file(), "a")  # noqa: SIM115
        ),
    )

    write_pid()
    logger.info("netwatchd starting", pid=os.getpid())

    queue: asyncio.Queue = asyncio.Queue()
    aggregator = Aggregator()
    socket_srv = SocketServer()
    socket_srv.set_state_callback(lambda: aggregator.snapshot().to_event("snapshot"))

    hook_receiver = HookReceiver(queue)
    tmux_watcher = TmuxWatcher(queue)
    jsonl_watcher = JsonlWatcher(queue)

    async def _start_hook_receiver_and_write_port() -> None:
        task = asyncio.create_task(hook_receiver.run())
        # Wait for the port to be assigned
        for _ in range(50):
            if hook_receiver.actual_port is not None:
                break
            await asyncio.sleep(0.1)
        if hook_receiver.actual_port:
            write_port(hook_receiver.actual_port)
            logger.info("hook receiver port written", port=hook_receiver.actual_port)
        await task

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(_shutdown()))

    async def _shutdown() -> None:
        logger.info("netwatchd shutting down")
        cleanup()
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks:
            t.cancel()
        sys.exit(0)

    await asyncio.gather(
        socket_srv.run(),
        _start_hook_receiver_and_write_port(),
        tmux_watcher.run(),
        jsonl_watcher.run(),
        event_loop(queue, aggregator, socket_srv),
    )


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        cleanup()
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
