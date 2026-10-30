"""HID++ protocol primitives for Logitech mice.

Implements the CHANGE_HOST (feature 0x1814) and HOSTS_INFO
(feature 0x1815) commands used by multi-host Logitech mice.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import ClassVar

# ---------------------------------------------------------------------------
# HID++ 2.0 constants
# ---------------------------------------------------------------------------

CHANGE_HOST: int = 0x1814
HOSTS_INFO: int = 0x1815

HIDPP_LONG_MESSAGE_ID: int = 0x11  # 20-byte long message
HIDPP_SHORT_MESSAGE_ID: int = 0x10  # 16-byte short message (not used here)

# Feature function IDs
FN_READ: int = 0x00
FN_WRITE: int = 0x10

# Device devnumber for directly-connected (Bluetooth) devices
DEVNUMBER_BT: int = 0xFF

# Length of a HID++ 2.0 long message report (fixed)
LONG_MSG_LEN: int = 20

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class HostCountResponse:
    """Result of reading CHANGE_HOST with fnid=0x00.

    Attributes
    ----------
    num_hosts : int
        Number of paired Bluetooth hosts (typically 2 or 3).
    current_host : int
        Currently active host slot index (0-based).
    """

    num_hosts: int
    current_host: int


@dataclass
class HostInfo:
    """Information about a single paired host.

    Attributes
    ----------
    paired : bool
        Whether this slot has a device paired.
    name : str
        Host name stored in the mouse (if any).
    """

    paired: bool
    name: str


@dataclass
class SendResult:
    """Outcome of sending an HID++ command."""

    success: bool
    error: int | None = None  # HID++ error code, if any


# ---------------------------------------------------------------------------
# Helper: build / parse HID++ packets
# ---------------------------------------------------------------------------


def _build_feature_request(
    feature: int,
    function: int,
    *params: int,
    no_reply: bool = False,
) -> bytearray:
    """Build a HID++ 2.0 long-message packet.

    Packet layout (20 bytes):
        byte 0:   report ID (0x11)
        byte 1:   devnumber (0xFF for BT)
        byte 2-3: request_id (feature << 8 | function | sw_id)
        bytes 4:  first parameter
        ...
        bytes 4-19: padded with zeros

    Parameters
    ----------
    feature : int
        Feature code, e.g. 0x1814.
    function : int
        Function ID - 0x00 for read, 0x10 for write.
    *params : int
        Parameter bytes for the command.
    no_reply : bool
        When True the caller does not expect a device reply.
    """
    # Build a 4-bit software ID for disambiguating requests.
    # In HID++ 2.0 the request_id is: [feature_index << 8 | function]
    # The lower 4 bits are overwritten with sw_id at request time.
    sw_id = random.getrandbits(4)
    request_id = (feature << 8) | function
    # Mask lower 4 bits with sw_id (as the Linux solaar does).
    request_id = (request_id & 0xFFF0) | sw_id

    buf = bytearray(LONG_MSG_LEN)
    buf[0] = HIDPP_LONG_MESSAGE_ID
    buf[1] = DEVNUMBER_BT
    buf[2] = (request_id >> 8) & 0xFF
    buf[3] = request_id & 0xFF

    for i, p in enumerate(params):
        if i + 4 < LONG_MSG_LEN:
            buf[i + 4] = p & 0xFF

    return buf


def _parse_host_count(data: bytes) -> HostCountResponse:
    """Parse the response from ``feature_request(CHANGE_HOST, FN_READ)``.

    Returns ``(num_hosts, current_host)``.
    """
    if len(data) < 2:
        raise ValueError(f"Host count response too short: {data!r}")
    return HostCountResponse(
        num_hosts=data[0],
        current_host=data[1],
    )


def _parse_hosts_info(data: bytes) -> list[HostInfo]:
    """Parse the response from ``feature_request(HOSTS_INFO, FN_READ)``.

    The response is a sequence of 2-byte entries:
        byte 0:  pair-status (bit 0 = paired)
        byte 1:  host name length
        bytes 2..: host name (null-padded, max 16 chars per entry)

    For brevity we return the known paired hosts.
    """
    if not data:
        return []

    hosts: list[HostInfo] = []
    offset = 0
    while offset + 1 < len(data):
        pair_byte = data[offset]
        name_len = data[offset + 1] if offset + 2 < len(data) else 0
        name_start = offset + 2
        name_end = min(name_start + name_len, len(data))
        name = data[name_start:name_end].decode("utf-8", errors="replace").rstrip("\x00")
        hosts.append(HostInfo(
            paired=bool(pair_byte & 0x01),
            name=name,
        ))
        offset += 2 + name_len  # each entry: pair + len + name
        if offset >= len(data):
            break

    return hosts


# ---------------------------------------------------------------------------
# Public API (low-level)
# ---------------------------------------------------------------------------


def build_get_feature_index_request(feature: int) -> bytearray:
    """Build an IRoot.GetFeature request (feature index 0x00, fn 0x00).

    The reply carries the device-specific index of *feature* in byte 4
    (0 means the feature is not supported).
    """
    return _build_feature_request(0x00, FN_READ, feature >> 8, feature & 0xFF)


def build_change_host_write_request(
    slot: int, feature_index: int = CHANGE_HOST
) -> bytearray:
    """Build a CHANGE_HOST command to switch to *slot* (0, 1, or 2).

    *feature_index* should be the index returned by IRoot.GetFeature
    for 0x1814; it varies per device (0x0C on the MX Vertical).

    This is a fire-and-forget command (no_reply=True).
    """
    if slot not in (0, 1, 2):
        raise ValueError(f"Host slot must be 0-2, got {slot}")
    return _build_feature_request(feature_index, FN_WRITE, slot)


def build_change_host_read_request() -> bytearray:
    """Build a CHANGE_HOST read request to query current host."""
    return _build_feature_request(CHANGE_HOST, FN_READ)


def build_hosts_info_read_request() -> bytearray:
    """Build a HOSTS_INFO read request to query paired host names."""
    return _build_feature_request(HOSTS_INFO, FN_READ)


def parse_host_count_response(data: bytes) -> HostCountResponse:
    """Parse a CHANGE_HOST read response."""
    return _parse_host_count(data)


def parse_hosts_info_response(data: bytes) -> list[HostInfo]:
    """Parse a HOSTS_INFO read response."""
    return _parse_hosts_info(data)


# ---------------------------------------------------------------------------
# High-level helper (requires a hidapi handle)
# ---------------------------------------------------------------------------


def send_change_host(
    handle,
    slot: int,
    write_fn,
    read_fn,
    debounce_ms: int = 0,
) -> SendResult:
    """Send a CHANGE_HOST command and verify the switch.

    Parameters
    ----------
    handle : object
        An open hidapi device handle (used only for the write).
    slot : int
        Target host slot (0, 1, or 2).
    write_fn : callable
        ``write_fn(data: bytes)`` - writes bytes to the device.
    read_fn : callable
        ``read_fn(timeout: float) -> bytes | None`` - reads a reply.
    debounce_ms : int
        Wait this many milliseconds after writing before reading,
        to give the device time to process the command.

    Returns
    -------
    SendResult
    """
    # 1. Send the command (fire-and-forget).
    try:
        cmd = build_change_host_write_request(slot)
        write_fn(bytes(cmd))
    except OSError as exc:
        return SendResult(success=False, error=-1)

    if debounce_ms:
        import time
        time.sleep(debounce_ms / 1000.0)

    # 2. Read back current host to confirm.
    try:
        # Wait briefly for a reply; timeout = 1 s.
        reply = read_fn(timeout=1.0)
        if reply is None:
            # No reply - command was likely accepted (no_reply mode).
            return SendResult(success=True)
        resp = parse_host_count_response(reply)
        return SendResult(success=resp.current_host == slot)
    except (OSError, ValueError) as exc:
        return SendResult(success=False, error=-2)
