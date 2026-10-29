"""Main daemon: orchestrates keyboard watching and mouse synchronization."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from .config import Config
from .events import KeyboardSwitchEvent, KeyboardWatcher, SwitchDirection
from .log import setup_logging

logger = logging.getLogger("kvmsync.daemon")


class Daemon:
    """Run a kvmsync daemon for the current host machine.

    The daemon picks an appropriate watcher based on the platform,
    connects it to a handler that sends CHANGE_HOST commands, and
    runs a reconciliation loop in the background.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        setup_logging(config.daemon.verbose)

    async def run(self) -> None:
        """Run the daemon event loop."""
        platform = sys.platform

        if platform == "linux":
            watcher = self._make_linux_watcher()
        elif platform == "win32":
            watcher = self._make_windows_watcher()
        else:
            logger.error("Unsupported platform: %s", platform)
            sys.exit(1)

        # Register the event handler.
        watcher.on_switch(self._on_keyboard_switch)

        # Register the reconciliation callback.
        watcher.on_switch(self._reconcile_check)

        # Start the watcher (blocks until stopped).
        try:
            watcher.start()
        except KeyboardInterrupt:
            logger.info("Interrupted.")
        finally:
            watcher.stop()

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    def _make_linux_watcher(self) -> KeyboardWatcher:
        """Create the appropriate watcher for Linux."""
        # Import happens inside the method so we don't crash on Windows.
        from .events_linux import LinuxKeyboardWatcher

        return LinuxKeyboardWatcher(
            linux_slot=self.config.hosts.linux_slot,
            windows_slot=self.config.hosts.windows_slot,
            debounce_ms=self.config.daemon.debounce_ms,
            verbose=self.config.daemon.verbose,
            # hidraw can be wired up later if a real HidrawWriter is available.
            hidraw=None,
        )

    def _make_windows_watcher(self) -> KeyboardWatcher:
        """Create the appropriate watcher for Windows."""
        from .events_windows import WindowsKeyboardWatcher

        return WindowsKeyboardWatcher(
            linux_slot=self.config.hosts.linux_slot,
            windows_slot=self.config.hosts.windows_slot,
            # Windows never sends CHANGE_HOST.
            hidraw=None,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_keyboard_switch(self, event: KeyboardSwitchEvent) -> None:
        """Handle a keyboard host-switch event."""
        logger.info(
            "Keyboard switch event: %s (old_connected=%s)",
            event.direction,
            event.old_connected,
        )

        if event.direction == SwitchDirection.WINDOWS_TO_LINUX:
            logger.info(
                "Keyboard switched to Linux (slot %d). "
                "Sending CHANGE_HOST to mouse …",
                self.config.hosts.linux_slot,
            )
            # The Linux daemon will handle sending the command.
        elif event.direction == SwitchDirection.LINUX_TO_WINDOWS:
            logger.info(
                "Keyboard switched to Windows. "
                "Windows does not send CHANGE_HOST — the Linux machine handles it."
            )

    async def _reconcile_check(self, event: KeyboardSwitchEvent) -> None:
        """Periodic reconciliation check.

        If the watcher detected a switch, this callback runs as a
        safety net to verify the mouse ended up on the correct host.
        """
        # The actual reconciliation logic reads the mouse's current
        # host and compares it to what the switch event implies.
        # This is a stub that would call the HID++ read function.
        pass
