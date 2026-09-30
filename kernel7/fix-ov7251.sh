#!/bin/bash
# Enable the IR illuminator of the Windows Hello camera (ov7251) on Surface IPU3 devices
#
# The IR camera (ACPI INT347E, ov7251) streams on kernel 7.0, but its IR flood
# LED stays dark: it is not a GPIO of the INT3472 PMIC but hangs off the
# sensor's strobe output, which the upstream driver never enables. Without it
# the camera only sees ambient IR (near-black frames indoors).
#
# This script downloads ov7251.c for the running kernel's version, patches
# s_stream to route the strobe to the LED pad (0x3005 = 0x08) and fire it
# every frame (0x3b81 = 0xff) -- only for INT347E, disable with the module
# parameter ir_strobe=0 -- and installs it via DKMS (signed with the Ubuntu MOK
# key, like fix-vcm.sh; PCR 7 unaffected). Used by face-unlock/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG=ov7251-surface
VER=1.0
KREL="$(uname -r)"
KVER="$(echo "$KREL" | cut -d. -f1,2)"   # e.g. 7.0

echo "Installing build dependencies..."
sudo apt-get install -y dkms make "linux-headers-$KREL" patch curl

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Fetching ov7251.c for v$KVER..."
curl -sfL "https://raw.githubusercontent.com/torvalds/linux/v$KVER/drivers/media/i2c/ov7251.c" \
    -o "$WORK/ov7251.c"

if grep -q 'OV7251_STROBE\|0x3b81, 0xff' "$WORK/ov7251.c"; then
    echo "ov7251 in v$KVER already drives the strobe -- no fix needed."
    exit 0
fi
(cd "$WORK" && patch -p1 < "$SCRIPT_DIR/ov7251-ir-strobe.patch")

cat > "$WORK/Makefile" << 'MK'
obj-m := ov7251.o
MK

cat > "$WORK/dkms.conf" << CONF
PACKAGE_NAME="$PKG"
PACKAGE_VERSION="$VER"
BUILT_MODULE_NAME[0]="ov7251"
DEST_MODULE_LOCATION[0]="/updates/dkms"
MAKE[0]="make -C \${kernel_source_dir} M=\${dkms_tree}/\${PACKAGE_NAME}/\${PACKAGE_VERSION}/build modules"
CLEAN="make -C \${kernel_source_dir} M=\${dkms_tree}/\${PACKAGE_NAME}/\${PACKAGE_VERSION}/build clean"
AUTOINSTALL="yes"
CONF

echo "Installing DKMS module $PKG/$VER..."
sudo dkms remove "$PKG/$VER" --all 2>/dev/null || true
sudo rm -rf "/usr/src/$PKG-$VER"
sudo mkdir -p "/usr/src/$PKG-$VER"
sudo cp "$WORK/ov7251.c" "$WORK/Makefile" "$WORK/dkms.conf" "/usr/src/$PKG-$VER/"
sudo dkms install "$PKG/$VER"

# libcamera doesn't use the IR camera (mono sensor, no IPU3 pipeline support),
# so the module can normally be reloaded right away -- after unbinding, since
# the CIO2 v4l2_device holds a module reference. The other cameras survive it.
DEV=i2c-INT347E:00
[[ -e /sys/bus/i2c/drivers/ov7251/$DEV ]] && echo "$DEV" | sudo tee /sys/bus/i2c/drivers/ov7251/unbind >/dev/null
if sudo modprobe -r ov7251 2>/dev/null; then
    sudo modprobe ov7251
    sleep 2
    echo "Done. $(modinfo -F filename ov7251)"
else
    echo "Done. ov7251 is in use -- reboot to load the fixed module."
fi
