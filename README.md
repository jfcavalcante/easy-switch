# kvmsync

Synchronize Bluetooth host switching between a multi-host keyboard and a multi-host mouse across Linux and Windows.

When you press **fn+1** on your keyboard to switch to Linux, the mouse automatically switches to the corresponding Bluetooth slot - and vice versa.

## How It Works

1. Each machine runs its own `kvmsync` daemon.
2. Each daemon polls whether the keyboard is connected to its machine:
   - Linux: the keyboard's `Connected` property in **BlueZ** (D-Bus).
   - Windows: whether the keyboard's HID interfaces are enumerated by **hidapi**.
3. When the keyboard **leaves** a machine (absent for 1s), that machine still owns the mouse, so it sends a **HID++ CHANGE_HOST** command moving the mouse to the other host's slot.
4. When the keyboard **arrives**, the daemon also sends CHANGE_HOST for its own slot (usually a no-op, the other daemon already moved the mouse).

Both daemons must be running: the machine the keyboard leaves is the one that moves the mouse.

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

2. Install the dependencies. `hidapi` is used through its `hidraw` backend (the `hid` module is libusb-only and cannot see Bluetooth devices); `dbus-python` reads BlueZ:

   ```bash
   sudo apt install python3-dbus   # Debian/Ubuntu
   pip install hidapi
   ```

3. Grant access to the mouse's hidraw device (one-time setup):

   ```bash
   sudo cp systemd/70-kvmsync-hidraw.rules /etc/udev/rules.d/
   sudo udevadm control --reload
   sudo udevadm trigger
   ```

   The rule matches the MX Vertical (`046D:B020`) over USB and Bluetooth. Adjust the product ID for another mouse. Note that `ATTRS{idVendor}` does not work here: it only exists for USB devices.

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

2. Create the configuration file (same slots as on Linux):

   ```powershell
   Copy-Item config.example.toml config.toml
   ```

3. Run the daemon as a regular user (no admin required):

   ```powershell
   python -m kvmsync -c config.toml -v
   ```

4. Run it like a systemd service: a Task Scheduler task that starts at logon, without a console window, restarts on failure and logs to `%LOCALAPPDATA%\kvmsync\kvmsync.log`:

   ```powershell
   powershell -ExecutionPolicy Bypass -File windows\install-task.ps1
   ```

   Manage it with `Start-ScheduledTask kvmsync` / `Stop-ScheduledTask kvmsync`, follow the log with `Get-Content $env:LOCALAPPDATA\kvmsync\kvmsync.log -Wait -Tail 50`, and remove it with `install-task.ps1 -Uninstall`.

## Configuration

Copy `config.example.toml` to `config.toml` and adjust:

```toml
[mouse]
# Logitech VID (always 0x046D)
vendor_id = 0x046D
# Mouse product ID - verify with lsusb (Linux) or Device Manager (Windows)
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
2. Switch the mouse manually to the slot connected to your Linux machine - note the slot number (1, 2, or 3).
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
ExecStart=/usr/bin/python3 -m kvmsync -c /etc/kvmsync/config.toml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`systemd/kvmsync.service` in this repo is a ready-made version. The config file must be readable by the service user (`sudo chmod 644 /etc/kvmsync/config.toml`).

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
Linux:   BlueZ Connected (polled)  ─┐
                                    ├─> presence.py (debounce) ─> mouse.py ─> HID++ CHANGE_HOST ─> mouse
Windows: hidapi enumerate (polled) ─┘
```

Key design decisions:

- **No network coordination between machines** - only the machine that currently holds the mouse can talk to it, and that is exactly the machine the keyboard just left.
- **Polling instead of event APIs** - BlueZ signals need a GLib main loop, and Windows SetupAPI/WMI either never fire for a Bluetooth host switch or lag several seconds. Polling every 200ms is cheap and reacts in about 1s.

## Project Structure

```
kvmsync/
├── kvmsync/
│   ├── __init__.py
│   ├── __main__.py        # CLI entry point
│   ├── config.py          # TOML configuration loader
│   ├── daemon.py          # Main daemon loop
│   ├── events.py          # Keyboard watcher base class
│   ├── presence.py        # Shared debounced presence watcher
│   ├── events_linux.py    # Presence via BlueZ D-Bus
│   ├── events_windows.py  # Presence via hidapi
│   ├── mouse.py           # Sends CHANGE_HOST via hidapi
│   ├── hidpp.py           # HID++ 2.0 protocol (CHANGE_HOST)
│   └── log.py             # Logging setup
├── systemd/               # systemd unit and udev rule (Linux)
├── tests/
│   ├── test_config.py         # Config loading and validation
│   ├── test_hidpp.py          # HID++ packet builder/parser
│   ├── test_mapping.py        # Host slot mapping logic
│   ├── test_events_linux.py   # Linux watcher state machine
│   └── test_events_windows.py # Windows watcher state machine
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
