# smart-stay-surface

## Overview
A "Smart Stay" daemon for Linux Surface devices. Keeps the screen awake while on AC power and the front camera can see a face.

## Architecture
Single-file Python script (`smart-stay`) — no build system, no package manager, no virtualenv. System Python packages only.

**Camera capture**: Uses `libcamera` Python bindings (not OpenCV) because Surface IPU3 cameras don't support standard V4L2 capture. Must capture at 1280x720 minimum — the IPU3 ImgU produces all-black frames at lower resolutions (e.g. 320x240, 640x480). Captures NV12 frames via continuous streaming (multiple buffers pre-queued) with ~20 warmup frames to let the IPU3 auto-exposure converge. Must mmap the full `frame_size` (Y+UV planes together), not just `plane[0].length` — IPU3 DMA coherency requires the complete NV12 frame to be mapped or the Y plane reads as zeros. Extracts the Y plane as grayscale for face detection. Camera acquire has retry logic (3 attempts with 1s delay) because IPU3 needs time between release/acquire cycles.

**Face detection** (default mode): `dlib.get_frontal_face_detector()` (HOG-based) with upsample=1 for better detection at distance. Runs on full 1280x720 grayscale with histogram equalization applied first (numpy LUT-based) to handle backlighting and low-light conditions. Fast enough for a 30s polling loop.

**Motion detection**: Compares consecutive frames by downscaling to 320x240 and computing mean absolute pixel difference. Threshold of 5.0 (configurable via `MOTION_THRESHOLD`). Better than face detection when the camera sees a profile/side angle. At 30s intervals, even subtle movements (typing, shifting) register well above threshold.

**Adaptive mode**: Detection method is configurable per power state via `--ac-mode` and `--battery-mode` flags (choices: `face`, `motion`, `off`). Defaults: motion on AC, face on battery. The `--motion` flag is legacy shorthand for `--ac-mode motion --battery-mode off`.

**Idle inhibit**: GNOME SessionManager DBus (`org.gnome.SessionManager.Inhibit` with flag 8). Acquire/release pattern with a cookie.

**Power detection**: Reads `/sys/class/power_supply/ADP1/online` — returns "1" when on AC.

## Key files
- `smart-stay` — the main script, installed to `~/bin/`
- `smart-stay.service` — systemd user service, installed to `~/.config/systemd/user/`
- `install.sh` — copies both files to the right places. Accepts `--ac-mode`/`--battery-mode` to configure detection per power state, or `--motion` for legacy motion-only mode.

## Hardware specifics
- Front camera: libcamera index 1 (`\_SB_.PCI0.I2C2.CAMF`)
- Back camera: libcamera index 0 (`\_SB_.PCI0.I2C3.CAMR`)
- AC power: `/sys/class/power_supply/ADP1/online`
- Pixel format: NV12 (default from IPU3 pipeline), frame_size=1382400 at 1280x720 (921600 Y + 460800 UV). IPU3 ImgU requires >= 1280x720 — smaller resolutions produce all-black frames.
- Tuning files: `/usr/share/libcamera/ipa/ipu3/ov5693.yaml` (front) and `ov8865.yaml` (back) — must have proper IPA algorithm config (Agc, Awb, BlackLevelCorrection, ToneMapping) or frames will be black. See `fix-camera.sh`. Not needed on libcamera >= 0.7, whose `uncalibrated.yaml` already has them (the script detects this).

## Kernel 7.0 / Ubuntu 26.04
- Kernel 7.0's `dw9719` (rear VCM) driver has no I2C ID table, so the ipu-bridge-created `dw9719` client never binds → CIO2 async notifier never completes → **no** sensor gets media links → libcamera lists zero cameras (front included). `kernel7/fix-vcm.sh` installs a DKMS build with the ID table restored (`kernel7/dw9719-id-table.patch`, matches upstream master). Diagnose with `media-ctl -d /dev/media1 -p` (sensors with "0 link") and `modinfo -F alias dw9719` (no `i2c:` aliases).
- Sysfs `bind` returning ENODEV (the shell shows it as "I/O error") = no driver match, not a hardware problem. ftrace `function_graph` on `bind_store` works under Secure Boot lockdown (integrity mode); debugfs writes (dynamic_debug) do not.
- Rear ov8865 still yields black frames on 7.0: CIO2 receives 1632x1224-sized payloads regardless of the configured mode. Unresolved; the front camera is unaffected.

## Conventions
- No virtualenv — all deps are system apt packages
- Constants at top of script, no config file
- Logs to `~/.cache/smart-stay.log`, PID file at `~/.cache/smart-stay.pid`
- Debug mode: `smart-stay --debug-capture` saves 7 frames (every 5s) to `/tmp/smart-stay-debug/` with face detection overlays
