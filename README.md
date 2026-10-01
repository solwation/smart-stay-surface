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

- **No cameras at all** (`cam -l` lists nothing, `media-ctl -p` on the CIO2 media device shows the sensors with `0 link`). Kernel 7.0 dropped the I2C ID table from the `dw9719` driver for the rear camera's focus motor (VCM). The VCM never binds, and because the IPU3 CIO2 driver waits for *every* subdevice before linking any sensor, the front camera disappears too. `kernel7/fix-vcm.sh` (run automatically by `install.sh`) rebuilds `dw9719` with the ID table restored, as in upstream master, and installs it via DKMS. It is a no-op on kernels that don't need it.
  - Under Secure Boot, DKMS signs the module with the Ubuntu MOK key (`/var/lib/shim-signed/mok/MOK.der`), which must already be enrolled. Signing modules with an enrolled MOK does not change PCR 7, so TPM2 disk auto-unlock bound to PCR 7 keeps working.
  - DKMS rebuilds the module automatically on kernel updates. Once Ubuntu ships a kernel with the fix, the script detects it and skips.
- **The tuning fix is no longer needed.** libcamera 0.7's `uncalibrated.yaml` already enables Agc/Awb/BlackLevelCorrection/ToneMapping, and `fix-camera.sh` detects this and skips.
- **Rear camera (ov8865) switching between resolutions gives black frames or a stalled stream** (`ipu3-cio2: payload length is 10340352, received 2585088` when full res is requested, `payload length is 2585088, received 2588672` + one frame the other way). Since 7.0, ov8865 only writes the sensor mode to the hardware on power-up, and `set_fmt` no longer programs a powered sensor. But the dw9719 VCM is a device-link consumer of the sensor, and libcamera opens the VCM (powering the sensor up) *before* it sets the sensor format, so the sensor streams with the previous session's mode. `kernel7/fix-ov8865.sh` installs a DKMS build of ov8865 (`kernel7/ov8865-stream-mode.patch`) that programs the current mode at stream start. Not needed for smart-stay (front camera only). The script reloads `dw9719` after `ov8865`, because the VCM doesn't re-register with the sensor's async notifier on its own (sensor left with `0 link`).
- **No reboot needed** after `fix-vcm.sh`: reloading the module is enough.

Useful diagnostics on this setup:

```bash
cam -l                                  # cameras libcamera can see
# the CIO2 media device number varies between boots
media-ctl -d $(dirname $(grep -l CIO2 /sys/bus/media/devices/*/model) | sed s,.*/,/dev/,) -p | grep entity   # sensors should have "1 link"
modinfo -F alias dw9719 | grep i2c      # empty = unfixed kernel 7.0 driver
cam --camera=2 --capture=30 --stream=role=viewfinder,width=1280,height=720 --file=/tmp/f-#.bin
```

Note that `cam` requires `=` for its optional-argument flags (`--capture=30`, not `-C 30`).

### Cameras in Chrome / Teams

IPU3 cameras can't be used through plain V4L2, so browsers only see them through the camera portal → PipeWire → libcamera. `kernel7/chrome-camera.sh` (run as your user) does the system side; Chrome needs two manual steps:

1. **PipeWire libcamera plugin** (`libspa-0.2-libcamera`). `wpctl status` should list `ov5693`/`ov8865` as `[libcamera]` devices. Reloading camera modules (`fix-vcm.sh`, `fix-ov8865.sh`) drops them until `systemctl --user restart wireplumber`; both scripts now do that.
2. **Chrome flag** `chrome://flags/#enable-webrtc-pipewire-camera` → Enabled, then `chrome://restart`.
3. **Portal permission.** The portal's permission dialog fails for Chrome web apps (`xdg-desktop-portal: … Only the focused app is allowed to show a system access dialog`) because the PWA window's app ID differs from the requesting process (`com.google.Chrome`). The script grants it directly in the permission store; revoke in Settings → Privacy & Security → Camera.
4. **Per-site permission.** A site that asked for permissions while no camera was available (Teams asked for the microphone only) won't ask again. Allow the camera in `chrome://settings/content/siteDetails?site=https://teams.cloud.microsoft` and reload.

`chrome://settings/content/camera` listing *Built-in Front Camera* / *Built-in Back Camera* means everything up to Chrome works. libcamera cameras are exclusive: only one app can use a camera at a time. smart-stay pauses while another app uses either camera (see Limitations). If a call starts during smart-stay's ~2 s capture, the browser may briefly report the camera as busy; retry.

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
- **Pauses while the camera is in use** — libcamera cameras are exclusive, so while another app (a video call, the Camera app) uses either camera, smart-stay can't capture. It detects this (acquire fails after its retries; on IPU3 both cameras share the CIO2/ImgU media devices, so the rear camera counts too), logs `Camera in use by another app — pausing detection`, and leaves the inhibitor and grace period untouched until the camera is free again. In motion mode the first frame after a pause counts as motion.
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

## Wifi after suspend (mwifiex)

The Marvell 88W8897 (`mwifiex_pcie`, PCI `0000:01:00.0`) sometimes does not wake up from
s2idle: `Unable to change power state from D3hot to D0`, `Firmware didn't wake up`, then an
endless stream of `cmd_wait_q terminated: -110` — wifi is dead until reboot. Kernel 7.0 lacks
linux-surface's mwifiex patches, so `wifi/` works around it:

- `mwifiex-sleep` (→ `/usr/lib/systemd/system-sleep/`) unloads `mwifiex_pcie` before suspend
  and reloads it after resume (fresh firmware download). Reconnecting takes a few seconds.
- `wifi-reset` (→ `/usr/local/sbin/`) reloads the driver, falling back to PCI remove + rescan.
  Run `pkexec wifi-reset` if wifi dies anyway — no reboot needed. Log: `journalctl -t wifi-reset`.

```bash
pkexec ~/Documents/smart-stay-surface/wifi/install.sh               # install / update
pkexec ~/Documents/smart-stay-surface/wifi/install.sh --uninstall
```

## Face unlock (IR camera)

Not part of smart-stay either: `face-unlock/` unlocks the GNOME lock screen with the
Windows Hello IR camera, like Howdy but working with IPU3. Two things stand in the way on
stock Ubuntu 26.04:

1. **The IR camera is invisible to libcamera.** The ov7251 (ACPI `INT347E`) is a mono sensor
   and libcamera's IPU3 pipeline only drives Bayer sensors, so `cam -l` lists only the front
   and rear cameras. It doesn't need an ISP though: `face-unlock` enables the (off by default,
   non-persistent) `ov7251 → ipu3-csi2 2` media link and reads 640x480 IPU3-packed 10-bit
   greyscale straight from CIO2 (video node `ipu3-cio2 2`, `ip3y`) with `v4l2-ctl`. The
   `/dev/media*`, `/dev/video*` and `/dev/v4l-subdev*` numbers change between boots, so
   `face-unlock` looks the nodes up by name in sysfs.
2. **The IR illuminator stays dark.** It is not a GPIO of the INT3472 (the IR sensor's
   `SKC2` only has clock-enable and reset) but hangs off the sensor's strobe output, which the
   upstream driver never enables — frames are near-black indoors. `kernel7/fix-ov7251.sh`
   installs DKMS `ov7251-surface/1.0` (`kernel7/ov7251-ir-strobe.patch`), which routes the
   strobe to the LED pad (`0x3005 = 0x08`) and fires it every frame (`0x3b81 = 0xff`) while
   streaming, only for `INT347E`. Module parameter `ir_strobe=0` turns it off. Values as found
   by linux-surface ([#739](https://github.com/linux-surface/linux-surface/issues/739),
   [#2252](https://github.com/linux-surface/linux-surface/pull/2252)).

Recognition uses OpenCV (apt `python3-opencv`; dlib isn't packaged for 26.04): YuNet finds
the face (all four rotations are tried, the tablet may be held any way and the sensor is mounted
rotated), CLAHE evens out the IR exposure, SFace turns it into an embedding that is
compared (cosine) against the enrolled samples. Unlock needs 2 frames ≥ 0.5 within 3.5 s
(own face scores ~0.7–0.77 here; OpenCV's same-person threshold is 0.363).

```bash
pkexec kernel7/fix-ov7251.sh          # IR illuminator (DKMS, MOK-signed, PCR 7 unaffected)
pkexec face-unlock/install.sh         # deps, models (sha256-pinned), PAM line in gdm-password
pkexec face-unlock enroll             # ~8 s, look at the camera and move your head a little
pkexec face-unlock add                # extra samples (glasses, other light) on top
pkexec face-unlock test               # per-frame scores
pkexec face-unlock/install.sh --uninstall   # remove the PAM line again
journalctl -t face-unlock             # match / no match log
```

How it hooks in: `auth [success=done default=ignore] pam_exec.so quiet stdout
/usr/local/bin/face-unlock auth` right before `@include common-auth` in
`/etc/pam.d/gdm-password`. A match ends the auth stack; anything else — no face, not enrolled,
camera error, even a crash — returns failure and GDM asks for the password as usual.

Deliberate limits:

- **Lock screen only.** It only answers when the user already has a local graphical session;
  the first login after boot always takes the password (that's what unlocks the GNOME
  keyring). `sudo`/`pkexec` are not hooked up.
- **Not Windows Hello grade.** IR defeats photos shown on a screen (LCDs are dark in IR) and
  makes lighting consistent, but there is no depth or liveness check: a good IR-bright
  print of your face might pass. The enrolled embeddings live in `/etc/face-unlock/<user>.npy`
  (root, 0600). Weigh this against what the lock screen protects.

## License

[MIT](LICENSE) — Olof Wingren
