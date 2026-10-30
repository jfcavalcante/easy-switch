"""Cross-platform keyboard host-switch watcher."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Protocol


class SwitchDirection(IntEnum):
    """Which way the keyboard switched."""

    LINUX_TO_WINDOWS = 1
    WINDOWS_TO_LINUX = 2


@dataclass(frozen=True)
class KeyboardSwitchEvent:
    """A keyboard host-switch event.

    Attributes
    ----------
    direction : SwitchDirection
        Which way the keyboard switched.
    timestamp : float
        Monotonic clock value at detection time.
    """

    direction: SwitchDirection
    timestamp: float


class HidrawWriter(Protocol):
    """Protocol for writing to the mouse hidraw device."""

    def open(self, slot_index: int) -> None:
        """Open the hidraw device corresponding to the mouse's current slot."""

    def send(self, data: bytes) -> None:
        """Write HID++ data to the mouse."""

    def close(self) -> None:
        """Close the hidraw handle."""


class KeyboardWatcher(abc.ABC):
    """Abstract keyboard watcher.

    Subclasses detect Bluetooth host switches for a specific OS.
    """

    # MAC address (or other identifier) of the keyboard.
    KEYBOARD_MAC: str = ""

    @abc.abstractmethod
    async def start(self) -> None:
        """Start watching for keyboard switch events.

        Blocks the calling coroutine until :meth:`stop` is called.
        """

    @abc.abstractmethod
    def stop(self) -> None:
        """Signal the watcher to stop and release resources."""

    @abc.abstractmethod
    def get_host_for_slot(self, slot: int) -> str:
        """Return the OS name for a given host slot index."""
