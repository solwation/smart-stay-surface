#!/bin/bash
# Fix rear camera (ov8865) mode switching on kernel 7.0 (Ubuntu 26.04) for Surface IPU3 devices
#
# Since kernel 7.0, ov8865 only writes the sensor mode to the hardware when it
# is powered up (runtime resume); set_fmt no longer programs a powered sensor.
# But the dw9719 VCM is a device-link consumer of the sensor, and libcamera
# opens the VCM subdev -- which powers the sensor up -- *before* it sets the
# sensor format. The sensor then streams with the mode of the previous
# session: switching between 1280x720 (binned 1632x1224) and full-resolution
# 3264x2448 yields black frames or a stalled stream until the next run.
#
# Symptom:  dmesg: "ipu3-cio2 ...: payload length is 10340352, received 2585088"
#           (full res requested, sensor still sending 1632x1224) or
#           "payload length is 2585088, received 2588672" plus a stalled stream.
#
# This script downloads ov8865.c for the running kernel's version, patches
# s_stream to program the current mode before streaming, and installs it via
# DKMS (signed with the Ubuntu MOK key, like fix-vcm.sh; PCR 7 unaffected).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG=ov8865-surface
VER=1.0
KREL="$(uname -r)"
KVER="$(echo "$KREL" | cut -d. -f1,2)"   # e.g. 7.0

echo "Installing build dependencies..."
sudo apt-get install -y dkms make "linux-headers-$KREL" patch curl

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Fetching ov8865.c for v$KVER..."
curl -sfL "https://raw.githubusercontent.com/torvalds/linux/v$KVER/drivers/media/i2c/ov8865.c" \
    -o "$WORK/ov8865.c"

if grep -q 'State will be configured at first power on otherwise' "$WORK/ov8865.c"; then
    echo "ov8865 in v$KVER still programs the mode in set_fmt -- no fix needed."
    exit 0
fi
(cd "$WORK" && patch -p1 < "$SCRIPT_DIR/ov8865-stream-mode.patch")

cat > "$WORK/Makefile" << 'MK'
obj-m := ov8865.o
MK

cat > "$WORK/dkms.conf" << CONF
PACKAGE_NAME="$PKG"
PACKAGE_VERSION="$VER"
BUILT_MODULE_NAME[0]="ov8865"
DEST_MODULE_LOCATION[0]="/updates/dkms"
MAKE[0]="make -C \${kernel_source_dir} M=\${dkms_tree}/\${PACKAGE_NAME}/\${PACKAGE_VERSION}/build modules"
CLEAN="make -C \${kernel_source_dir} M=\${dkms_tree}/\${PACKAGE_NAME}/\${PACKAGE_VERSION}/build clean"
AUTOINSTALL="yes"
CONF

echo "Installing DKMS module $PKG/$VER..."
sudo dkms remove "$PKG/$VER" --all 2>/dev/null || true
sudo rm -rf "/usr/src/$PKG-$VER"
sudo mkdir -p "/usr/src/$PKG-$VER"
sudo cp "$WORK/ov8865.c" "$WORK/Makefile" "$WORK/dkms.conf" "/usr/src/$PKG-$VER/"
sudo dkms install "$PKG/$VER"

# Reload ov8865, then dw9719: the VCM is an async sub-device of the sensor and
# doesn't re-register on its own, which leaves the sensor with 0 media links
# (rear camera missing from `cam -l`) until the VCM driver is reloaded too.
if sudo modprobe -r ov8865 2>/dev/null; then
    sudo modprobe ov8865
    sudo modprobe -r dw9719 2>/dev/null && sudo modprobe dw9719
    sleep 3
    echo ""
    cam -l 2>/dev/null || true
    echo ""
    echo "Done. If the rear camera is not listed above, reboot."
else
    echo "Done. ov8865 is in use -- reboot to load the fixed module."
fi
