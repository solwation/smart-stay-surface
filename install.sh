#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing smart-stay..."

# Install the script
mkdir -p ~/bin
cp "$SCRIPT_DIR/smart-stay" ~/bin/smart-stay
chmod +x ~/bin/smart-stay

# Install the systemd user service
mkdir -p ~/.config/systemd/user
cp "$SCRIPT_DIR/smart-stay.service" ~/.config/systemd/user/smart-stay.service
systemctl --user daemon-reload

echo "Installed. To enable auto-start on login:"
echo "  systemctl --user enable smart-stay"
echo "  systemctl --user start smart-stay"
echo ""
echo "Or run manually:"
echo "  smart-stay            # foreground"
echo "  smart-stay --daemon   # background"
