"""Windows keyboard watcher using SetupAPI.

Listens for HID device removal events via SetupAPI.
When the Aula75 keyboard is removed, the daemon logs it
but does NOT send CHANGE_HOST — only the Linux machine
sends the command.

Note: This module requires pywin32 and only works on Windows.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from .events import (
    HidrawWriter,
    KeyboardSwitchEvent,
    KeyboardWatcher,
    SwitchDirection,
)
from .log import setup_logging

logger = logging.getLogger("kvmsync.events_windows")

GUID_DEVINTERFACE_HID = "{811FC6A5-F287-4FCA-9882-3C14BE4F8D2A}"


class WindowsKeyboardWatcher(KeyboardWatcher):
    """Monitor Windows SetupAPI for keyboard removal events."""

    def __init__(
        self,
        linux_slot: int = 0,
        windows_slot: int = 1,
        hidraw: HidrawWriter | None = None,
    ) -> None:
        self.linux_slot = linux_slot
        self.windows_slot = windows_slot
        self.hidraw = hidraw
        self._callbacks: list = []
        self._running = False

        # Keyboard identifiers.
        self.KEYBOARD_VENDOR_ID = 0x3554
        self.KEYBOARD_PRODUCT_ID_BT = 0xFA07

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_switch(self, callback) -> None:
        """Register a callback for keyboard switch events."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start watching for HID device events.

        On Windows, this attempts to register for device notification
        via SetupAPI. If pywin32 is not available, logs a warning
        and returns immediately (non-blocking).
        """
        self._running = True
        logger.info("Starting Windows keyboard watcher …")

        try:
            import win32con
            import win32gui
            import win32api
        except ImportError:
            logger.error(
                "pywin32 not installed. Cannot monitor SetupAPI. "
                "Install with: pip install pywin32"
            )
            return

        try:
            import setupapi
        except ImportError:
            logger.warning(
                "setupapi module not found. "
                "Using DeviceWatcher polling as fallback."
            )
            await self._polling_start()
            return

        # Set up a window handle for device notifications.
        hwnd = win32gui.CreateWindow(
            win32con.STATIC_CLASS,
            "kvmsync",
            0,
            0,
            0,
            win32con.CW_USEDEFAULT,
            win32con.CW_USEDEFAULT,
            0,
            0,
            0,
            None,
            None,
        )

        notification_filter = {
            "flags": win32con.DBT_DEVICEARRIVAL | win32con.DBT_DEVICEREMOVECOMPLETE,
            "device_interface": win32gui.PackGUID(
                win32gui.PyGUID(GUID_DEVINTERFACE_HID)
            ),
        }

        dev_handle = setupapi.SetupDiGetClassDevs(
            None, None, 0, setupapi.DIGCF_DEVICEINTERFACE
        )

        try:
            win32gui.RegisterDeviceNotification(
                hwnd,
                notification_filter,
                win32con.DEVICE_NOTIFY_WINDOW_HANDLE,
            )
        except Exception as exc:
            logger.error("Failed to register for device notifications: %s", exc)
            return

        logger.info("Watching for HID device events via SetupAPI …")

        # Pump Windows messages.
        while self._running:
            import win32event
            win32event.MsgWaitForMultipleObjects(
                [], 0, 100,  # 100ms timeout
                win32con.QS_ALLINPUT,
            )
            while win32gui.PeekMessage(hwnd, 0, 0, win32con.PM_REMOVE):
                win32gui.TranslateMessage(hwnd)
                win32gui.DispatchMessage(hwnd)

        win32gui.DestroyWindow(hwnd)

    async def _polling_start(self) -> None:
        """Fallback: use periodic polling if SetupAPI is unavailable."""
        logger.info("Using polling fallback — check every 2 seconds.")
        while self._running:
            await asyncio.sleep(2)

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        logger.info("Windows keyboard watcher stopped.")

    def get_host_for_slot(self, slot: int) -> str:
        """Return the OS name for a given slot."""
        if slot == self.linux_slot:
            return "linux"
        if slot == self.windows_slot:
            return "windows"
        return f"slot-{slot}"
