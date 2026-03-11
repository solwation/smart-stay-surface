# smart-stay-surface

## Overview
A "Smart Stay" daemon for Linux Surface devices. Keeps the screen awake while on AC power and the front camera can see a face.

## Architecture
Single-file Python script (`smart-stay`) — no build system, no package manager, no virtualenv. System Python packages only.

**Camera capture**: Uses `libcamera` Python bindings (not OpenCV) because Surface IPU3 cameras don't support standard V4L2 capture. Captures NV12 frames via continuous streaming (multiple buffers pre-queued) with ~20 warmup frames to let the IPU3 auto-exposure converge. Must mmap the full `frame_size` (Y+UV planes together), not just `plane[0].length` — IPU3 DMA coherency requires the complete NV12 frame to be mapped or the Y plane reads as zeros. Extracts the Y plane as grayscale for face detection.

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
- Pixel format: NV12 (default from IPU3 pipeline), frame_size=115200 at 320x240 (76800 Y + 38400 UV)
- Tuning files: `/usr/share/libcamera/ipa/ipu3/ov5693.yaml` (front) and `ov8865.yaml` (back) — must have proper IPA algorithm config (Agc, Awb, BlackLevelCorrection, ToneMapping) or frames will be black. See `~/fix-camera.sh`.

## Conventions
- No virtualenv — all deps are system apt packages
- Constants at top of script, no config file
- Logs to `~/.cache/smart-stay.log`, PID file at `~/.cache/smart-stay.pid`
- Debug mode: `smart-stay --debug-capture` saves 7 frames (every 5s) to `/tmp/smart-stay-debug/` with face detection overlays
