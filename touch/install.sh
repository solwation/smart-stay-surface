#!/bin/bash
# Install the touch-gestures daemon (system service, needs root for EVIOCGRAB + uinput).
#   pkexec ~/Documents/smart-stay-surface/touch/install.sh             install / update
#   pkexec ~/Documents/smart-stay-surface/touch/install.sh --uninstall
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"

if [[ "${1:-}" == "--uninstall" ]]; then
    systemctl disable --now touch-gestures.service || true
    rm -f /usr/local/bin/touch-gestures /etc/systemd/system/touch-gestures.service
    systemctl daemon-reload
    echo "touch-gestures removed"
    exit 0
fi

python3 -c 'import evdev' 2>/dev/null || apt-get install -y python3-evdev
install -m755 "$HERE/touch-gestures" /usr/local/bin/touch-gestures
install -m644 "$HERE/touch-gestures.service" /etc/systemd/system/touch-gestures.service
systemctl daemon-reload
systemctl enable touch-gestures.service
systemctl restart touch-gestures.service
sleep 2
systemctl --no-pager status touch-gestures.service | head -8
