#!/bin/bash
# Make the IPU3 cameras usable in Google Chrome (and web apps such as Teams).
#   ./chrome-camera.sh        (run as your user, not root)
#
# IPU3 cameras can't be used through plain V4L2; Chrome must go through the
# camera portal -> PipeWire -> libcamera. This script:
#   1. installs the PipeWire libcamera plugin and restarts WirePlumber
#   2. grants Chrome camera access in the portal permission store. The portal's
#      own dialog fails for Chrome web apps ("Only the focused app is allowed to
#      show a system access dialog"), because the PWA window has a different
#      app ID than the requesting Chrome process (com.google.Chrome).
# Revoke later in Settings -> Privacy & Security -> Camera.
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
    echo "Run as your normal user (it talks to your session's portal and PipeWire)."
    exit 1
fi

dpkg -s libspa-0.2-libcamera >/dev/null 2>&1 || sudo apt-get install -y libspa-0.2-libcamera
systemctl --user restart wireplumber
sleep 3

gdbus call --session --dest org.freedesktop.impl.portal.PermissionStore \
    --object-path /org/freedesktop/impl/portal/PermissionStore \
    --method org.freedesktop.impl.portal.PermissionStore.SetPermission \
    devices true camera com.google.Chrome "['yes']" >/dev/null

echo "PipeWire cameras:"
pw-dump 2>/dev/null | python3 -c '
import json, sys
for o in json.load(sys.stdin):
    p = (o.get("info") or {}).get("props") or {}
    if p.get("media.class") == "Video/Source":
        print("  " + str(p.get("node.description")))'

cat <<'MSG'

Remaining steps in Chrome:
  1. chrome://flags/#enable-webrtc-pipewire-camera -> Enabled, then chrome://restart
  2. chrome://settings/content/camera should now list the cameras
  3. Sites that asked for permission while no camera existed (e.g. Teams asked
     for the microphone only) won't ask again. Allow the camera per site:
       chrome://settings/content/siteDetails?site=https://teams.cloud.microsoft
     then reload the site.
MSG
