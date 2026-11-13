# Optional lid power saving and battery suspend

Keep background work running with a closed keyboard cover, or request suspend at a
chosen battery level. These are two independent opt-in components. The main
`install.sh` never installs them, and running this installer without a component
selection exits without changes.

## Requirements

Lid handling requires Linux with systemd, an ACPI lid sensor, GNOME, and
`power-profiles-daemon` (`powerprofilesctl`). It targets one explicitly selected
non-root desktop account. Intel P-state CPU controls are used when present; other
CPUs receive the power profile and GNOME idle policy changes without an Intel CPU
cap or turbo override. This module is not a universal thermal controller.

The battery rule requires suspend support and UPower with configuration drop-in
support and `CriticalPowerAction=Suspend` (developed with UPower 1.91.1). The
installer checks for the drop-in documentation and verifies the effective action
through D-Bus. It leaves the main UPower configuration intact.

## Choose components

Run these commands from the repository root, in a terminal:

```bash
# Lid handling only, for your desktop account
sudo /usr/bin/python3 power/install.py --lid --user "$USER"

# Battery suspend only; no changes to lid behavior
sudo /usr/bin/python3 power/install.py --battery --suspend-at 10 --critical-at 15 --low-at 20

# Both components, with explicit preferences
sudo /usr/bin/python3 power/install.py --lid --user "$USER" --cpu-max-percent 35 --battery --suspend-at 10
```

`pkexec /usr/bin/python3 ...` also works with the same options. `--user` defaults to
the sudo/pkexec caller, but an explicit account is useful for repeatable restores.
Root is not accepted as the desktop account. To preview the planned files without
root privileges or changes, add `--dry-run`.

| Option | Default | Meaning |
|---|---|---|
| `--lid` | Off | Explicitly select closed-lid handling |
| `--battery` | Off | Explicitly select the battery suspend policy |
| `--user ACCOUNT` | Calling desktop user | GNOME account affected by lid handling |
| `--cpu-max-percent N` | 35 | Intel P-state performance cap, 1–100 |
| `--profile PROFILE` | `power-saver` | Closed-lid power profile; must be available on the machine |
| `--keep-turbo` | Off | Leave the existing turbo setting in place |
| `--poll-seconds N` | 2 | Lid sensor polling interval, 0.5–60 seconds |
| `--suspend-at N` | 10 | Battery percentage for suspend |
| `--critical-at N` | 15 | Critical battery warning level |
| `--low-at N` | 20 | Low battery warning level |
| `--uninstall` | Off | Remove only the selected components |

Battery thresholds must satisfy `0 < suspend < critical < low <= 100`. If you
raise the suspend threshold, adjust the warning thresholds above it as needed.
Suspend pauses processes and keeps RAM powered. A fully drained battery can lose
the in-memory session; this policy does not provide hibernation protection.

## Runtime behavior and configuration

When the cover closes, the service saves current settings, selects the requested
profile, applies available Intel CPU controls, activates GNOME's screensaver, and
sets the selected user's AC and battery idle-suspend policies to `nothing`.
Opening the cover restores the saved values. A normal stop restores them too;
a service restart attempts to recover saved settings before watching the lid again.

The CPU cap is a performance limit, not a CPU-usage percentage or process priority.
A lower existing limit is preserved, subject to the driver's minimum setting.
Other software that changes power profiles, including charger hooks, can override
the profile while the cover is closed. Opening restores the profile captured at
closure, regardless of intervening charger events. CPU controls remain separate.

Only `handle-lid-switch` is inhibited. Battery-triggered and manual suspend remain
available. No `logind.conf` changes are made. Lid configuration is stored locally
in `/etc/surface-lid-power.conf`:

```ini
[LidPower]
User=your-desktop-account
Profile=power-saver
CpuMaxPercent=35
DisableTurbo=true
PollSeconds=2
```

Change that file and restart `surface-lid-power.service`, or rerun the installer
with your preferred options. Keep personal configuration outside the public repo.
The battery policy lives in
`/etc/UPower/UPower.conf.d/90-surface-battery.conf`; restart `upower.service` after
changing it. Reinstalling a selected component replaces its settings with the
options supplied on that invocation, including their defaults.

Installed code and unit: `/usr/local/lib/surface-lid-power.py` and
`/etc/systemd/system/surface-lid-power.service`. Restoration state is temporary:
`/run/surface-lid-power/state.json`. Install/update/remove operations save previous
files and their modes under `/var/backups/surface-power/`, with a `manifest.json`
identifying each backup. Failed installation attempts restore previous files and
the prior lid-service activation state.

## Check behavior

```bash
systemctl status surface-lid-power.service --no-pager
journalctl -u surface-lid-power.service -n 30 --no-pager
cat /proc/acpi/button/lid/*/state
powerprofilesctl get
# Intel systems only:
cat /sys/devices/system/cpu/intel_pstate/max_perf_pct
cat /sys/devices/system/cpu/intel_pstate/no_turbo
# With the battery component installed, expect: s "Suspend"
busctl call org.freedesktop.UPower /org/freedesktop/UPower org.freedesktop.UPower GetCriticalAction
```

Record baseline values, close the cover, then open it and confirm they return.
Reboot once and confirm the service is `active` without starting it manually.

If it is `inactive` after boot and the journal shows `Found ordering cycle ...
Job surface-lid-power.service/start deleted`, the installed unit is an older
copy with `WantedBy=multi-user.target`. Ubuntu's `power-profiles-daemon` orders
itself after `multi-user.target`, so systemd drops this service at boot and the
lid suspends as usual. Reinstall with `--lid` to use `WantedBy=graphical.target`.
Check suspend/resume on your hardware before relying on low-battery handling.
For Marvell Wi-Fi resume problems, see [`../wifi/`](../wifi/) and the main README.

Automated tests use temporary CPU controls and mocked system/desktop commands:

```bash
/usr/bin/python3 -m unittest discover -s power -v
```

## Remove selected components

```bash
sudo /usr/bin/python3 power/install.py --lid --uninstall
sudo /usr/bin/python3 power/install.py --battery --uninstall
```

Removing lid handling restores saved values and releases the lid inhibitor;
Ubuntu resumes its normal lid policy. Removing the battery override restores the
remaining system/vendor battery policy. Either component can remain installed
without the other. Backups are retained for manual recovery.
