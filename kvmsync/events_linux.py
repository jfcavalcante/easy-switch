"""Linux keyboard watcher using BlueZ D-Bus.

Listens for ``PropertiesChanged`` signals on
``org.bluez.Device1.Connected`` for the Aula75 keyboard.
When it observes a reconnection (Connected: 0 -> 1), it emits
a ``KeyboardSwitchEvent``.
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
from .hidpp import build_change_host_write_request, send_change_host
from .log import setup_logging

logger = logging.getLogger("kvmsync.events_linux")


# D-Bus object path of the Aula75 keyboard (determined during discovery).
KEYBOARD_PATH = "/org/bluez/hci0/dev_E3_34_CC_0D_A4_0F"
KEYBOARD_ALIAS = "AULA-F75 5.0 KB"
HIDRAW_PATH = "/dev/hidraw4"  # MX Vertical


@dataclass
class LinuxKeyboardWatcher(KeyboardWatcher):
    """Monitor BlueZ for keyboard host switches."""

    linux_slot: int = 0
    windows_slot: int = 1
    debounce_ms: int = 500
    verbose: bool = False
    hidraw: HidrawWriter | None = None
    _last_disconnect_time: float = 0.0
    _is_connected: bool = True
    _running: bool = False
    _callbacks: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._callbacks is None:
            self._callbacks: list = []
        setup_logging(self.verbose)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_switch(self, callback):
        """Register a callback for keyboard switch events."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start watching BlueZ D-Bus for keyboard events."""
        self._running = True
        logger.info("Starting Linux keyboard watcher …")

        # Ensure we can reach BlueZ system bus.
        try:
            import dbus
        except ImportError:
            logger.error("dbus-python not installed. Cannot monitor BlueZ.")
            return

        bus = dbus.SystemBus()
        props_iface = dbus.Interface(
            bus.get_object("org.bluez", KEYBOARD_PATH),
            "org.freedesktop.DBus.Properties",
        )

        # Listen for Connected property changes.
        bus.add_signal_receiver(
            self._on_dbus_signal,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path=KEYBOARD_PATH,
        )

        logger.info(
            "Watching %s for Connected changes (linux_slot=%d, windows_slot=%d)",
            KEYBOARD_PATH,
            self.linux_slot,
            self.windows_slot,
        )

        # Poll the initial state.
        try:
            initial = props_iface.Get("org.bluez.Device1", "Connected")
            self._is_connected = bool(initial)
            logger.info("Initial keyboard state: connected=%s", self._is_connected)
        except Exception as exc:
            logger.warning("Could not read initial Connected state: %s", exc)

        # Keep the event loop running.
        while self._running:
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        logger.info("Linux keyboard watcher stopped.")

    def get_host_for_slot(self, slot: int) -> str:
        """Return the OS name for a given slot."""
        if slot == self.linux_slot:
            return "linux"
        if slot == self.windows_slot:
            return "windows"
        return f"slot-{slot}"

    # ------------------------------------------------------------------
    # D-Bus callback
    # ------------------------------------------------------------------

    def _on_dbus_signal(self, interface, changed, invalidated, path):
        """Handle BlueZ PropertiesChanged signals."""
        if interface != "org.bluez.Device1":
            return
        if "Connected" not in changed:
            return

        new_state = bool(changed["Connected"])
        now = time.monotonic()
        old_state = self._is_connected

        logger.debug(
            "Keyboard Connected: %s -> %s (path=%s)",
            old_state,
            new_state,
            path,
        )

        if old_state and not new_state:
            # Keyboard disconnected — start debounce timer.
            self._last_disconnect_time = now
            self._is_connected = False
        elif not old_state and new_state:
            # Keyboard reconnected — check debounce.
            elapsed_ms = (now - self._last_disconnect_time) * 1000

            if elapsed_ms < self.debounce_ms:
                logger.debug(
                    "Debounce not met (%.0f ms < %d ms), ignoring.",
                    elapsed_ms,
                    self.debounce_ms,
                )
                self._is_connected = True
                return

            # Debounce passed — this is a real switch.
            self._is_connected = True
            self._on_switch_detected()

    def _on_switch_detected(self) -> None:
        """Handle a detected keyboard switch event."""
        ts = time.monotonic()

        if self._is_connected:
            # Keyboard reconnected to Linux.
            # We are on Linux — the keyboard switched FROM Windows TO Linux.
            event = KeyboardSwitchEvent(
                direction=SwitchDirection.WINDOWS_TO_LINUX,
                old_connected=False,
                timestamp=ts,
            )
            logger.info("Keyboard switched to Linux (slot %d)", self.linux_slot)

            # Send CHANGE_HOST if hidraw is available.
            self._send_change_host(event)

            for cb in self._callbacks:
                asyncio.create_task(cb(event)) if asyncio.iscoroutinefunction(cb) else cb(event)

    def _send_change_host(self, event: KeyboardSwitchEvent) -> None:
        """Send CHANGE_HOST command to the mouse."""
        if self.hidraw is None:
            logger.warning(
                "hidraw not available — cannot send CHANGE_HOST. "
                "Create a udev rule to allow hidraw access."
            )
            return

        target_slot = self.linux_slot
        logger.info(
            "Sending CHANGE_HOST to mouse (slot %d …)",
            target_slot,
        )

        try:
            self.hidraw.open(slot_index=target_slot)
            cmd = build_change_host_write_request(target_slot)
            self.hidraw.send(bytes(cmd))
            logger.info("CHANGE_HOST sent successfully.")
            self.hidraw.close()
        except Exception as exc:
            logger.error("Failed to send CHANGE_HOST: %s", exc)
            try:
                self.hidraw.close()
            except Exception:
                pass
