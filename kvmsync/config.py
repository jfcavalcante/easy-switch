"""Configuration loader for kvmsync."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[import-not-found, unused-ignore]
    except ImportError:
        tomllib = None  # type: ignore[assignment, unused-ignore]


@dataclass(frozen=True)
class HostConfig:
    """Host slot mapping."""

    linux_slot: int
    windows_slot: int


@dataclass(frozen=True)
class MouseConfig:
    """Mouse device identification."""

    vendor_id: int
    product_id: int


@dataclass(frozen=True)
class DaemonConfig:
    """Daemon runtime behaviour."""

    debounce_ms: int = 500
    reconcile_interval_s: int = 5
    verbose: bool = False


@dataclass
class Config:
    """Top-level application configuration."""

    mouse: MouseConfig
    hosts: HostConfig
    daemon: DaemonConfig = field(default_factory=DaemonConfig)


def _load(raw: dict) -> Config:
    """Validate and convert a raw TOML dict into a Config."""

    mouse_raw = raw["mouse"]
    mouse = MouseConfig(
        vendor_id=mouse_raw["vendor_id"],
        product_id=mouse_raw["product_id"],
    )

    hosts_raw = raw["hosts"]
    hosts = HostConfig(
        linux_slot=hosts_raw["linux_slot"],
        windows_slot=hosts_raw["windows_slot"],
    )

    daemon_raw = raw.get("daemon", {})
    daemon = DaemonConfig(
        debounce_ms=int(daemon_raw.get("debounce_ms", 500)),
        reconcile_interval_s=int(daemon_raw.get("reconcile_interval_s", 5)),
        verbose=daemon_raw.get("verbose", False),
    )

    # Validate slot range (0-based: 0, 1, 2)
    for slot_name, slot in (("linux", hosts.linux_slot), ("windows", hosts.windows_slot)):
        if slot not in (0, 1, 2):
            raise ValueError(
                f"hosts.{slot_name}_slot must be 0, 1, or 2, got {slot}"
            )

    if daemon.debounce_ms < 0:
        raise ValueError("daemon.debounce_ms must be >= 0")
    if daemon.reconcile_interval_s < 1:
        raise ValueError("daemon.reconcile_interval_s must be >= 1")

    return Config(mouse=mouse, hosts=hosts, daemon=daemon)


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from a TOML file.

    Search order
    -------------
    1. Explicit *path* if provided.
    2. ``config.toml`` in the current working directory.
    3. ``config.toml`` in the user config directory (~/.config/kvmsync/config.toml).
    """
    if path is not None:
        config_path = Path(path)
    else:
        config_path = Path("config.toml")
        if not config_path.is_file():
            fallback = Path.home() / ".config" / "kvmsync" / "config.toml"
            if fallback.is_file():
                config_path = fallback

    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found. Tried:\n"
            f"  1. {path}\n"
            f"  2. {config_path.resolve()}\n"
            f"\nCopy config.example.toml to config.toml and edit it."
        )

    data = config_path.read_bytes()

    if tomllib is None:
        raise ImportError(
            "tomli is required for Python < 3.11. "
            "Install it with: pip install tomli"
        )

    raw = tomllib.loads(data.decode("utf-8"))
    return _load(raw)
