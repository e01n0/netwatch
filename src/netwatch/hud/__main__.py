"""Entrypoint for `netwatch-hud` — launches the Textual sidebar app."""

from __future__ import annotations


def main() -> None:
    from netwatch.hud.app import NetwatchApp

    app = NetwatchApp()
    app.run()


if __name__ == "__main__":
    main()
