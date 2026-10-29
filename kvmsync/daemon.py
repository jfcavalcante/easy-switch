"""Main daemon: orchestrates keyboard watching and mouse synchronization."""

from __future__ import annotations

import asyncio
import logging
import sys

from .config import Config
from .events import KeyboardSwitchEvent, KeyboardWatcher
from .log import setup_logging

logger = logging.getLogger("kvmsync.daemon")


class Daemon:
    """Run a kvmsync daemon for the current host machine.

    The daemon picks an appropriate watcher based on the platform,
    connects it to event handlers, and runs a reconciliation loop
    in the background.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        setup_logging(config.daemon.verbose)

    async def run(self) -> None:
        """Run the daemon event loop.

        This creates the platform-appropriate watcher, registers event
        handlers, starts a reconciliation task, and awaits the watcher.
        """
        platform = sys.platform

        if platform == "linux":
            watcher = self._make_linux_watcher()
        elif platform == "win32":
            watcher = self._make_windows_watcher()
        else:
            logger.error("Unsupported platform: %s", platform)
            sys.exit(1)

        # Register event handlers.
        watcher.on_switch(self._on_keyboard_switch)

        # Start reconciliation task in the background.
        reconcile_task = asyncio.create_task(self._reconciliation_loop(watcher))

        try:
            # Watcher.start() blocks until stop() is called.
            await watcher.start()
        except asyncio.CancelledError:
            logger.info("Watcher cancelled.")
        except KeyboardInterrupt:
            logger.info("Interrupted.")
        finally:
            watcher.stop()
            reconcile_task.cancel()
            try:
                await reconcile_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    def _make_linux_watcher(self) -> KeyboardWatcher:
        """Create the appropriate watcher for Linux."""
        from .events_linux import LinuxKeyboardWatcher

        return LinuxKeyboardWatcher(
            linux_slot=self.config.hosts.linux_slot,
            windows_slot=self.config.hosts.windows_slot,
            debounce_ms=self.config.daemon.debounce_ms,
            verbose=self.config.daemon.verbose,
            hidraw=None,
        )

    def _make_windows_watcher(self) -> KeyboardWatcher:
        """Create the appropriate watcher for Windows."""
        from .events_windows import WindowsKeyboardWatcher

        return WindowsKeyboardWatcher(
            linux_slot=self.config.hosts.linux_slot,
            windows_slot=self.config.hosts.windows_slot,
            hidraw=None,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_keyboard_switch(self, event: KeyboardSwitchEvent) -> None:
        """Handle a keyboard host-switch event."""
        logger.info(
            "Keyboard switch: %s (old_connected=%s)",
            event.direction,
            event.old_connected,
        )

        if event.direction == SwitchDirection.WINDOWS_TO_LINUX:
            logger.info(
                "Keyboard switched to Linux (slot %d). "
                "CHANGE_HOST will be sent.",
                self.config.hosts.linux_slot,
            )
        elif event.direction == SwitchDirection.LINUX_TO_WINDOWS:
            logger.info(
                "Keyboard switched to Windows. "
                "No action needed — the Linux machine always sends the command."
            )

    async def _reconciliation_loop(self, watcher: KeyboardWatcher) -> None:
        """Periodically verify that the mouse is on the correct host.

        Runs every ``reconcile_interval_s`` seconds as a safety net.
        If the keyboard was on this machine but the mouse is not on the
        corresponding slot, re-send the CHANGE_HOST command.
        """
        interval = self.config.daemon.reconcile_interval_s
        logger.info(
            "Reconciliation loop started (every %ds).",
            interval,
        )

        while True:
            await asyncio.sleep(interval)
            await self._check_mouse_slot(watcher)

    async def _check_mouse_slot(self, watcher: KeyboardWatcher) -> None:
        """Check if the mouse is on the correct host slot."""
        # Stub: read the mouse current host via HID++ and compare.
        # When a real HidrawWriter is wired up, this will:
        # 1. Read the mouse's current host via CHANGE_HOST read command.
        # 2. Compare it to the expected slot for this machine.
        # 3. If mismatch, send CHANGE_HOST to correct it.
        pass
