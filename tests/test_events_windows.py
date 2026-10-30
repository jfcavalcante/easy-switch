"""Tests for the Windows hidapi-based keyboard watcher state machine."""

from kvmsync.events import SwitchDirection
from kvmsync.events_windows import WindowsKeyboardWatcher


def make_watcher():
    w = WindowsKeyboardWatcher(
        linux_slot=0, windows_slot=1, away_after_s=1.0, arrive_after_s=0.5
    )
    sent: list[int] = []
    events: list[SwitchDirection] = []
    w._send_change_host = sent.append
    w.on_switch(lambda e: events.append(e.direction))
    return w, sent, events


def test_leaving_sends_linux_slot_after_debounce():
    w, sent, events = make_watcher()
    w._update(False, 10.0)
    w._update(False, 10.5)
    assert sent == []
    w._update(False, 11.0)
    assert sent == [0]
    assert events == [SwitchDirection.WINDOWS_TO_LINUX]


def test_arriving_sends_windows_slot():
    w, sent, events = make_watcher()
    w._present = False
    w._update(True, 5.0)
    w._update(True, 5.5)
    assert sent == [1]
    assert events == [SwitchDirection.LINUX_TO_WINDOWS]


def test_short_dropout_is_ignored():
    w, sent, _ = make_watcher()
    w._update(False, 1.0)
    w._update(True, 1.4)
    w._update(False, 2.0)
    w._update(False, 2.5)
    assert sent == []


def test_full_round_trip():
    w, sent, _ = make_watcher()
    for t in (0.0, 0.5, 1.0, 1.5):
        w._update(False, t)
    for t in (10.0, 10.2, 10.5, 11.0):
        w._update(True, t)
    assert sent == [0, 1]
