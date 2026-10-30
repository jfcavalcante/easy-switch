"""Keyboard watcher shared by Linux and Windows: debounced presence polling.

Each platform supplies one function answering "is the keyboard connected
to this machine right now?". The watcher polls it and makes the mouse
follow the keyboard:

- Keyboard absent for ``away_after_s`` -> it switched to the other host,
  send CHANGE_HOST(remote slot).
- Keyboard present again for ``arrive_after_s`` -> it switched to this
  host, send CHANGE_HOST(local slot) (usually a no-op, because the other
  daemon already moved the mouse).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from .events import KeyboardSwitchEvent, KeyboardWatcher, SwitchDirection
from .mouse import send_change_host

logger = logging.getLogger("kvmsync.presence")


class PresenceWatcher(KeyboardWatcher):
    """Poll *is_present* and follow the keyboard with the mouse."""

    # Name of the OS this watcher runs on: "linux" or "windows".
    local_host: str = ""

    def __init__(
        self,
        is_present: Callable[[], bool],
        linux_slot: int = 0,
        windows_slot: int = 1,
        check_interval_s: float = 0.2,
        away_after_s: float = 1.0,
        arrive_after_s: float = 0.5,
    ) -> None:
        self.linux_slot = linux_slot
        self.windows_slot = windows_slot
        self.check_interval_s = check_interval_s
        self.away_after_s = away_after_s
        self.arrive_after_s = arrive_after_s
        self._is_present = is_present
        self._callbacks: list = []
        self._running = False
        self._present: bool = True
        # Monotonic time when the raw reading first differed from
        # self._present, or None while they agree.
        self._pending_since: float | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_switch(self, callback: Callable) -> None:
        """Register a callback for keyboard switch events.

        The callback may be sync or async (coroutine).
        """
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Poll keyboard presence until :meth:`stop` is called."""
        self._running = True
        logger.info("Starting %s keyboard watcher …", self.local_host)

        self._present = await asyncio.to_thread(self._is_present)
        self._pending_since = None
        logger.info("Initial keyboard state: present=%s", self._present)

        while self._running:
            await asyncio.sleep(self.check_interval_s)
            try:
                current = await asyncio.to_thread(self._is_present)
            except Exception:
                logger.exception("Keyboard presence check failed")
                continue
            self._update(current, time.monotonic())

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        logger.info("%s keyboard watcher stopped.", self.local_host)

    def get_host_for_slot(self, slot: int) -> str:
        """Return the OS name for a given host slot index."""
        if slot == self.linux_slot:
            return "linux"
        if slot == self.windows_slot:
            return "windows"
        return f"slot-{slot}"

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _update(self, current: bool, now: float) -> None:
        """Feed one presence reading; emit once it has been stable long enough."""
        if current == self._present:
            self._pending_since = None
            return

        if self._pending_since is None:
            self._pending_since = now
            logger.debug("Keyboard present=%s (pending)", current)

        needed = self.arrive_after_s if current else self.away_after_s
        if now - self._pending_since < needed:
            return

        self._present = current
        self._pending_since = None
        if current:
            logger.info("Keyboard arrived at %s.", self.local_host)
        else:
            logger.info("Keyboard left %s.", self.local_host)

        to_linux = current == (self.local_host == "linux")
        self._emit(
            SwitchDirection.WINDOWS_TO_LINUX
            if to_linux
            else SwitchDirection.LINUX_TO_WINDOWS
        )

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    def _emit(self, direction: SwitchDirection) -> None:
        """Emit a switch event and send CHANGE_HOST to the mouse."""
        event = KeyboardSwitchEvent(
            direction=direction,
            timestamp=time.monotonic(),
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
        self._send_change_host(target_slot)

        for cb in self._callbacks:
            if asyncio.iscoroutinefunction(cb):
                asyncio.ensure_future(cb(event))
            else:
                cb(event)

    def _send_change_host(self, slot: int) -> None:
        """Send CHANGE_HOST HID++ command to the Logitech mouse."""
        try:
            send_change_host(slot)
        except Exception:
            logger.exception("Failed to send CHANGE_HOST")
