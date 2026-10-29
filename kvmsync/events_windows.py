"""Windows keyboard watcher using SetupAPI.

Listens for HID device removal events via SetupAPI.
When the Aula75 keyboard is removed, the daemon logs it
but does NOT send CHANGE_HOST — only the Linux machine
sends the command.
"""

from __future__ import annotations

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

# GUID for HID device interface (Windows).
GUID_DEVINTERFACE_HID = "{811FC6A5-F287-4FCA-9882-3C14BE4F8D2A}"


@dataclass
class WindowsKeyboardWatcher(KeyboardWatcher):
    """Monitor Windows SetupAPI for keyboard removal events."""

    linux_slot: int = 0
    windows_slot: int = 1
    hidraw: HidrawWriter | None = None
    _callbacks: list = None  # type: ignore[assignment]
    _running: bool = False

    # Keyboard identifier — matches the Aula75 VID/PID.
    KEYBOARD_VENDOR_ID: int = 0x3554
    KEYBOARD_PRODUCT_ID_2_4G: int = 0xFA09
    KEYBOARD_PRODUCT_ID_BT: int = 0xFA07

    def __post_init__(self) -> None:
        if self._callbacks is None:
            self._callbacks: list = []
        setup_logging(self.verbose if hasattr(self, "verbose") else False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_switch(self, callback):
        """Register a callback for keyboard switch events."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start watching for HID device events."""
        self._running = True
        logger.info("Starting Windows keyboard watcher …")

        try:
            import win32con
            import win32gui
            import win32api
            import setupapi
        except ImportError:
            logger.error(
                "pywin32 not installed. Cannot monitor SetupAPI. "
                "Install with: pip install pywin32"
            )
            return

        # Set up a window handle for device notifications.
        class _DummyWindow:
            def __init__(self):
                self.hwnd = win32gui.CreateWindow(
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

            def run(self):
                win32gui.PumpMessages()

        _win = _DummyWindow()

        # Register for HID device notifications.
        notification_filter = {
            "flags": win32con.DBT_DEVICEARRIVAL | win32con.DBT_DEVICEREMOVECOMPLETE,
            "device_interface": win32gui.PackGUID(
                win32gui.PyGUID(GUID_DEVINTERFACE_HID)
            ),
        }

        try:
            dev_handle = setupapi.SetupDiGetClassDevs(
                None,
                None,
                0,
                setupapi.DIGCF_DEVICEINTERFACE,
            )
            win32gui.RegisterDeviceNotification(
                _win.hwnd,
                notification_filter,
                win32con.DEVICE_NOTIFY_WINDOW_HANDLE,
            )
        except Exception as exc:
            logger.error("SetupAPI initialization failed: %s", exc)
            return

        logger.info("Watching for HID device events …")

        # Pump Windows messages.
        while self._running:
            # Process pending messages (will trigger callbacks).
            win32api.WaitMessage()
            import win32event
            win32event.MsgWaitForMultipleObjects(
                [], 0, 100,  # 100ms timeout
                win32con.QS_ALLINPUT,
            )
            while win32gui.PeekMessage(_win.hwnd, 0, 0, win32con.PM_REMOVE):
                win32gui.TranslateMessage(_win.hwnd)
                win32gui.DispatchMessage(_win.hwnd)

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

    # ------------------------------------------------------------------
    # Callbacks (called from the message loop)
    # ------------------------------------------------------------------

    def _on_device_change(self, msg):
        """Handle device arrival/removal events."""
        event_type = msg.wParam
        if event_type == win32con.DBT_DEVICEREMOVECOMPLETE:
            logger.info("Keyboard device removed — switching detected.")
            # We do NOT send CHANGE_HOST on Windows.
            # Only the Linux machine sends the command.
            ts = time.monotonic()
            event = KeyboardSwitchEvent(
                direction=SwitchDirection.LINUX_TO_WINDOWS,
                old_connected=True,
                timestamp=ts,
            )
            for cb in self._callbacks:
                cb(event)
        elif event_type == win32con.DBT_DEVICEARRIVAL:
            logger.info("New HID device detected.")
