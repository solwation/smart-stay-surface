#!/bin/bash
# Install face-unlock: GNOME lock screen unlock with the Surface IR camera.
#
#   sudo ./install.sh              # install + enable in /etc/pam.d/gdm-password
#   sudo ./install.sh --uninstall  # remove the PAM line (keeps models and enrolled faces)
#
# Needs the IR illuminator fix first: ../kernel7/fix-ov7251.sh
# Afterwards, enroll: sudo face-unlock enroll <user>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PAM_FILE=/etc/pam.d/gdm-password
PAM_LINE='auth    [success=done default=ignore]  pam_exec.so quiet stdout /usr/local/bin/face-unlock auth'
MODEL_DIR=/usr/local/share/face-unlock
ZOO=https://github.com/opencv/opencv_zoo/raw/main/models
MODELS=(
    "face_detection_yunet/face_detection_yunet_2023mar.onnx 8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    "face_recognition_sface/face_recognition_sface_2021dec.onnx 0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
)

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo/pkexec)."; exit 1; }

if [[ "${1:-}" == "--uninstall" ]]; then
    sed -i '\|pam_exec.so .*/usr/local/bin/face-unlock|d' "$PAM_FILE"
    echo "Removed face-unlock from $PAM_FILE."
    exit 0
fi

if ! modinfo -F filename ov7251 | grep -q /updates/dkms/; then
    echo "Warning: ov7251 without IR strobe fix -- run ../kernel7/fix-ov7251.sh (frames will be dark)."
fi

apt-get install -y --no-install-recommends python3-opencv python3-numpy v4l-utils curl

install -d -m 755 "$MODEL_DIR"
for m in "${MODELS[@]}"; do
    read -r path sum <<< "$m"
    f="$MODEL_DIR/$(basename "$path")"
    if ! echo "$sum  $f" | sha256sum -c --quiet 2>/dev/null; then
        echo "Downloading $(basename "$path")..."
        curl -sfL "$ZOO/$path" -o "$f.tmp"
        echo "$sum  $f.tmp" | sha256sum -c --quiet
        mv "$f.tmp" "$f"
        chmod 644 "$f"
    fi
done

install -m 755 "$SCRIPT_DIR/face-unlock" /usr/local/bin/face-unlock
install -d -m 700 /etc/face-unlock

# Before the password (common-auth): a match ends the stack, anything else
# (no face, no enrollment, first login, camera error) falls through to it.
if ! grep -q 'pam_exec.so .*/usr/local/bin/face-unlock' "$PAM_FILE"; then
    cp -a "$PAM_FILE" "$PAM_FILE.bak-face-unlock"
    sed -i "\|^@include common-auth|i $PAM_LINE" "$PAM_FILE"
    echo "Enabled in $PAM_FILE (backup: $PAM_FILE.bak-face-unlock)."
fi

echo "Done. Enroll with: sudo face-unlock enroll <user>, then lock (Super+L) to try it."
