# smart-stay-surface

Keep your screen awake while on AC power and your face is visible to the front camera. Automatically allows locking when it can't see you. A Linux equivalent of Samsung's "Smart Stay" feature, built for Microsoft Surface devices with IPU3 cameras.

## How it works

Every 30 seconds (configurable), the script:

1. Checks power state (AC or battery) and selects the configured detection mode
2. Captures a 1280x720 frame from the front camera via `libcamera`
3. Detects presence using the active mode:
   - **Face mode**: histogram equalization + dlib HOG detection (frontal faces)
   - **Motion mode**: frame-to-frame pixel difference — works at any angle
   - **Off**: skips detection entirely (e.g. to save battery)
4. If presence is detected, inhibits GNOME idle/screensaver via DBus
5. Includes a grace period (2 checks / ~1 min) after presence is lost, so brief glances away don't trigger a lock

By default, motion detection runs on AC and face detection on battery. This is configurable via `--ac-mode` and `--battery-mode`.

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
sudo apt install python3-libcamera python3-dlib python3-numpy python3-dbus python3-pil
```

## Install

```bash
git clone https://github.com/solwation/smart-stay-surface.git
cd smart-stay-surface
./install.sh                                    # default (AC=motion, battery=face)
./install.sh --ac-mode face --battery-mode off  # face on AC only, skip on battery
./install.sh --motion                           # legacy: motion on AC, skip on battery
sudo reboot                                     # required to reset camera sensors
```

After reboot:
```bash
systemctl --user enable smart-stay
systemctl --user start smart-stay
```

The installer:
1. Fixes the IPU3 camera tuning files (see [Camera Fix](#camera-fix) below)
2. Copies `smart-stay` to `~/bin/`
3. Installs the systemd user service to `~/.config/systemd/user/`

### Camera Fix

Surface IPU3 cameras require proper libcamera IPA tuning files to function. The default files shipped with `python3-libcamera` are often symlinks to `uncalibrated.yaml`, which lacks the required algorithm configuration. Without this fix, **the cameras produce completely black frames**.

`fix-camera.sh` (run automatically by `install.sh`) writes minimal working tuning files for both sensors:
- `/usr/share/libcamera/ipa/ipu3/ov5693.yaml` (front camera)
- `/usr/share/libcamera/ipa/ipu3/ov8865.yaml` (back camera)

These enable the essential IPA algorithms: auto-gain (Agc), auto-white-balance (Awb), black level correction, and tone mapping. A reboot is required after the fix to power-cycle the camera sensors.

You can run `fix-camera.sh` independently if needed:
```bash
./fix-camera.sh
sudo reboot
```

### Ubuntu 26.04 / kernel 7.0

On Ubuntu 26.04 (kernel 7.0, libcamera 0.7) the setup differs from older releases:

- **No cameras at all** (`cam -l` lists nothing, `media-ctl -d /dev/media1 -p` shows the sensors with `0 link`). Kernel 7.0 dropped the I2C ID table from the `dw9719` driver for the rear camera's focus motor (VCM). The VCM never binds, and because the IPU3 CIO2 driver waits for *every* subdevice before linking any sensor, the front camera disappears too. `kernel7/fix-vcm.sh` (run automatically by `install.sh`) rebuilds `dw9719` with the ID table restored, as in upstream master, and installs it via DKMS. It is a no-op on kernels that don't need it.
  - Under Secure Boot, DKMS signs the module with the Ubuntu MOK key (`/var/lib/shim-signed/mok/MOK.der`), which must already be enrolled. Signing modules with an enrolled MOK does not change PCR 7, so TPM2 disk auto-unlock bound to PCR 7 keeps working.
  - DKMS rebuilds the module automatically on kernel updates. Once Ubuntu ships a kernel with the fix, the script detects it and skips.
- **The tuning fix is no longer needed.** libcamera 0.7's `uncalibrated.yaml` already enables Agc/Awb/BlackLevelCorrection/ToneMapping, and `fix-camera.sh` detects this and skips.
- **The rear camera (ov8865) still produces black frames.** The sensor keeps sending 1632x1224-sized frames whatever mode is configured (`ipu3-cio2: payload length is 10340352, received 2585088`). smart-stay only uses the front camera, so this doesn't matter here.
- **No reboot needed** after `fix-vcm.sh`: reloading the module is enough.

Useful diagnostics on this setup:

```bash
cam -l                                  # cameras libcamera can see
media-ctl -d /dev/media1 -p | grep entity   # sensors should have "1 link"
modinfo -F alias dw9719 | grep i2c      # empty = unfixed kernel 7.0 driver
cam --camera=2 --capture=30 --stream=role=viewfinder,width=1280,height=720 --file=/tmp/f-#.bin
```

Note that `cam` requires `=` for its optional-argument flags (`--capture=30`, not `-C 30`).

## Usage

### Manual
```bash
smart-stay                                    # default (AC=motion, battery=face)
smart-stay --ac-mode face --battery-mode off  # face on AC only, skip on battery
smart-stay --motion                           # legacy: motion on AC, skip on battery
smart-stay --daemon                           # run as background daemon
smart-stay --stop                             # stop background daemon
smart-stay --status                           # check if running
smart-stay --debug-capture                    # test frames with detection overlay
```

### Systemd (auto-start on login)
```bash
systemctl --user enable smart-stay
systemctl --user start smart-stay
```

The installer configures the systemd service with the mode flags you pass. To change modes later, re-run `./install.sh` with different flags, or edit `~/.config/systemd/user/smart-stay.service` and add `--ac-mode`/`--battery-mode` to the `ExecStart` line.

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
| `CAPTURE_WIDTH` | `1280` | Capture resolution width (IPU3 needs >= 1280x720) |
| `CAPTURE_HEIGHT` | `720` | Capture resolution height |
| `MOTION_THRESHOLD` | `5.0` | Mean pixel diff to count as motion (0-255 scale) |

## Limitations

- **Surface / IPU3 only** — uses `libcamera` for camera access, which is needed for IPU3 cameras. Standard laptops with UVC cameras would need a different (simpler) capture approach using OpenCV directly.
- **GNOME only** — uses GNOME SessionManager DBus for idle inhibit. Other desktop environments would need a different inhibit mechanism.
- **Minimum resolution** — the IPU3 ImgU requires >= 1280x720 capture resolution. Lower resolutions produce black frames.
- **Privacy** — frames are captured, processed in memory, and immediately discarded. Nothing is saved to disk (except in `--debug-capture` mode).

## Touchscreen (IPTS) on kernel 7.0

Not part of smart-stay, but lives here because it's the same machine. Getting full touch
(tap, drag, two-finger scroll in *every* app, pinch-zoom, stylus) on a Surface Pro 5 with the
stock Ubuntu 26.04 kernel takes four pieces:

1. **ipts driver** — out-of-tree DKMS (`linux-surface/intel-precise-touch`). On kernel 7.0 its
   raw data report is 3 bytes shorter than its own HID descriptor declares, which 7.0's
   `hid_report_raw_event()` now rejects (`Event data for report 65 was too short (7487 vs 7484)`,
   `ipts: Failed to process buffer: -22`) — everything looks alive but no touch arrives.
   `ipts/ipts-kernel7-report-len.patch` fixes it; `pkexec ipts/apply-report-len-fix.sh`
   rebuilds and reloads the patched source in `ipts/src/`.
2. **IOMMU identity for the MEI group** — otherwise iptsd's DMA mode faults
   (`DMAR … [00:16.4] PTE Read access is not set`). `ipts/system/mei-iommu-identity` is a
   modprobe `install` hook (`ipts/system/mei-iommu-identity.conf` → `/etc/modprobe.d/`) that
   switches IOMMU group 00:16.0+00:16.4 to `identity` before `mei_me` binds. Only that group is
   affected; PCR 7 is not.
3. **iptsd** v3.1.0 built from upstream (`linux-surface/iptsd`), with
   `ipts/system/surface-pro-5-ipts-dkms.conf` in `/etc/iptsd.d/` (the DKMS driver reports vendor
   `0x045E`, not the `0x1B96` the presets match).
4. **touch-gestures** (`touch/`) — GNOME hands touchscreen input straight to apps, and apps
   without their own touch scrolling (VTE terminals such as Ptyxis) can't be scrolled. This
   daemon grabs iptsd's virtual touchscreen and re-emits it: one finger and 3+ fingers pass
   through untouched, two fingers moving together become hi-res wheel events (with kinetic
   scrolling) at the fingers, and two fingers pinching are replayed as touch so apps zoom
   natively. Install with `pkexec touch/install.sh` (`--uninstall` to remove). Tunables are
   constants at the top of `touch/touch-gestures`.

```bash
journalctl -b -k | grep -iE 'ipts|too short|DMAR'   # driver / IOMMU problems
systemctl status 'iptsd@*' touch-gestures           # daemons
grep -A1 -E 'IPTSD|Touch Gestures' /proc/bus/input/devices
```

## License

[MIT](LICENSE) — Olof Wingren
