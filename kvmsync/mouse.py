"""Send HID++ CHANGE_HOST to the Logitech mouse via hidapi.

Shared by the Linux and Windows watchers. hidapi uses hidraw on Linux
(needs read/write access to /dev/hidraw*) and the native HID API on
Windows.
"""

from __future__ import annotations

import logging
import time

from .hidpp import (
    CHANGE_HOST,
    build_change_host_write_request,
    build_get_feature_index_request,
)

logger = logging.getLogger("kvmsync.mouse")

# Logitech MX Vertical.
MOUSE_VENDOR_ID = 0x046D
MOUSE_PRODUCT_ID = 0xB020

# Vendor usage pages carrying HID++: 0xFF43 for Bluetooth LE devices,
# 0xFF00 for devices behind a Unifying / Bolt receiver.
HIDPP_USAGE_PAGES = (0xFF43, 0xFF00)


def send_change_host(
    slot: int,
    vendor_id: int = MOUSE_VENDOR_ID,
    product_id: int = MOUSE_PRODUCT_ID,
) -> bool:
    """Switch the mouse to host *slot*. Returns True if the command was sent.

    Interfaces on a HID++ usage page are tried first; the rest are
    probed too, because some hidapi backends report usage_page 0.
    """
    try:
        import hid
    except ImportError:
        logger.error("hidapi not installed. Install with: pip install hidapi")
        return False

    devices = hid.enumerate(vendor_id, product_id)
    if not devices:
        logger.warning(
            "Mouse %04x:%04x not found (not connected to this host?).",
            vendor_id,
            product_id,
        )
        return False
    devices.sort(key=lambda d: d.get("usage_page") not in HIDPP_USAGE_PAGES)

    for dev in devices:
        h = hid.device()
        try:
            h.open_path(dev["path"])
        except OSError as exc:
            logger.debug("Cannot open %r: %s", dev["path"], exc)
            continue
        try:
            index = _get_feature_index(h, CHANGE_HOST)
            if not index:
                logger.error("Mouse does not support CHANGE_HOST (0x1814).")
                return False
            h.write(bytes(build_change_host_write_request(slot, index)))
            logger.info("CHANGE_HOST sent successfully (slot %d).", slot)
            return True
        except (OSError, ValueError, TimeoutError) as exc:
            logger.debug("No HID++ on %r: %s", dev["path"], exc)
        finally:
            h.close()

    logger.error(
        "No HID++ interface answered on the mouse. On Linux, check "
        "permissions on /dev/hidraw* (udev rule)."
    )
    return False


def _get_feature_index(h, feature: int, timeout_ms: int = 500) -> int:
    """Resolve the device-specific index of *feature* via IRoot."""
    req = build_get_feature_index_request(feature)
    if h.write(bytes(req)) < 0:
        raise OSError("write failed")
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        reply = bytes(h.read(64, timeout_ms))
        # Match report id, IRoot index 0x00 and our function/sw_id byte.
        if len(reply) >= 5 and reply[0] == 0x11 and reply[2] == 0x00 and reply[3] == req[3]:
            return reply[4]
    raise TimeoutError("No reply to IRoot.GetFeature")
