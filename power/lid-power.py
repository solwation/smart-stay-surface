#!/usr/bin/python3
"""Keep work running with a closed lid, with bounded CPU performance."""
import argparse
import configparser
import glob
import json
from pathlib import Path
import pwd
import signal
import subprocess
import time

STATE = Path('/run/surface-lid-power/state.json')
CPU = Path('/sys/devices/system/cpu/intel_pstate')
SCHEMA = 'org.gnome.settings-daemon.plugins.power'
KEYS = ('sleep-inactive-battery-type', 'sleep-inactive-ac-type')
USER = None
PROFILE = 'power-saver'
CPU_MAX_PERCENT = 35
DISABLE_TURBO = True
POLL_SECONDS = 2.0


def load_config(path):
    global USER, PROFILE, CPU_MAX_PERCENT, DISABLE_TURBO, POLL_SECONDS
    config = configparser.ConfigParser()
    with open(path) as stream:
        config.read_file(stream)
    settings = config['LidPower']
    user = settings['User']
    if pwd.getpwnam(user).pw_uid == 0:
        raise ValueError('User must name a non-root desktop account')
    profile = settings.get('Profile', 'power-saver')
    cap = settings.getint('CpuMaxPercent', 35)
    interval = settings.getfloat('PollSeconds', 2)
    turbo = settings.getboolean('DisableTurbo', True)
    if profile not in ('power-saver', 'balanced', 'performance'):
        raise ValueError('Unsupported power profile')
    if not 1 <= cap <= 100 or not 0.5 <= interval <= 60:
        raise ValueError('CpuMaxPercent must be 1..100 and PollSeconds 0.5..60')
    USER, PROFILE, CPU_MAX_PERCENT = user, profile, cap
    DISABLE_TURBO, POLL_SECONDS = turbo, interval


def run(*args):
    return subprocess.check_output(args, text=True, timeout=15).strip()


def desktop(*args, user=None):
    account = pwd.getpwnam(user or USER)
    return run('/usr/sbin/runuser', '-u', account.pw_name, '--', '/usr/bin/env',
               f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{account.pw_uid}/bus',
               f'XDG_RUNTIME_DIR=/run/user/{account.pw_uid}', *args)


def capture():
    settings = {}
    if Path(f'/run/user/{pwd.getpwnam(USER).pw_uid}/bus').exists():
        settings = {key: desktop('/usr/bin/gsettings', 'get', SCHEMA, key)
                    for key in KEYS}
    return {'user': USER, 'profile': run('/usr/bin/powerprofilesctl', 'get'),
            'max_perf_pct': ((CPU / 'max_perf_pct').read_text().strip()
                             if (CPU / 'max_perf_pct').exists() else None),
            'no_turbo': ((CPU / 'no_turbo').read_text().strip()
                         if (CPU / 'no_turbo').exists() else None),
            'settings': settings}


def restore():
    if not STATE.exists():
        return
    state = json.loads(STATE.read_text())
    errors = []
    actions = [lambda: run('/usr/bin/powerprofilesctl', 'set', state['profile'])]
    actions += [lambda key=key: (CPU / key).write_text(state[key])
                for key in ('max_perf_pct', 'no_turbo') if state.get(key) is not None]
    actions += [lambda k=k, v=v: desktop('/usr/bin/gsettings', 'set', SCHEMA, k, v,
                                        user=state.get('user', USER))
                for k, v in state['settings'].items()]
    for action in actions:
        try:
            action()
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        raise RuntimeError('; '.join(errors))
    STATE.unlink()
    print('Lid open/stopping: previous power and idle settings restored.', flush=True)


def close_lid():
    state = capture()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))
    # Save before making changes, allowing recovery after a service crash.
    try:
        run('/usr/bin/powerprofilesctl', 'set', PROFILE)
        cap = None
        if state['max_perf_pct'] is not None:
            minimum = int((CPU / 'min_perf_pct').read_text())
            cap = max(minimum, min(CPU_MAX_PERCENT, int(state['max_perf_pct'])))
            (CPU / 'max_perf_pct').write_text(str(cap))
        if DISABLE_TURBO and state['no_turbo'] is not None:
            (CPU / 'no_turbo').write_text('1')
        for key in state['settings']:
            desktop('/usr/bin/gsettings', 'set', SCHEMA, key, 'nothing')
        if state['settings']:
            desktop('/usr/bin/gdbus', 'call', '--session', '--dest',
                    'org.gnome.ScreenSaver', '--object-path', '/org/gnome/ScreenSaver',
                    '--method', 'org.gnome.ScreenSaver.SetActive', 'true')
    except Exception:
        restore()
        raise
    print(f'Lid closed: profile={PROFILE}, CPU cap={cap}, '
          f'disable_turbo={DISABLE_TURBO}, idle suspend paused. '
          'Intel CPU controls are skipped when unavailable.',
          flush=True)


def lid_closed():
    paths = glob.glob('/proc/acpi/button/lid/*/state')
    if not paths:
        raise RuntimeError('No lid sensor found')
    return any('closed' in Path(path).read_text() for path in paths)


def stop(_signum, _frame):
    raise SystemExit(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='/etc/surface-lid-power.conf')
    args = parser.parse_args()
    load_config(args.config)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    restore()
    previous = False
    print('Watching lid; battery suspend is independently managed by UPower.', flush=True)
    try:
        while True:
            closed = lid_closed()
            if closed != previous:
                close_lid() if closed else restore()
                previous = closed
            time.sleep(POLL_SECONDS)
    finally:
        restore()


if __name__ == '__main__':
    main()
