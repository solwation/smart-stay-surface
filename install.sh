#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRA_ARGS=""

usage() {
    echo "Usage: install.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --ac-mode MODE       Detection on AC power: face, motion, off (default: motion)"
    echo "  --battery-mode MODE  Detection on battery: face, motion, off (default: face)"
    echo "  --motion             Legacy shorthand for --ac-mode motion --battery-mode off"
    echo ""
    echo "Examples:"
    echo "  ./install.sh                                    # default (AC=motion, battery=face)"
    echo "  ./install.sh --ac-mode face --battery-mode off  # face on AC, skip on battery"
    echo "  ./install.sh --motion                           # motion on AC, skip on battery"
}

AC_MODE="motion"
BATTERY_MODE="face"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --motion)
            AC_MODE="motion"
            BATTERY_MODE="off"
            shift
            ;;
        --ac-mode)
            AC_MODE="$2"
            shift 2
            ;;
        --battery-mode)
            BATTERY_MODE="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

echo "Installing smart-stay (AC=${AC_MODE}, battery=${BATTERY_MODE})..."

if [[ "$AC_MODE" != "motion" ]] || [[ "$BATTERY_MODE" != "face" ]]; then
    EXTRA_ARGS=" --ac-mode ${AC_MODE} --battery-mode ${BATTERY_MODE}"
fi

# Fix IPU3 camera tuning files (requires sudo)
echo ""
echo "Fixing camera tuning files (requires sudo)..."
"$SCRIPT_DIR/fix-camera.sh"

# Install the script
mkdir -p ~/bin
cp "$SCRIPT_DIR/smart-stay" ~/bin/smart-stay
chmod +x ~/bin/smart-stay

# Install the systemd user service, injecting mode flags
mkdir -p ~/.config/systemd/user
sed "s|ExecStart=%h/bin/smart-stay|ExecStart=%h/bin/smart-stay${EXTRA_ARGS}|" \
    "$SCRIPT_DIR/smart-stay.service" > ~/.config/systemd/user/smart-stay.service
systemctl --user daemon-reload

echo ""
echo "Installed (AC=${AC_MODE}, battery=${BATTERY_MODE}). Next steps:"
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
echo "       smart-stay --debug-capture"
