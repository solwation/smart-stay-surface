#!/bin/bash
# Install the wifi suspend/resume workaround for mwifiex_pcie.
#   pkexec ~/Documents/smart-stay-surface/wifi/install.sh             install / update
#   pkexec ~/Documents/smart-stay-surface/wifi/install.sh --uninstall
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f /usr/lib/systemd/system-sleep/mwifiex-sleep /usr/local/sbin/wifi-reset
    echo "wifi workaround removed"
    exit 0
fi

install -m755 "$HERE/wifi-reset" /usr/local/sbin/wifi-reset
install -m755 "$HERE/mwifiex-sleep" /usr/lib/systemd/system-sleep/mwifiex-sleep
echo "installed: /usr/local/sbin/wifi-reset, /usr/lib/systemd/system-sleep/mwifiex-sleep"
