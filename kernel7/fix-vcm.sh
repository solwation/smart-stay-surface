#!/bin/bash
# Fix "no cameras found" on kernel 7.0 (Ubuntu 26.04) for Surface IPU3 devices
#
# Kernel 7.0 dropped the I2C ID table from the dw9719 VCM (rear camera focus
# motor) driver. On ACPI systems ipu-bridge instantiates the VCM as a plain
# "dw9719" I2C client, which then never matches and the module never
# autoloads. The CIO2 async notifier waits for every subdevice, so without
# the VCM *no* sensor gets linked -- libcamera lists zero cameras, including
# the front camera.
#
# Symptom:  cam -l            -> "Available cameras:" (empty)
#           media-ctl -d /dev/media1 -p  -> sensors show "0 link"
#
# This script downloads dw9719.c for the running kernel's version, restores
# the ID table (as in upstream master) and installs it via DKMS. DKMS signs
# the module with the Ubuntu MOK key, so it loads under Secure Boot as long
# as /var/lib/shim-signed/mok/MOK.der is enrolled. No new MOK enrollment is
# needed if it already is, and PCR 7 (TPM auto-unlock) is not affected.
# DKMS rebuilds the module on every kernel update.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG=dw9719-surface
VER=1.0
KREL="$(uname -r)"
KVER="$(echo "$KREL" | cut -d. -f1,2)"   # e.g. 7.0

if modinfo -F alias dw9719 2>/dev/null | grep -q '^i2c:dw9719$'; then
    echo "dw9719 already has an I2C ID table -- no fix needed."
    exit 0
fi

if [[ -d /sys/firmware/efi ]] && mokutil --sb-state 2>/dev/null | grep -q enabled; then
    if ! mokutil --test-key /var/lib/shim-signed/mok/MOK.der 2>/dev/null | grep -q 'already enrolled'; then
        echo "Secure Boot is on but the DKMS MOK key is not enrolled."
        echo "Enroll it first (sudo mokutil --import /var/lib/shim-signed/mok/MOK.der, then reboot)."
        exit 1
    fi
fi

echo "Installing build dependencies..."
sudo apt-get install -y dkms make "linux-headers-$KREL" patch curl

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Fetching dw9719.c for v$KVER..."
curl -sfL "https://raw.githubusercontent.com/torvalds/linux/v$KVER/drivers/media/i2c/dw9719.c" \
    -o "$WORK/dw9719.c"
(cd "$WORK" && patch -p1 < "$SCRIPT_DIR/dw9719-id-table.patch")

cat > "$WORK/Makefile" << 'MK'
obj-m := dw9719.o
MK

cat > "$WORK/dkms.conf" << CONF
PACKAGE_NAME="$PKG"
PACKAGE_VERSION="$VER"
BUILT_MODULE_NAME[0]="dw9719"
DEST_MODULE_LOCATION[0]="/updates/dkms"
MAKE[0]="make -C \${kernel_source_dir} M=\${dkms_tree}/\${PACKAGE_NAME}/\${PACKAGE_VERSION}/build modules"
CLEAN="make -C \${kernel_source_dir} M=\${dkms_tree}/\${PACKAGE_NAME}/\${PACKAGE_VERSION}/build clean"
AUTOINSTALL="yes"
CONF

echo "Installing DKMS module $PKG/$VER..."
sudo dkms remove "$PKG/$VER" --all 2>/dev/null || true
sudo rm -rf "/usr/src/$PKG-$VER"
sudo mkdir -p "/usr/src/$PKG-$VER"
sudo cp "$WORK/dw9719.c" "$WORK/Makefile" "$WORK/dkms.conf" "/usr/src/$PKG-$VER/"
sudo dkms install "$PKG/$VER"

sudo modprobe -r dw9719 2>/dev/null || true
sudo modprobe dw9719
sleep 2

echo ""
cam -l 2>/dev/null || true
echo ""
echo "Done. If no cameras are listed above, reboot."
