# smart-stay-surface

## Overview
A "Smart Stay" daemon for Linux Surface devices. Keeps the screen awake while on AC power and the front camera can see a face.

## Architecture
Single-file Python script (`smart-stay`) — no build system, no package manager, no virtualenv. System Python packages only.

**Camera capture**: Uses `libcamera` Python bindings (not OpenCV) because Surface IPU3 cameras don't support standard V4L2 capture. Must capture at 1280x720 minimum — the IPU3 ImgU produces all-black frames at lower resolutions (e.g. 320x240, 640x480). Captures NV12 frames via continuous streaming (multiple buffers pre-queued) with ~20 warmup frames to let the IPU3 auto-exposure converge. Must mmap the full `frame_size` (Y+UV planes together), not just `plane[0].length` — IPU3 DMA coherency requires the complete NV12 frame to be mapped or the Y plane reads as zeros. Extracts the Y plane as grayscale for face detection. Camera acquire has retry logic (3 attempts with 1s delay) because IPU3 needs time between release/acquire cycles.

**Face detection** (default mode): `dlib.get_frontal_face_detector()` (HOG-based) with upsample=1 for better detection at distance. Runs on full 1280x720 grayscale with histogram equalization applied first (numpy LUT-based) to handle backlighting and low-light conditions. Fast enough for a 30s polling loop.

**Motion detection**: Compares consecutive frames by downscaling to 320x240 and computing mean absolute pixel difference. Threshold of 5.0 (configurable via `MOTION_THRESHOLD`). Better than face detection when the camera sees a profile/side angle. At 30s intervals, even subtle movements (typing, shifting) register well above threshold.

**Adaptive mode**: Detection method is configurable per power state via `--ac-mode` and `--battery-mode` flags (choices: `face`, `motion`, `off`). Defaults: motion on AC, face on battery. The `--motion` flag is legacy shorthand for `--ac-mode motion --battery-mode off`.

**Camera busy**: `capture_frame()` raises `CameraBusy` when acquire still fails after its 3 retries (another process holds the camera; on IPU3 the front and rear cameras share media devices, so a rear-camera user blocks the front too). `run_loop` then pauses: inhibitor and grace untouched, `prev_frame` reset, logs only on pause/resume transitions. Other capture failures still return `None` (= nobody present).

**Idle inhibit**: GNOME SessionManager DBus (`org.gnome.SessionManager.Inhibit` with flag 8). Acquire/release pattern with a cookie.

**Power detection**: Reads `/sys/class/power_supply/ADP1/online` — returns "1" when on AC.

## Key files
- `smart-stay` — the main script, installed to `~/bin/`
- `smart-stay.service` — systemd user service, installed to `~/.config/systemd/user/`
- `ipts/`, `touch/` — Surface Pro 5 touchscreen on kernel 7.0 (unrelated to smart-stay itself, see README "Touchscreen")
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
- Rear ov8865 on 7.0 streamed with the *previous* session's mode (verified by reading 0x3808-0x380b/0x3814 over I2C while streaming): 7.0 dropped the `ov8865_mode_configure()` call from `ov8865_state_configure()` (set_fmt), relying on resume to program the mode, but the dw9719 VCM is a device-link consumer (`/sys/bus/i2c/devices/i2c-INT347A:00/consumer:*`, runtime_pm=1) and libcamera opens the VCM subdev — resuming the sensor — before setting the format. `kernel7/fix-ov8865.sh` + `ov8865-stream-mode.patch` (DKMS `ov8865-surface/1.0`) program the mode in `s_stream`. Full res works after it (libcamera still stream: 3200x2432 NV12, ~15 fps). Reloading ov8865 needs a dw9719 reload afterwards or the sensor keeps 0 media links.

- Chrome/Teams camera path: portal → PipeWire → libcamera (`kernel7/chrome-camera.sh`, README "Cameras in Chrome / Teams"). Module reloads drop cameras from PipeWire until WirePlumber restarts.

## Touchscreen (ipts/, touch/)
- `touch/touch-gestures` is a root system service (EVIOCGRAB on "IPTSD Virtual Touchscreen" + two uinput devices). State machine: HOLD (single finger held ≤ HOLD_MS waiting for a 2nd) → GESTURE (2 fingers buffered until DECIDE_MM movement) → SCROLL (wheel) or PASS (buffer replayed as touch — pinch, 3+ fingers, timeouts). Frames dropped during SCROLL mean the output device's MT slot/axis state can diverge from the source, so `forward()` always re-selects the slot and resends full contact state on a new tracking ID.
- The scroll device is an absolute pointer (ABS_X/Y + BTN_LEFT + wheels) so the wheel lands under the fingers; udev classes it as a mouse. Mapping assumes a single display.
- Wheel direction is "natural" (content follows fingers). GNOME's *mouse* natural-scroll setting applies to this device and would invert it.

## Conventions
- No virtualenv — all deps are system apt packages
- Constants at top of script, no config file
- Logs to `~/.cache/smart-stay.log`, PID file at `~/.cache/smart-stay.pid`
- Debug mode: `smart-stay --debug-capture` saves 7 frames (every 5s) to `/tmp/smart-stay-debug/` with face detection overlays
