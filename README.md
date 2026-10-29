# kvmsync

Synchronize Bluetooth host switching between a multi-host keyboard and a multi-host mouse across Linux and Windows.

When you press **fn+1** on your keyboard to switch to Linux, the mouse automatically switches to the corresponding Bluetooth slot — and vice versa.

## How It Works

1. Each machine runs its own `kvmsync` daemon.
2. The Linux daemon monitors the keyboard's Bluetooth connection state via **BlueZ D-Bus**.
3. The Windows daemon monitors HID device events via **SetupAPI**.
4. When the keyboard reconnects to Linux (detected by the Linux daemon), the daemon sends a **HID++ CHANGE_HOST** command to the mouse via `hidraw`.
5. The Windows daemon does nothing on keyboard removal (the Linux machine always sends the command).
6. A periodic reconciliation check (every 5 seconds) ensures the mouse is on the correct host, catching edge cases.

## Supported Hardware

| Device | Type | Connection |
|---|---|---|
| Aula75 (or similar) | Keyboard | Bluetooth multi-host |
| Logitech MX Vertical | Mouse | Bluetooth (HID++ 2.0) |

The mouse must support the **CHANGE_HOST** (feature `0x1814`) HID++ 2.0 command. This includes most Logitech multi-host devices (MX Vertical, MX Master 3, MX Anywhere 3, etc.).

## Installation

### Prerequisites

- **Python 3.10+**
- **pip**

### Linux

1. Install the package:

   ```bash
   cd easy-switch
   pip install -e ".[docs]"
   ```

2. Install `hidapi` (the only external dependency):

   ```bash
   sudo apt install libhidapi-libusb0   # Debian/Ubuntu
   pip install hidapi
   ```

3. Grant access to the mouse's hidraw device (one-time setup):

   ```bash
   sudo tee /etc/udev/rules.d/99-kvmsync.rules << 'EOF'
   # Allow the kvmsync user to write to Logitech mice via hidraw
   SUBSYSTEM=="hidraw", ATTRS{idVendor}=="046d", ATTRS{idProduct}=="b020", GROUP="plugdev", MODE="0660"
   EOF
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   sudo usermod -aG plugdev $USER
   ```

   > **Important:** You must log out and log back in (or reboot) for the group change to take effect. Adjust `idProduct` if your mouse has a different product ID (see [Finding Your Host Slot](#finding-your-host-slot) below).

4. Create the configuration file:

   ```bash
   cp config.example.toml config.toml
   ```

   Edit `config.toml` with your settings.

### Windows

1. Install the package:

   ```powershell
   cd C:\path\to\easy-switch
   pip install -e ".[docs]"
   ```

2. For device notifications, `pywin32` is typically pre-installed on most Windows systems. If not:

   ```powershell
   pip install pywin32
   ```

3. Create the configuration file:

   ```powershell
   Copy-Item config.example.toml config.toml
   ```

   Edit `config.toml` with your settings.

4. Run the daemon as a regular user (no admin required in most cases).

## Configuration

Copy `config.example.toml` to `config.toml` and adjust:

```toml
[mouse]
# Logitech VID (always 0x046D)
vendor_id = 0x046D
# Mouse product ID — verify with lsusb (Linux) or Device Manager (Windows)
product_id = 0xB020

[hosts]
# BT host slot indices (0-based: 0 = BT1, 1 = BT2, 2 = BT3)
linux_slot = 0
windows_slot = 1

[daemon]
# Debounce window in milliseconds
debounce_ms = 500
# Reconciliation interval in seconds
reconcile_interval_s = 5
# Verbose logging
verbose = false
```

### Finding Your Host Slot

The host slot is the **Bluetooth slot number** on your mouse, 0-based:

- Slot 0 = BT1 (first Bluetooth connection)
- Slot 1 = BT2 (second Bluetooth connection)
- Slot 2 = BT3 (third Bluetooth connection, if available)

To find which slot is which:

1. On the mouse, look at the Easy-Switch button or slot indicators.
2. Switch the mouse manually to the slot connected to your Linux machine — note the slot number (1, 2, or 3).
3. Subtract 1 to get the 0-based index.

For example, if Linux is connected via **BT2**, use `linux_slot = 1`.

### Verbose Mode

Enable verbose logging for debugging:

```bash
kvmsync --verbose
```

Or set `verbose = true` in `config.toml`.

## Running

### As a foreground process

```bash
kvmsync
```

### As a systemd service (Linux)

Create `/etc/systemd/system/kvmsync.service`:

```ini
[Unit]
Description=kvmSync Bluetooth host sync daemon
After=bluetooth.target

[Service]
Type=simple
User=jh_cavalcante
ExecStart=/usr/bin/python3 -m kvmsync
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable kvmsync
sudo systemctl start kvmsync
sudo systemctl status kvmsync
```

### List paired Bluetooth devices (Linux)

```bash
kvmsync --list-devices
```

This prints all paired Bluetooth devices with their connection status, useful for verifying your setup.

## Architecture

```
┌───────────────────────┐
│     Linux Machine      │
│                      │
│  BlueZ D-Bus         │─── Keyboard reconnect ──→ CHANGE_HOST ──→ Mouse
│  PropertiesChanged   │
│                      │
│  Reconciliation 5s   │─── Safety net ──→ Verify mouse slot
│                      │
└───────────────────────┘

┌───────────────────────┐
│    Windows Machine     │
│                      │
│  SetupAPI            │─── Keyboard removal ──→ Log only
│  Device notification │   (Linux sends the command)
│                      │
│  Reconciliation 5s   │─── Safety net ──→ Verify mouse slot
│                      │
└───────────────────────┘
```

Key design decisions:

- **No network coordination between machines** — the logic "only act on reconnection" guarantees no race condition.
- **Only the Linux machine sends CHANGE_HOST** — it's the one that sees the keyboard reconnect.
- **Self-healing** — the 5-second reconciliation loop catches any errors where the watcher missed an event.

## Project Structure

```
kvmsync/
├── kvmsync/
│   ├── __init__.py
│   ├── __main__.py        # CLI entry point
│   ├── config.py          # TOML configuration loader
│   ├── daemon.py          # Main daemon loop
│   ├── events.py          # Keyboard watcher base class
│   ├── events_linux.py    # BlueZ D-Bus watcher
│   ├── events_windows.py  # SetupAPI watcher
│   ├── hidpp.py           # HID++ 2.0 protocol (CHANGE_HOST)
│   └── log.py             # Logging setup
├── tests/
│   ├── test_config.py     # Config loading and validation
│   ├── test_hidpp.py      # HID++ packet builder/parser
│   └── test_mapping.py    # Host slot mapping logic
├── config.example.toml
├── pyproject.toml
└── README.md
```

## Development

### Running tests

```bash
pip install -e ".[test]"
pytest -v
```

### Adding a new mouse

1. Find the mouse's VID and PID:

   ```bash
   lsusb | grep -i logitech
   ```

2. Update `config.toml` with the new PID.
3. The CHANGE_HOST (0x1814) command should work on any Logitech mouse that supports HID++ 2.0.

## License

MIT
