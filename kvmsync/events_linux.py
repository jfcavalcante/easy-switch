"""Linux keyboard watcher using BlueZ D-Bus.

Polls ``org.bluez.Device1.Connected`` of the Aula75 keyboard. BlueZ
flips it within ~1s when the keyboard switches hosts (verified E2E with
fn+2 / fn+1).

Polling is used instead of ``PropertiesChanged`` signals because
dbus-python only delivers signals through a GLib main loop, which does
not mix with the asyncio daemon.

The debounce / switch logic lives in :mod:`kvmsync.presence`.
"""

from __future__ import annotations

from typing import Callable

from .presence import PresenceWatcher

# D-Bus object path of the Aula75 keyboard.
KEYBOARD_PATH = "/org/bluez/hci0/dev_E3_34_CC_0D_A4_0F"


def _make_bluez_probe() -> Callable[[], bool]:
    """Return a function reading the keyboard's BlueZ Connected property."""
    import dbus

    props = dbus.Interface(
        dbus.SystemBus().get_object("org.bluez", KEYBOARD_PATH),
        "org.freedesktop.DBus.Properties",
    )

    def is_present() -> bool:
        return bool(props.Get("org.bluez.Device1", "Connected", timeout=2))

    return is_present


class LinuxKeyboardWatcher(PresenceWatcher):
    """Poll BlueZ for the keyboard and follow it with the mouse."""

    local_host = "linux"

    def __init__(
        self,
        is_present: Callable[[], bool] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(is_present or _make_bluez_probe(), **kwargs)
