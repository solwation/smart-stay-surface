#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing smart-stay..."

# Fix IPU3 camera tuning files (requires sudo)
echo ""
echo "Fixing camera tuning files (requires sudo)..."
"$SCRIPT_DIR/fix-camera.sh"

# Install the script
mkdir -p ~/bin
cp "$SCRIPT_DIR/smart-stay" ~/bin/smart-stay
chmod +x ~/bin/smart-stay

# Install the systemd user service
mkdir -p ~/.config/systemd/user
cp "$SCRIPT_DIR/smart-stay.service" ~/.config/systemd/user/smart-stay.service
systemctl --user daemon-reload

echo ""
echo "Installed. Next steps:"
echo "  1. Reboot to reset camera sensors: sudo reboot"
echo "  2. After reboot, enable auto-start:"
echo "       systemctl --user enable smart-stay"
echo "       systemctl --user start smart-stay"
echo ""
echo "  Or run manually:"
echo "       smart-stay              # foreground"
echo "       smart-stay --daemon     # background"
echo ""
echo "  To verify the camera works:"
echo "       smart-stay --debug-capture"
