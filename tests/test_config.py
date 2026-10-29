"""Tests for the configuration loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from kvmsync.config import Config, DaemonConfig, HostConfig, MouseConfig, load_config

VALID_CONFIG = """
[mouse]
vendor_id = 0x046D
product_id = 0xB020

[hosts]
linux_slot = 0
windows_slot = 1

[daemon]
debounce_ms = 500
reconcile_interval_s = 5
verbose = false
"""

MINIMAL_CONFIG = """
[mouse]
vendor_id = 0x046D
product_id = 0xB020

[hosts]
linux_slot = 0
windows_slot = 1
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Write the default valid config to a temporary file and return its path."""
    f = tmp_path / "config.toml"
    f.write_text(VALID_CONFIG)
    return f


@pytest.fixture
def minimal_config_file(tmp_path: Path) -> Path:
    """Write a minimal config (no [daemon]) and return its path."""
    f = tmp_path / "config.toml"
    f.write_text(MINIMAL_CONFIG)
    return f


class TestLoadConfig:
    """Test config loading from disk."""

    def test_valid_config(self, config_file: Path):
        cfg = load_config(config_file)
        assert cfg.mouse.vendor_id == 0x046D
        assert cfg.mouse.product_id == 0xB020
        assert cfg.hosts.linux_slot == 0
        assert cfg.hosts.windows_slot == 1
        assert cfg.daemon.debounce_ms == 500
        assert cfg.daemon.reconcile_interval_s == 5
        assert cfg.daemon.verbose is False

    def test_minimal_config(self, minimal_config_file: Path):
        """Minimal config (no [daemon] section) uses defaults."""
        cfg = load_config(minimal_config_file)
        assert cfg.daemon.debounce_ms == 500
        assert cfg.daemon.reconcile_interval_s == 5
        assert cfg.daemon.verbose is False

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.toml")

    def test_custom_path(self, config_file: Path):
        """load_config accepts an explicit path."""
        cfg = load_config(config_file)
        assert cfg.mouse.vendor_id == 0x046D


class TestAlternateSlots:
    """Test alternate slot configurations."""

    def test_alt_slots(self, tmp_path: Path) -> Path:
        content = """
[mouse]
vendor_id = 0x046D
product_id = 0xB020

[hosts]
linux_slot = 1
windows_slot = 2

[daemon]
debounce_ms = 1000
reconcile_interval_s = 10
verbose = true
"""
        f = tmp_path / "config.toml"
        f.write_text(content)
        cfg = load_config(f)
        assert cfg.hosts.linux_slot == 1
        assert cfg.hosts.windows_slot == 2
        assert cfg.daemon.verbose is True
        assert cfg.daemon.debounce_ms == 1000


class TestConfigValidation:
    """Test configuration validation."""

    def test_invalid_linux_slot(self, tmp_path: Path):
        content = VALID_CONFIG.replace("linux_slot = 0", "linux_slot = 5")
        f = tmp_path / "config.toml"
        f.write_text(content)
        with pytest.raises(ValueError, match="linux_slot must be 0, 1, or 2"):
            load_config(f)

    def test_invalid_windows_slot(self, tmp_path: Path):
        content = VALID_CONFIG.replace("windows_slot = 1", "windows_slot = 99")
        f = tmp_path / "config.toml"
        f.write_text(content)
        with pytest.raises(ValueError, match="windows_slot must be 0, 1, or 2"):
            load_config(f)

    def test_negative_debounce(self, tmp_path: Path):
        content = VALID_CONFIG.replace("debounce_ms = 500", "debounce_ms = -10")
        f = tmp_path / "config.toml"
        f.write_text(content)
        with pytest.raises(ValueError, match="debounce_ms must be >= 0"):
            load_config(f)

    def test_interval_too_low(self, tmp_path: Path):
        content = VALID_CONFIG.replace("reconcile_interval_s = 5", "reconcile_interval_s = 0")
        f = tmp_path / "config.toml"
        f.write_text(content)
        with pytest.raises(ValueError, match="reconcile_interval_s must be >= 1"):
            load_config(f)


class TestConfigDataclasses:
    """Test config dataclass structure."""

    def test_config_is_dataclass(self):
        cfg = Config(
            mouse=MouseConfig(vendor_id=0x046D, product_id=0xB020),
            hosts=HostConfig(linux_slot=0, windows_slot=1),
        )
        assert cfg.mouse.vendor_id == 0x046D

    def test_frozen_dataclasses(self):
        cfg = Config(
            mouse=MouseConfig(vendor_id=0x046D, product_id=0xB020),
            hosts=HostConfig(linux_slot=0, windows_slot=1),
        )
        with pytest.raises(Exception):
            cfg.mouse.vendor_id = 0x1234
