#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRA_ARGS=""

if [[ "${1:-}" == "--motion" ]]; then
    EXTRA_ARGS=" --motion"
    echo "Installing smart-stay (motion-only mode)..."
else
    echo "Installing smart-stay (adaptive: motion on AC, face on battery)..."
fi

# Fix IPU3 camera tuning files (requires sudo)
echo ""
echo "Fixing camera tuning files (requires sudo)..."
"$SCRIPT_DIR/fix-camera.sh"

# Install the script
mkdir -p ~/bin
cp "$SCRIPT_DIR/smart-stay" ~/bin/smart-stay
chmod +x ~/bin/smart-stay

# Install the systemd user service, injecting mode flag
mkdir -p ~/.config/systemd/user
sed "s|ExecStart=%h/bin/smart-stay|ExecStart=%h/bin/smart-stay${EXTRA_ARGS}|" \
    "$SCRIPT_DIR/smart-stay.service" > ~/.config/systemd/user/smart-stay.service
systemctl --user daemon-reload

echo ""
echo "Installed. Next steps:"
echo "  1. Reboot to reset camera sensors: sudo reboot"
echo "  2. After reboot, enable auto-start:"
echo "       systemctl --user enable smart-stay"
echo "       systemctl --user start smart-stay"
echo ""
echo "  Or run manually:"
echo "       smart-stay${EXTRA_ARGS}              # foreground"
echo "       smart-stay${EXTRA_ARGS} --daemon     # background"
echo ""
echo "  To verify the camera works:"
echo "       smart-stay${EXTRA_ARGS} --debug-capture"
