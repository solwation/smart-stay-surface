# Surface setup and restoration

Use this repository as a collection of optional Surface utilities. Install the
components your hardware needs after a clean Ubuntu installation; a kernel or
distribution upgrade may already include some fixes. The camera patches here target
IPU3 devices and the documented kernel regressions, not every Surface model.

Keep a private record of your chosen options and desktop settings outside this
public repo. Face enrollment is local and must be performed again after reinstall.
This guide restores software and configuration; it does not restore personal files,
LUKS keys, or TPM disk-unlock enrollment.

## Choose modules

| Need | Entry point | Selection and prerequisites |
|---|---|---|
| Camera stays awake while you are present | `install.sh` | Optional Smart Stay; libcamera/IPU3; also checks camera tuning and the dw9719 fix |
| No cameras on affected kernel 7.0 | `kernel7/fix-vcm.sh` | dw9719 matching fix; skips if matching is already present |
| Rear camera stalls after resolution changes | `kernel7/fix-ov8865.sh` | ov8865 stream-mode fix for the documented regression |
| Cameras in Chrome or Teams | `kernel7/chrome-camera.sh` | Run as desktop user; PipeWire/libcamera and browser setup |
| GNOME lock-screen face unlock | `kernel7/fix-ov7251.sh`, `face-unlock/install.sh` | Compatible IR camera, IR strobe fix, enrollment |
| IPTS touchscreen | `ipts/` | Patched driver sources, iptsd, optional model-specific config and IOMMU hook |
| Touch scrolling in terminal apps | `touch/install.sh` | Working iptsd virtual touchscreen first |
| Marvell Wi-Fi fails after suspend | `wifi/install.sh` | Only the affected mwifiex hardware |
| Keep work running with cover closed | `power/install.py --lid` | Optional GNOME/systemd service with local account and CPU settings |
| Suspend at a chosen battery percentage | `power/install.py --battery` | Independent optional UPower policy |
| Screen-lock timing | GNOME `gsettings` commands below | Per-user settings, independent of face unlock and Smart Stay |

There is no all-modules installation. The main installer is for Smart Stay and
its camera prerequisites; it does not install face unlock, touch gestures, Wi-Fi
workarounds, or power policy. Follow only the sections you need.

## Start on a clean installation

Run commands in a regular terminal under the desktop account you intend to use.
Install Git, clone the repo, and record the machine and kernel version:

```bash
sudo apt update
sudo apt install git
git clone https://github.com/solwation/smart-stay-surface.git
cd smart-stay-surface
uname -r
cat /sys/class/dmi/id/product_name
cat /sys/class/dmi/id/product_sku
```

If Secure Boot is enabled, locally built DKMS modules need an enrolled signing
certificate. A fresh installation may generate a new one. Check/enroll the Ubuntu
DKMS certificate when it exists, then complete enrollment in firmware at reboot:

```bash
mokutil --sb-state
sudo mokutil --import /var/lib/shim-signed/mok/MOK.der
```

Do not run the import if Secure Boot is off or the key is already enrolled. The
camera scripts install build dependencies and running-kernel headers. Follow their
error messages if DKMS signing setup is incomplete.

## Cameras and browser integration

Install camera tools and Smart Stay dependencies if you select Smart Stay:

```bash
sudo apt install libcamera-tools python3-libcamera python3-dlib python3-numpy python3-dbus python3-pil v4l-utils
```

For the documented dw9719 matching problem:

```bash
./kernel7/fix-vcm.sh
cam -l
```

For the documented rear-camera resolution problem, run `./kernel7/fix-ov8865.sh`.
Test a full-resolution capture afterwards. Driver fixes depend on the kernel and
sensor; patches that do not apply to a new kernel need review rather than forcing.

To configure browser integration:

```bash
./kernel7/chrome-camera.sh
```

Follow the script and the README's browser section for the Chrome PipeWire flag,
portal permission, and site permission. If camera access fails because WirePlumber
started before device permissions were granted, the README describes the `video`
group workaround and the need to log out/in after changing group membership.

Smart Stay itself is a separate choice:

```bash
./install.sh --ac-mode motion --battery-mode face
# After any required camera reboot, enable only if you want presence detection:
systemctl --user enable --now smart-stay
```

## Face unlock and screen lock

On a supported ov7251 IR camera, install the strobe fix, then the PAM integration:

```bash
./kernel7/fix-ov7251.sh
sudo ./face-unlock/install.sh
sudo face-unlock enroll "$USER"
sudo face-unlock test "$USER"
```

Use `sudo face-unlock add "$USER"` for additional lighting conditions or glasses.
Test on the lock screen with Super+L. The first login still requires the password;
face unlock is for an existing GNOME session. Password fallback remains available.
The README discusses the limits of this IR-based implementation.

Screen-lock timing is independent. These are example preferences, applied only if
you run the commands, as your desktop user without sudo:

```bash
# Lock when idle, after five minutes; no extra delay once the screen blanks
gsettings set org.gnome.desktop.screensaver lock-enabled true
gsettings set org.gnome.desktop.session idle-delay 300
gsettings set org.gnome.desktop.screensaver lock-delay 0
```

Use your preferred values. Smart Stay can inhibit idle locking while presence is
detected. Closed-lid power handling separately activates the GNOME screensaver.

## IPTS touch and gestures

The following is the optional stock-kernel path documented for Surface Pro 5 (1796)
on Ubuntu 26.04/kernel 7.0. Other models may need different presets or a kernel with
built-in IPTS support. Do not install the SP5 config or the MEI hook on unrelated
hardware. Prefer a distribution/linux-surface iptsd package where appropriate.

For the bundled patched driver on the affected kernel:

```bash
sudo apt install dkms make gcc rsync "linux-headers-$(uname -r)"
sudo ./ipts/apply-report-len-fix.sh
```

For an iptsd source build, keep the build tree in a persistent local directory.
This follows the [upstream v3.1.0 build instructions](https://github.com/linux-surface/iptsd/tree/v3.1.0)
and [dependency definitions](https://github.com/linux-surface/iptsd/blob/v3.1.0/src/meson.build),
with visualization tools disabled:

```bash
sudo apt install g++ meson ninja-build cmake pkg-config libcli11-dev libeigen3-dev libfmt-dev libinih-dev libmsgsl-dev libspdlog-dev
mkdir -p "$HOME/.local/src"
git clone --branch v3.1.0 --depth 1 https://github.com/linux-surface/iptsd.git "$HOME/.local/src/iptsd-v3.1.0"
meson setup "$HOME/.local/src/iptsd-v3.1.0/build" "$HOME/.local/src/iptsd-v3.1.0" --prefix=/usr -Ddebug_tools=[]
ninja -C "$HOME/.local/src/iptsd-v3.1.0/build"
sudo ninja -C "$HOME/.local/src/iptsd-v3.1.0/build" install
```

For SP5 with the bundled DKMS driver reporting vendor `0x045E`, select the matching
preset explicitly:

```bash
sudo install -d /etc/iptsd.d
sudo install -m644 ipts/system/surface-pro-5-ipts-dkms.conf /etc/iptsd.d/
```

If the documented MEI DMA/IOMMU fault affects that model, select its hook explicitly:

```bash
sudo install -m755 ipts/system/mei-iommu-identity /usr/local/sbin/
sudo install -m644 ipts/system/mei-iommu-identity.conf /etc/modprobe.d/
```

Reload udev rules and systemd units, then reboot so the driver, MEI hook, and hidraw
services start together:

```bash
sudo udevadm control --reload
sudo systemctl daemon-reload
sudo reboot
```

Verify touch before adding the optional gesture daemon:

```bash
systemctl status 'iptsd@*'
sudo ./touch/install.sh
```

This replaces reliance on an old temporary iptsd build directory. The individual
components have been used on the documented setup; the full fresh-install sequence
still needs an end-to-end test on a clean installation.

## Wi Fi and power policy

For affected Marvell Wi-Fi resume failures, select the workaround:

```bash
sudo ./wifi/install.sh
```

For optional closed-cover work and battery suspend, see the
[power module guide](power/README.md). Example choices:

```bash
sudo /usr/bin/python3 power/install.py --lid --user "$USER" --cpu-max-percent 35 --battery --suspend-at 10 --critical-at 15 --low-at 20
```

Check the lid close/open cycle and suspend/resume before relying on background
work. Power policy is independent of camera presence detection and face unlock.

## Keep a private restoration record

Back up the chosen command options, local power configuration, and GNOME setting
values alongside your own files. Do not commit a machine inventory or enrolled
face data to this public repo. Record which hardware-specific fixes were needed,
the kernel version, and any manual browser settings. After reinstall, select those
modules again, confirm each one works, and enroll your face anew.
