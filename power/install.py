#!/usr/bin/python3
"""Explicitly install optional lid power saving and/or a low-battery suspend policy."""
import argparse
import configparser
import datetime
import io
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parent
LID_SCRIPT = Path('/usr/local/lib/surface-lid-power.py')
LID_SERVICE = Path('/etc/systemd/system/surface-lid-power.service')
LID_CONFIG = Path('/etc/surface-lid-power.conf')
BATTERY_CONFIG = Path('/etc/UPower/UPower.conf.d/90-surface-battery.conf')
BACKUPS = Path('/var/backups/surface-power')
SERVICE = 'surface-lid-power.service'


def run(*args):
    return subprocess.check_output(args, text=True, timeout=45).strip()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lid', action='store_true', help='install closed-lid handling')
    parser.add_argument('--battery', action='store_true', help='install a UPower suspend rule')
    parser.add_argument('--user', help='desktop account for lid handling (defaults to sudo/pkexec caller)')
    parser.add_argument('--cpu-max-percent', type=int, default=35)
    parser.add_argument('--profile', choices=('power-saver', 'balanced', 'performance'), default='power-saver')
    parser.add_argument('--keep-turbo', action='store_true')
    parser.add_argument('--poll-seconds', type=float, default=2)
    parser.add_argument('--suspend-at', type=float, default=10)
    parser.add_argument('--critical-at', type=float, default=15)
    parser.add_argument('--low-at', type=float, default=20)
    parser.add_argument('--uninstall', action='store_true', help='remove only the selected components')
    parser.add_argument('--dry-run', action='store_true', help='show planned files without changing anything')
    args = parser.parse_args(argv)
    if not (args.lid or args.battery):
        parser.error('select --lid and/or --battery; nothing is installed by default')
    if args.lid and not args.uninstall:
        if not 1 <= args.cpu_max_percent <= 100 or not 0.5 <= args.poll_seconds <= 60:
            parser.error('CPU limit must be 1..100 and polling interval 0.5..60 seconds')
        user = args.user or os.environ.get('SUDO_USER')
        if not user and os.environ.get('PKEXEC_UID'):
            user = pwd.getpwuid(int(os.environ['PKEXEC_UID'])).pw_name
        if not user and os.geteuid() != 0:
            user = pwd.getpwuid(os.getuid()).pw_name
        try:
            account = pwd.getpwnam(user) if user else None
        except KeyError:
            parser.error('desktop account does not exist')
        if account is None or account.pw_uid == 0:
            parser.error('specify --user with a non-root desktop account')
        args.user = account.pw_name
    if args.battery and not args.uninstall:
        if not 0 < args.suspend_at < args.critical_at < args.low_at <= 100:
            parser.error('require 0 < suspend-at < critical-at < low-at <= 100')
    return args


def ini_bytes(section, values):
    config = configparser.ConfigParser()
    config.optionxform = str
    config[section] = {key: str(value) for key, value in values.items()}
    stream = io.StringIO()
    config.write(stream, space_around_delimiters=False)
    return stream.getvalue().encode()


def build_plan(args):
    plan = {}
    if args.lid:
        plan = {LID_SCRIPT: (SOURCE / 'lid-power.py').read_bytes(),
                LID_SERVICE: (SOURCE / 'surface-lid-power.service').read_bytes(),
                LID_CONFIG: ini_bytes('LidPower', {
                    'User': args.user or '', 'Profile': args.profile,
                    'CpuMaxPercent': args.cpu_max_percent,
                    'DisableTurbo': str(not args.keep_turbo).lower(),
                    'PollSeconds': args.poll_seconds})}
    if args.battery:
        plan[BATTERY_CONFIG] = ini_bytes('UPower', {
            'UsePercentageForPolicy': 'true', 'PercentageLow': args.low_at,
            'PercentageCritical': args.critical_at, 'PercentageAction': args.suspend_at,
            'AllowRiskyCriticalPowerAction': 'true', 'CriticalPowerAction': 'Suspend'})
    return {path: None if args.uninstall else content for path, content in plan.items()}


def preflight(args):
    if args.uninstall:
        return
    if args.lid:
        for command in ('powerprofilesctl', 'systemd-inhibit', 'gsettings', 'gdbus', 'runuser'):
            if not shutil.which(command):
                raise RuntimeError('Missing dependency: ' + command)
        if not list(Path('/proc/acpi/button/lid').glob('*/state')):
            raise RuntimeError('No ACPI lid sensor found; lid handling is not supported here')
        run('powerprofilesctl', 'get')
    if args.battery:
        if run('busctl', 'call', 'org.freedesktop.login1', '/org/freedesktop/login1',
               'org.freedesktop.login1.Manager', 'CanSuspend') != 's "yes"':
            raise RuntimeError('Suspend is not available')
        if not Path('/etc/UPower/UPower.conf.d/README.md').exists():
            raise RuntimeError('This installer requires UPower with UPower.conf.d support')


def apply_plan(args, plan):
    original = {path: (path.read_bytes(), path.stat().st_mode & 0o777)
                if path.exists() else None for path in plan}
    active = args.lid and subprocess.run(['systemctl', 'is-active', '--quiet', SERVICE]).returncode == 0
    enabled = args.lid and subprocess.run(['systemctl', 'is-enabled', '--quiet', SERVICE]).returncode == 0
    backup = BACKUPS / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    manifest = {}
    for index, (path, data) in enumerate(original.items()):
        manifest[str(path)] = {'file': str(index) if data else None,
                               'mode': data[1] if data else None}
        if data:
            (backup / str(index)).write_bytes(data[0])
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    try:
        if args.lid and active:
            run('systemctl', 'stop', SERVICE)
        if args.lid and args.uninstall:
            run('systemctl', 'disable', SERVICE)
        for path, content in plan.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                path.chmod(0o644)
        if args.lid:
            run('systemctl', 'daemon-reload')
        if args.battery:
            run('systemctl', 'restart', 'upower.service')
            if not args.uninstall:
                action = run('busctl', 'call', 'org.freedesktop.UPower', '/org/freedesktop/UPower',
                             'org.freedesktop.UPower', 'GetCriticalAction')
                if action != 's "Suspend"':
                    raise RuntimeError('UPower did not select Suspend: ' + action)
        if args.lid and not args.uninstall:
            # reenable drops links from an older [Install] section (e.g. multi-user.target)
            run('systemctl', 'reenable', SERVICE)
            run('systemctl', 'start', SERVICE)
            run('systemctl', 'is-active', '--quiet', SERVICE)
    except Exception:
        if args.lid:
            subprocess.run(['systemctl', 'disable', '--now', SERVICE], check=False)
        for path, data in original.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data[0])
                path.chmod(data[1])
        if args.lid:
            run('systemctl', 'daemon-reload')
            if enabled:
                run('systemctl', 'enable', SERVICE)
            if active:
                run('systemctl', 'start', SERVICE)
        if args.battery:
            run('systemctl', 'restart', 'upower.service')
        raise
    print('Removed' if args.uninstall else 'Installed', ', '.join(str(p) for p in plan))
    print('Backup:', backup)


def main():
    args = parse_args()
    plan = build_plan(args)
    if args.dry_run:
        for path, data in plan.items():
            print(('REMOVE ' if data is None else 'WRITE ') + str(path))
            if data is not None and path in (LID_CONFIG, BATTERY_CONFIG):
                print(data.decode())
        return
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo or pkexec, or use --dry-run.')
    preflight(args)
    apply_plan(args, plan)


if __name__ == '__main__':
    main()
