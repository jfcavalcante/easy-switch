"""Windows keyboard watcher using WMI polling.

Detects connection state changes of the Aula75 keyboard via
Win32_PnPEntity.ConnectionState. When the keyboard switches hosts,
its ConnectionState drops from 1 (Connected) to 3 (Disconnected).

This is preferred over SetupAPI because Bluetooth device host
switches do not trigger physical removal events.
"""

from __future__ import annotations

import asyncio
import logging
import time

from .events import (
    HidrawWriter,
    KeyboardSwitchEvent,
    KeyboardWatcher,
    SwitchDirection,
)
from .hidpp import build_change_host_write_request

logger = logging.getLogger("kvmsync.events_windows")

# Aula75 keyboard VID/PID (Bluetooth and 2.4G modes).
KEYBOARD_VENDOR_ID = "3554"
KEYBOARD_PRODUCT_IDS = ("FA07", "FA09")

# Logitech mouse VID only; we match by first device found.
MOUSE_VENDOR_ID = 0x046D


class WindowsKeyboardWatcher(KeyboardWatcher):
    """Monitor Windows WMI for keyboard connection state changes.

    Polls Win32_PnPEntity every *check_interval_s* seconds looking for
    the Aula75 keyboard by VID/PID.  The *ConnectionState* property is:
    1 = Connected, 3 = Disconnected.
    """

    # KeyboardWatcher abstract API uses KEYBOARD_MAC; we leave it blank
    # because the Windows watcher identifies the keyboard by USB VID/PID.
    KEYBOARD_MAC: str = ""

    def __init__(
        self,
        linux_slot: int = 0,
        windows_slot: int = 1,
        hidraw: HidrawWriter | None = None,
        check_interval_s: float = 1.0,
    ) -> None:
        self.linux_slot = linux_slot
        self.windows_slot = windows_slot
        self.hidraw = hidraw
        self.check_interval_s = check_interval_s
        self._callbacks: list = []
        self._running = False
        self._last_connected: bool = True
        self._last_change_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_switch(self, callback: callable) -> None:
        """Register a callback for keyboard switch events.

        The callback may be sync or async (coroutine).
        """
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start polling WMI for keyboard connection state."""
        self._running = True
        self._last_change_time = 0.0
        logger.info("Starting Windows keyboard watcher …")
        logger.info(
            "Polling Win32_PnPEntity every %.1fs …", self.check_interval_s
        )

        self._last_connected = WindowsKeyboardWatcher._is_keyboard_connected()
        logger.info(
            "Initial keyboard state: connected=%s", self._last_connected
        )

        while self._running:
            await asyncio.sleep(self.check_interval_s)
            self._check_state()

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        logger.info("Windows keyboard watcher stopped.")

    def get_host_for_slot(self, slot: int) -> str:
        """Return the OS name for a given host slot index."""
        if slot == self.linux_slot:
            return "linux"
        if slot == self.windows_slot:
            return "windows"
        return f"slot-{slot}"

    # ------------------------------------------------------------------
    # WMI polling
    # ------------------------------------------------------------------

    @staticmethod
    def _is_keyboard_connected() -> bool:
        """Check if the Aula75 keyboard is currently connected.

        Returns True when ConnectionState == 1 (Connected).
        Returns False when the device is not found or ConnectionState == 3.
        """
        try:
            import wmi
        except ImportError:
            logger.error(
                "pywmi not installed. Cannot poll WMI. "
                "Install with: pip install wmi"
            )
            return True  # assume connected to avoid false triggers

        try:
            c = wmi.WMI()
            devices = c.Win32_PnPEntity()
        except Exception:
            logger.exception("Failed to query WMI")
            return True

        for device in devices:
            caption = getattr(device, "Caption", "") or ""
            if KEYBOARD_VENDOR_ID not in caption.upper():
                continue
            if not any(
                pid in caption.upper() for pid in KEYBOARD_PRODUCT_IDS
            ):
                continue
            # ConnectionState: 1=Connected, 3=Disconnected
            state = getattr(device, "ConnectionState", 3)
            logger.debug(
                "Found keyboard device, ConnectionState=%s", state
            )
            return state == 1

        logger.debug("Aula75 keyboard not found in WMI")
        return False

    def _check_state(self) -> None:
        """Compare current connection state with the last known state and
        emit a switch event when they differ, with a 3-second debounce.
        """
        now = time.monotonic()
        current = WindowsKeyboardWatcher._is_keyboard_connected()
        diff = now - self._last_change_time

        if current != self._last_connected and diff > 3.0:
            if current:
                # Keyboard reconnected → switched TO this machine.
                logger.info("Keyboard connected (detected via WMI).")
                self._emit(SwitchDirection.WINDOWS_TO_LINUX)
            else:
                # Keyboard disconnected → switched FROM this machine.
                logger.info("Keyboard disconnected (detected via WMI).")
                self._emit(SwitchDirection.LINUX_TO_WINDOWS)

            self._last_connected = current
            self._last_change_time = now

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    def _emit(self, direction: SwitchDirection) -> None:
        """Emit a switch event and send CHANGE_HOST to the mouse."""
        ts = time.monotonic()
        event = KeyboardSwitchEvent(
            direction=direction,
            timestamp=ts,
        )

        target_slot = (
            self.linux_slot
            if direction == SwitchDirection.WINDOWS_TO_LINUX
            else self.windows_slot
        )
        host_name = self.get_host_for_slot(target_slot)

        logger.info(
            "Keyboard switched to %s (slot %d).", host_name, target_slot
        )
        self._send_change_host(target_slot, event)

        for cb in self._callbacks:
            if asyncio.iscoroutinefunction(cb):
                asyncio.ensure_future(cb(event))
            else:
                cb(event)

    def _send_change_host(self, slot: int, event: KeyboardSwitchEvent) -> None:
        """Send CHANGE_HOST HID++ command to the Logitech mouse via hidapi."""
        try:
            import hid

            cmd = build_change_host_write_request(slot)
            found = False
            for dev in hid.enumerate(MOUSE_VENDOR_ID, 0):
                usage_page = dev.get("usage_page", 0)
                if usage_page == 1:  # HID Generic Desktop
                    path = dev["path"]
                    h = hid.Device(path=path)
                    try:
                        h.write(bytes(cmd))
                        logger.info(
                            "CHANGE_HOST sent successfully (slot %d).", slot
                        )
                    finally:
                        h.close()
                    found = True
                    break

            if not found:
                logger.error("Logitech mouse (usage=Keyboard) not found.")
        except Exception:
            logger.exception("Failed to send CHANGE_HOST")
