"""Canonical paths for netwatch runtime, config, logs, and Claude data."""

from __future__ import annotations

import os
from pathlib import Path


def xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def xdg_runtime_dir() -> Path:
    d = os.environ.get("XDG_RUNTIME_DIR")
    if d:
        return Path(d)
    return Path(os.environ.get("TMPDIR", "/tmp"))


def config_dir() -> Path:
    return xdg_config_home() / "netwatch"


def config_file() -> Path:
    return config_dir() / "config.toml"


def install_manifest() -> Path:
    return config_dir() / "install-manifest.json"


def pid_file() -> Path:
    return xdg_runtime_dir() / "netwatch" / "netwatchd.pid"


def port_file() -> Path:
    return config_dir() / "port"


def socket_path() -> Path:
    return xdg_runtime_dir() / "netwatch" / "netwatch.sock"


def log_dir() -> Path:
    return config_dir() / "logs"


def log_file() -> Path:
    return log_dir() / "netwatchd.log"


def claude_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def claude_settings_file() -> Path:
    return Path.home() / ".claude" / "settings.json"
