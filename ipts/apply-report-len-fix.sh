#!/bin/bash
# Rebuild ipts DKMS with the kernel 7.0 report-length fix and reload it.
#   pkexec ~/Documents/smart-stay-surface/ipts/apply-report-len-fix.sh
#
# Kernel 7.0 hid_report_raw_event() rejects reports shorter than the descriptor
# ("Event data for report 65 was too short (7487 vs 7484)", ipts: "Failed to
# process buffer: -22"). The driver sent 7485 bytes incl. report ID, but the
# descriptor declares scan time (2) + 7485 data bytes. See the .patch next to this.
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
K="$(uname -r)"

rsync -a --delete "$HERE/src/" /usr/src/ipts-1.0.0/
dkms remove ipts/1.0.0 -k "$K" || true
dkms install ipts/1.0.0 -k "$K"

systemctl stop 'iptsd@*' || true
modprobe -r ipts
modprobe ipts
sleep 3
dkms status ipts
systemctl --no-pager list-units 'iptsd*'
