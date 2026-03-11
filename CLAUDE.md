# smart-stay-surface

## Overview
A "Smart Stay" daemon for Linux Surface devices. Keeps the screen awake while on AC power and the front camera can see a face.

## Architecture
Single-file Python script (`smart-stay`) — no build system, no package manager, no virtualenv. System Python packages only.

**Camera capture**: Uses `libcamera` Python bindings (not OpenCV) because Surface IPU3 cameras don't support standard V4L2 capture. Captures NV12 frames and extracts the Y plane as grayscale for face detection.

**Face detection**: `dlib.get_frontal_face_detector()` (HOG-based). Runs on 320x240 grayscale — fast enough for a 30s polling loop.

**Idle inhibit**: GNOME SessionManager DBus (`org.gnome.SessionManager.Inhibit` with flag 8). Acquire/release pattern with a cookie.

**Power detection**: Reads `/sys/class/power_supply/ADP1/online` — returns "1" when on AC.

## Key files
- `smart-stay` — the main script, installed to `~/bin/`
- `smart-stay.service` — systemd user service, installed to `~/.config/systemd/user/`
- `install.sh` — copies both files to the right places

## Hardware specifics
- Front camera: libcamera index 1 (`\_SB_.PCI0.I2C2.CAMF`)
- Back camera: libcamera index 0 (`\_SB_.PCI0.I2C3.CAMR`)
- AC power: `/sys/class/power_supply/ADP1/online`
- Pixel format: NV12 (default from IPU3 pipeline)

## Conventions
- No virtualenv — all deps are system apt packages
- Constants at top of script, no config file
- Logs to `~/.cache/smart-stay.log`, PID file at `~/.cache/smart-stay.pid`
