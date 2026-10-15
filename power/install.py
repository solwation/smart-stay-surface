#!/usr/bin/python3
"""Install reviewed local power settings. Requires root authentication."""
import datetime
import os
from pathlib import Path
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parent
FILES = {
    'lid-power.py': Path('/usr/local/lib/surface-lid-power.py'),
    'surface-lid-power.service': Path('/etc/systemd/system/surface-lid-power.service'),
    '90-surface-battery.conf': Path('/etc/UPower/UPower.conf.d/90-surface-battery.conf'),
}


def run(*args):
    return subprocess.check_output(args, text=True, timeout=30).strip()


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run with pkexec or sudo.')
    # Fail before changing anything if essential hardware support is missing.
    if run('busctl', 'call', 'org.freedesktop.login1', '/org/freedesktop/login1',
           'org.freedesktop.login1.Manager', 'CanSuspend') != 's "yes"':
        raise SystemExit('Suspend is not available.')
    if not Path('/sys/devices/system/cpu/intel_pstate/max_perf_pct').exists():
        raise SystemExit('Intel CPU power controls are not available.')
    backup = Path('/var/backups/surface-power') / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    shutil.copy2('/etc/UPower/UPower.conf', backup / 'UPower.conf')
    original = {dest: dest.read_bytes() if dest.exists() else None for dest in FILES.values()}
    for name, dest in FILES.items():
        if dest.exists():
            shutil.copy2(dest, backup / name)
    try:
        for name, dest in FILES.items():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((SOURCE / name).read_bytes())
            dest.chmod(0o644)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'restart', 'upower.service')
        action = run('busctl', 'call', 'org.freedesktop.UPower', '/org/freedesktop/UPower',
                     'org.freedesktop.UPower', 'GetCriticalAction')
        if action != 's "Suspend"':
            raise RuntimeError('UPower did not select Suspend: ' + action)
        run('systemctl', 'enable', '--now', 'surface-lid-power.service')
        print('Installed: closed-lid power saving and battery suspend at 10%.')
        print('Backup:', backup)
    except Exception:
        run('systemctl', 'stop', 'surface-lid-power.service')
        for dest, data in original.items():
            if data is None:
                dest.unlink(missing_ok=True)
            else:
                dest.write_bytes(data)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'restart', 'upower.service')
        raise


if __name__ == '__main__':
    main()
