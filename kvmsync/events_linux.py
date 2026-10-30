"""Linux keyboard watcher using BlueZ D-Bus.

Listens for ``PropertiesChanged`` signals on
``org.bluez.Device1.Connected`` for the Aula75 keyboard.

Switch logic
------------
When the keyboard switches **to this machine** (reconnects to
Linux), the daemon sends CHANGE_HOST to the mouse.

When the keyboard switches **away from this machine** (disconnects
from Linux and does not reconnect within the timeout), the daemon
also sends CHANGE_HOST — so the mouse follows to the new host.

In both cases the correct target slot is:
- ``linux_slot`` when the keyboard arrives at Linux
- ``windows_slot`` when the keyboard leaves Linux
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
from .log import setup_logging

logger = logging.getLogger("kvmsync.events_linux")

# D-Bus object path of the Aula75 keyboard.
KEYBOARD_PATH = "/org/bluez/hci0/dev_E3_34_CC_0D_A4_0F"

# Time to wait for reconnection before assuming the keyboard has
# switched away from this machine.
RECONNECT_TIMEOUT_S = 3


class LinuxKeyboardWatcher(KeyboardWatcher):
    """Monitor BlueZ for keyboard host switches."""

    def __init__(
        self,
        linux_slot: int = 0,
        windows_slot: int = 1,
        debounce_ms: int = 500,
        verbose: bool = False,
        hidraw: HidrawWriter | None = None,
    ) -> None:
        self.linux_slot = linux_slot
        self.windows_slot = windows_slot
        self.debounce_ms = debounce_ms
        self.verbose = verbose
        self.hidraw = hidraw
        setup_logging(self.verbose)
        self._callbacks: list = []
        self._last_disconnect_time: float = 0.0
        self._is_connected: bool = True
        self._running: bool = False
        self._disconnect_timer_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_switch(self, callback) -> None:
        """Register a callback for keyboard switch events."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start watching BlueZ D-Bus for keyboard events."""
        self._running = True
        logger.info("Starting Linux keyboard watcher …")

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

        bus.add_signal_receiver(
            self._on_dbus_signal,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path=KEYBOARD_PATH,
        )

        try:
            initial = props_iface.Get("org.bluez.Device1", "Connected")
            self._is_connected = bool(initial)
            logger.info("Initial keyboard state: connected=%s", self._is_connected)
        except Exception as exc:
            logger.warning("Could not read initial Connected state: %s", exc)

        logger.info(
            "Watching %s (linux_slot=%d, windows_slot=%d)",
            KEYBOARD_PATH,
            self.linux_slot,
            self.windows_slot,
        )

        while self._running:
            await asyncio.sleep(0.1)

            # If keyboard is disconnected and no timer is running,
            # start the reconnect timeout.
            if not self._is_connected:
                if (
                    self._disconnect_timer_task is None
                    or self._disconnect_timer_task.done()
                ):
                    self._disconnect_timer_task = asyncio.create_task(
                        self._wait_reconnect()
                    )
                    if self._disconnect_timer_task.done():
                        self._disconnect_timer_task = None

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._disconnect_timer_task:
            self._disconnect_timer_task.cancel()
        logger.info("Linux keyboard watcher stopped.")

    def get_host_for_slot(self, slot: int) -> str:
        """Return the OS name for a given slot."""
        if slot == self.linux_slot:
            return "linux"
        if slot == self.windows_slot:
            return "windows"
        return f"slot-{slot}"

    # ------------------------------------------------------------------
    # D-Bus callback (sync — called from dbus-python thread)
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

        logger.debug("Keyboard Connected: %s -> %s", old_state, new_state)

        if old_state and not new_state:
            # Keyboard disconnected — start timer.
            self._last_disconnect_time = now
            self._is_connected = False
        elif not old_state and new_state:
            # Keyboard reconnected.
            # Cancel any pending "switched away" timer.
            if self._disconnect_timer_task and not self._disconnect_timer_task.done():
                self._disconnect_timer_task.cancel()
                self._disconnect_timer_task = None

            elapsed_ms = (now - self._last_disconnect_time) * 1000
            if elapsed_ms < self.debounce_ms:
                logger.debug(
                    "Debounce not met (%.0f ms < %d ms), ignoring.",
                    elapsed_ms,
                    self.debounce_ms,
                )
                self._is_connected = True
                return

            # Debounce passed — keyboard arrived at Linux.
            self._is_connected = True
            self._emit(SwitchDirection.WINDOWS_TO_LINUX)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _wait_reconnect(self) -> None:
        """Wait for reconnection; emit switch if no reconnect within timeout."""
        await asyncio.sleep(RECONNECT_TIMEOUT_S)

        if not self._is_connected:
            logger.info(
                "Keyboard did not reconnect within %.0fs — "
                "assuming switched away from this machine.",
                RECONNECT_TIMEOUT_S,
            )
            self._emit(SwitchDirection.LINUX_TO_WINDOWS)

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

        logger.info("Keyboard switched to %s (slot %d).", host_name, target_slot)
        self._send_change_host(target_slot, event)

        for cb in self._callbacks:
            if asyncio.iscoroutinefunction(cb):
                asyncio.ensure_future(cb(event))
            else:
                cb(event)

    def _send_change_host(self, slot: int, event: KeyboardSwitchEvent) -> None:
        """Send CHANGE_HOST command to the mouse."""
        if self.hidraw is None:
            logger.warning(
                "hidraw not available — cannot send CHANGE_HOST. "
                "Create a udev rule to allow hidraw access."
            )
            return

        try:
            self.hidraw.open(slot_index=slot)
            cmd = build_change_host_write_request(slot)
            self.hidraw.send(bytes(cmd))
            logger.info("CHANGE_HOST sent successfully (slot %d).", slot)
            self.hidraw.close()
        except Exception as exc:
            logger.error("Failed to send CHANGE_HOST: %s", exc)
            try:
                self.hidraw.close()
            except Exception:
                pass
