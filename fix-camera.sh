#!/bin/bash
# Fix Surface IPU3 camera tuning files
#
# The default libcamera IPA tuning files for ov5693/ov8865 sensors are often
# symlinks to uncalibrated.yaml, which lacks the required algorithm config.
# Without proper tuning, the IPU3 ImgU produces all-black frames (Y plane = 0).
#
# This script writes minimal working tuning files that enable the essential
# IPA algorithms: auto-gain, auto-white-balance, black level correction, and
# tone mapping. Reboot after running to power-cycle the camera sensors.

set -euo pipefail

# libcamera >= 0.7 (Ubuntu 26.04) ships an uncalibrated.yaml that already
# enables these algorithms, so the per-sensor files are not needed there.
UNCAL=/usr/share/libcamera/ipa/ipu3/uncalibrated.yaml
if [[ -f "$UNCAL" && ! -L "$UNCAL" ]] && grep -q 'Agc' "$UNCAL" && grep -q 'Awb' "$UNCAL"; then
    echo "uncalibrated.yaml already enables Agc/Awb -- tuning fix not needed."
    exit 0
fi

echo "Writing ov5693 (front camera) tuning file..."
sudo tee /usr/share/libcamera/ipa/ipu3/ov5693.yaml > /dev/null << 'EOF'
# SPDX-License-Identifier: CC0-1.0
%YAML 1.1
---
version: 1
algorithms:
  - Af:
  - Agc:
  - Awb:
  - BlackLevelCorrection:
  - ToneMapping:
...
EOF

echo "Writing ov8865 (back camera) tuning file..."
sudo tee /usr/share/libcamera/ipa/ipu3/ov8865.yaml > /dev/null << 'EOF'
# SPDX-License-Identifier: CC0-1.0
%YAML 1.1
---
version: 1
algorithms:
  - Af:
  - Agc:
  - Awb:
  - BlackLevelCorrection:
  - ToneMapping:
...
EOF

echo ""
echo "Done! Tuning files written. Reboot to reset the camera sensors:"
echo "  sudo reboot"
