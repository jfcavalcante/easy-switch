"""Windows keyboard watcher using hidapi polling.

Detects the Aula75 keyboard leaving / arriving by checking whether its
HID interfaces are enumerated (``hid.enumerate(0x3554, 0xFA07)``). When
the keyboard switches to another host, Windows drops all of its HID
collections within ~1s; they come back when it switches back.

WMI / PnP was tried before and is unreliable here: the BTHLE
"connected" property lags several seconds and SetupAPI never fires
removal events for a Bluetooth host switch.

The debounce / switch logic lives in :mod:`kvmsync.presence`.
"""

from __future__ import annotations

from typing import Callable

from .presence import PresenceWatcher

# Aula75 keyboard VID/PID over Bluetooth LE.
KEYBOARD_VENDOR_ID = 0x3554
KEYBOARD_PRODUCT_ID = 0xFA07


def _keyboard_present() -> bool:
    import hid

    return bool(hid.enumerate(KEYBOARD_VENDOR_ID, KEYBOARD_PRODUCT_ID))


class WindowsKeyboardWatcher(PresenceWatcher):
    """Poll hidapi for the keyboard and follow it with the mouse."""

    local_host = "windows"

    def __init__(
        self,
        is_present: Callable[[], bool] = _keyboard_present,
        **kwargs,
    ) -> None:
        super().__init__(is_present, **kwargs)
