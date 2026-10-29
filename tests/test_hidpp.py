"""Tests for the HID++ protocol module."""

from __future__ import annotations

import pytest

from kvmsync.hidpp import (
    CHANGE_HOST,
    HOSTS_INFO,
    FN_WRITE,
    _build_feature_request,
    _parse_host_count,
    _parse_hosts_info,
    build_change_host_read_request,
    build_change_host_write_request,
    build_hosts_info_read_request,
    parse_host_count_response,
    parse_hosts_info_response,
)


class TestBuildFeatureRequest:
    """Build correct HID++ 2.0 long-message packets."""

    def test_change_host_write_request(self):
        """Writing to slot 1 should produce a valid packet."""
        data = _build_feature_request(CHANGE_HOST, FN_WRITE, 1)
        assert len(data) == 20
        assert data[0] == 0x11  # Long message report ID
        assert data[1] == 0xFF  # BT devnumber
        # Feature 0x1814 high byte (shifted: 0x1814 << 8 = 0x181400, & 0xFF00 = 0x14)
        # Actually: request_id = (0x1814 << 8) | 0x10 = ...
        # Then (request_id & 0xFFF0) | sw_id
        # Byte 2 = (request_id >> 8) & 0xFF = (0x1814 & 0xFF) = 0x14
        assert data[2] == 0x14
        assert data[4] == 1  # Slot 1

    def test_invalid_slot_raises(self):
        """Slot outside 0-2 should not be accepted at the public API."""
        with pytest.raises(ValueError, match="slot must be 0-2"):
            build_change_host_write_request(5)

    def test_change_host_read_request(self):
        """Reading current host."""
        data = _build_feature_request(CHANGE_HOST, 0x00)
        assert len(data) == 20
        assert data[2] == 0x14
        assert data[4] == 0  # Read has no params

    def test_all_bytes_initialized(self):
        """Unused bytes should be zero (no garbage)."""
        data = _build_feature_request(CHANGE_HOST, FN_WRITE, 0)
        # All bytes after byte 5 should be zero.
        assert all(b == 0 for b in data[5:])

    def test_read_has_no_params(self):
        """Read requests have no parameters (byte 4 = 0)."""
        data = _build_feature_request(CHANGE_HOST, 0x00)
        assert data[4] == 0

    def test_feature_index_in_byte2(self):
        """Byte 2 holds the lower byte of the feature code."""
        data = _build_feature_request(HOSTS_INFO, 0x00)
        # HOSTS_INFO = 0x1815, so byte 2 = 0x15
        assert data[2] == 0x15


class TestBuildRequestFunctions:
    """Public convenience functions."""

    def test_build_change_host_write(self):
        req = build_change_host_write_request(2)
        assert req[0] == 0x11
        assert req[4] == 2

    def test_build_change_host_read(self):
        req = build_change_host_read_request()
        assert req[0] == 0x11

    def test_build_hosts_info_read(self):
        req = build_hosts_info_read_request()
        assert req[0] == 0x11
        assert req[2] == 0x15  # HOSTS_INFO low byte

    def test_invalid_slot_raises(self):
        with pytest.raises(ValueError, match="slot must be 0-2"):
            build_change_host_write_request(99)


class TestParseHostCount:
    """Parse CHANGE_HOST read responses."""

    def test_two_hosts_current_0(self):
        resp = parse_host_count_response(bytes([2, 0]))
        assert resp.num_hosts == 2
        assert resp.current_host == 0

    def test_three_hosts_current_1(self):
        resp = parse_host_count_response(bytes([3, 1]))
        assert resp.num_hosts == 3
        assert resp.current_host == 1

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="too short"):
            parse_host_count_response(bytes([2]))


class TestParseFunctions:
    """Public parse functions."""

    def test_parse_host_count_response(self):
        resp = parse_host_count_response(bytes([3, 2]))
        assert resp.num_hosts == 3
        assert resp.current_host == 2

    def test_parse_hosts_info_empty(self):
        result = parse_hosts_info_response(b"")
        assert result == []

    def test_parse_hosts_info_one_paired(self):
        # One entry: paired (0x01), name "Linux" (5 chars)
        data = bytes([0x01, 5, 76, 105, 110, 117, 120])
        result = parse_hosts_info_response(data)
        assert len(result) == 1
        assert result[0].paired is True
        assert result[0].name == "Linux"

    def test_parse_hosts_info_multiple(self):
        # Two entries: paired "Linux", unpaired ""
        data = bytes([
            0x01, 5, 76, 105, 110, 117, 120,  # paired "Linux"
            0x00, 0,                            # unpaired ""
        ])
        result = parse_hosts_info_response(data)
        assert len(result) == 2
        assert result[0].paired is True
        assert result[0].name == "Linux"
        assert result[1].paired is False
        assert result[1].name == ""
