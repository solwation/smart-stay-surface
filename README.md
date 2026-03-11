# smart-stay-surface

Keep your screen awake while on AC power and your face is visible to the front camera. Automatically allows locking when it can't see you. A Linux equivalent of Samsung's "Smart Stay" feature, built for Microsoft Surface devices with IPU3 cameras.

## How it works

Every 30 seconds (configurable), the script:

1. Checks if the device is on AC power — does nothing on battery
2. Captures a frame from the front camera via `libcamera`
3. Runs face detection using `dlib`
4. If a face is found, inhibits GNOME idle/screensaver via DBus
5. Includes a grace period (2 checks / ~1 min) after the face disappears, so brief glances away don't trigger a lock

## Hardware

Built for Surface devices (tested on Surface Pro / Surface Book) that use Intel IPU3 cameras. These cameras require `libcamera` — standard V4L2/OpenCV capture doesn't work.

The script uses:
- **Front camera**: `\_SB_.PCI0.I2C2.CAMF` (libcamera index 1)
- **Power supply**: `/sys/class/power_supply/ADP1/online`

If your Surface has different paths, edit the constants at the top of the `smart-stay` script.

## Dependencies

```
python3-libcamera    # libcamera Python bindings (apt)
python3-dlib         # face detection (apt)
python3-numpy        # array handling (apt)
python3-dbus         # GNOME session DBus (apt)
```

Install with:
```bash
sudo apt install python3-libcamera python3-dlib python3-numpy python3-dbus
```

## Install

```bash
git clone git@github.com:solwation/smart-stay-surface.git
cd smart-stay-surface
./install.sh
```

This copies `smart-stay` to `~/bin/` and the systemd service to `~/.config/systemd/user/`.

## Usage

### Manual
```bash
smart-stay              # run in foreground (see logs live)
smart-stay --daemon     # run in background
smart-stay --stop       # stop background daemon
smart-stay --status     # check if running
```

### Systemd (auto-start on login)
```bash
systemctl --user enable smart-stay
systemctl --user start smart-stay
```

### Logs
```bash
cat ~/.cache/smart-stay.log
journalctl --user -u smart-stay    # if using systemd
```

## Configuration

Edit the constants at the top of `smart-stay`:

| Variable | Default | Description |
|---|---|---|
| `CHECK_INTERVAL` | `30` | Seconds between face checks |
| `GRACE_CHECKS` | `2` | Extra checks to keep screen on after face disappears |
| `AC_POWER_PATH` | `/sys/class/power_supply/ADP1/online` | Sysfs path for AC adapter |
| `CAMERA_INDEX` | `1` | libcamera camera index (front camera) |
| `CAPTURE_WIDTH` | `320` | Capture resolution width |
| `CAPTURE_HEIGHT` | `240` | Capture resolution height |

## Limitations

- **Surface / IPU3 only** — uses `libcamera` for camera access, which is needed for IPU3 cameras. Standard laptops with UVC cameras would need a different (simpler) capture approach using OpenCV directly.
- **GNOME only** — uses GNOME SessionManager DBus for idle inhibit. Other desktop environments would need a different inhibit mechanism.
- **Privacy** — frames are captured, processed in memory, and immediately discarded. Nothing is saved to disk.
