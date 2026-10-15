#!/usr/bin/python3
"""Keep work running with a closed lid, with bounded CPU performance."""
import glob
import json
import os
from pathlib import Path
import pwd
import signal
import subprocess
import time

STATE = Path('/run/surface-lid-power/state.json')
CPU = Path('/sys/devices/system/cpu/intel_pstate')
SCHEMA = 'org.gnome.settings-daemon.plugins.power'
KEYS = ('sleep-inactive-battery-type', 'sleep-inactive-ac-type')
USER = 'olw'


def run(*args):
    return subprocess.check_output(args, text=True, timeout=15).strip()


def desktop(*args):
    account = pwd.getpwnam(USER)
    return run('/usr/sbin/runuser', '-u', USER, '--', '/usr/bin/env',
               f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{account.pw_uid}/bus',
               f'XDG_RUNTIME_DIR=/run/user/{account.pw_uid}', *args)


def capture():
    settings = {}
    if Path(f'/run/user/{pwd.getpwnam(USER).pw_uid}/bus').exists():
        settings = {key: desktop('/usr/bin/gsettings', 'get', SCHEMA, key)
                    for key in KEYS}
    return {'profile': run('/usr/bin/powerprofilesctl', 'get'),
            'max_perf_pct': (CPU / 'max_perf_pct').read_text().strip(),
            'no_turbo': (CPU / 'no_turbo').read_text().strip(),
            'settings': settings}


def restore():
    if not STATE.exists():
        return
    state = json.loads(STATE.read_text())
    errors = []
    actions = [lambda: run('/usr/bin/powerprofilesctl', 'set', state['profile']),
               lambda: (CPU / 'max_perf_pct').write_text(state['max_perf_pct']),
               lambda: (CPU / 'no_turbo').write_text(state['no_turbo'])]
    actions += [lambda k=k, v=v: desktop('/usr/bin/gsettings', 'set', SCHEMA, k, v)
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
        run('/usr/bin/powerprofilesctl', 'set', 'power-saver')
        minimum = int((CPU / 'min_perf_pct').read_text())
        cap = max(minimum, min(35, int(state['max_perf_pct'])))
        (CPU / 'max_perf_pct').write_text(str(cap))
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
    print(f'Lid closed: power-saver, CPU cap {cap}%, turbo off, idle suspend paused.',
          flush=True)


def lid_closed():
    paths = glob.glob('/proc/acpi/button/lid/*/state')
    if not paths:
        raise RuntimeError('No lid sensor found')
    return any('closed' in Path(path).read_text() for path in paths)


def stop(_signum, _frame):
    raise SystemExit(0)


def main():
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
            time.sleep(2)
    finally:
        restore()


if __name__ == '__main__':
    main()
