"""Entry point for ``python -m kvmsync``."""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .daemon import Daemon


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kvmsync",
        description="Synchronize Bluetooth host switching between keyboard and mouse",
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to configuration file (default: auto-detect)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print verbose debug logs",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List paired Bluetooth devices and exit",
    )
    args = parser.parse_args()

    # Quick device listing (Linux only).
    if args.list_devices:
        _list_devices_linux()
        return

    # Load configuration.
    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Apply --verbose flag on top of config.
    if args.verbose:
        config.daemon.verbose = True

    # Run the daemon.
    daemon = Daemon(config)

    import asyncio
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        pass


def _list_devices_linux() -> None:
    """List paired Bluetooth devices (Linux only)."""
    try:
        import dbus
    except ImportError:
        print("dbus-python not installed.", file=sys.stderr)
        return

    bus = dbus.SystemBus()
    obj = bus.get_object("org.bluez", "/")
    mgr = dbus.Interface(obj, "org.freedesktop.DBus.ObjectManager")

    for path, interfaces in mgr.GetManagedObjects().items():
        for iface, props in interfaces.items():
            if "Device" in iface:
                alias = props.get("Alias", "?")
                addr = props.get("Address", "?")
                connected = props.get("Connected", False)
                icon = props.get("Icon", "?")
                state = "ONLINE" if connected else "offline"
                print(f"  {addr:17s}  {alias:30s}  {state:7s}  {icon}")


if __name__ == "__main__":
    main()
