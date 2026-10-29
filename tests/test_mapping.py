"""Tests for keyboard-to-mouse host mapping logic."""

from __future__ import annotations

import pytest

from kvmsync.events import KeyboardSwitchEvent, SwitchDirection


class TestSwitchDirection:
    """Verify SwitchDirection enum values."""

    def test_windows_to_linux(self):
        assert SwitchDirection.WINDOWS_TO_LINUX.value == 2

    def test_linux_to_windows(self):
        assert SwitchDirection.LINUX_TO_WINDOWS.value == 1


class TestEventCreation:
    """Verify KeyboardSwitchEvent construction."""

    def test_from_windows_to_linux(self):
        event = KeyboardSwitchEvent(
            direction=SwitchDirection.WINDOWS_TO_LINUX,
            old_connected=False,
            timestamp=1000.0,
        )
        assert event.direction == SwitchDirection.WINDOWS_TO_LINUX
        assert event.old_connected is False
        assert event.timestamp == 1000.0

    def test_frozen_dataclass(self):
        """Events should be immutable."""
        event = KeyboardSwitchEvent(
            direction=SwitchDirection.LINUX_TO_WINDOWS,
            old_connected=True,
            timestamp=0.0,
        )
        with pytest.raises(Exception):
            event.direction = SwitchDirection.WINDOWS_TO_LINUX


def resolve_target_slot(
    direction: SwitchDirection,
    linux_slot: int,
    windows_slot: int,
) -> int:
    """Resolve which mouse slot to switch to."""
    if direction == SwitchDirection.WINDOWS_TO_LINUX:
        return linux_slot
    elif direction == SwitchDirection.LINUX_TO_WINDOWS:
        return windows_slot
    raise ValueError(f"Unknown direction: {direction}")


class TestMappingLogic:
    """Test the core mapping: which slot to send for each switch direction."""

    def test_windows_to_linux_uses_linux_slot(self):
        assert resolve_target_slot(
            SwitchDirection.WINDOWS_TO_LINUX,
            linux_slot=0,
            windows_slot=1,
        ) == 0

    def test_linux_to_windows_uses_windows_slot(self):
        assert resolve_target_slot(
            SwitchDirection.LINUX_TO_WINDOWS,
            linux_slot=0,
            windows_slot=1,
        ) == 1

    def test_arbitrary_slots(self):
        """Works with any valid slot mapping."""
        assert resolve_target_slot(
            SwitchDirection.WINDOWS_TO_LINUX,
            linux_slot=2,
            windows_slot=1,
        ) == 2

        assert resolve_target_slot(
            SwitchDirection.LINUX_TO_WINDOWS,
            linux_slot=1,
            windows_slot=2,
        ) == 2

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="Unknown direction"):
            resolve_target_slot(0, linux_slot=0, windows_slot=1)
