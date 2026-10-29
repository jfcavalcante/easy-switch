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
    old_connected : bool
        Was the keyboard connected to *this* machine before the switch.
    timestamp : float
        Monotonic clock value at detection time.
    """

    direction: SwitchDirection
    old_connected: bool
    timestamp: float


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class KeyboardWatcher(abc.ABC):
    """Abstract keyboard watcher.

    Subclasses detect Bluetooth host switches for a specific OS.
    """

    # MAC address (or other identifier) of the keyboard.
    KEYBOARD_MAC: str = ""

    @abc.abstractmethod
    def start(self) -> None:
        """Start watching for keyboard switch events."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop watching."""

    @abc.abstractmethod
    def get_host_for_slot(self, slot: int) -> str:
        """Return the OS name for a given host slot index."""


class HidrawWriter(Protocol):
    """Protocol for writing to the mouse hidraw device."""

    def open(self, slot_index: int) -> None:
        """Open the hidraw device corresponding to the mouse's current slot."""

    def send(self, data: bytes) -> None:
        """Write HID++ data to the mouse."""

    def close(self) -> None:
        """Close the hidraw handle."""
