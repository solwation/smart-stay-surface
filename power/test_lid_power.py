import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('lid_power', Path(__file__).with_name('lid-power.py'))
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)


class LidPowerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.cpu = root / 'cpu'
        self.cpu.mkdir()
        for key, value in [('max_perf_pct', '100'), ('no_turbo', '0'), ('min_perf_pct', '10')]:
            (self.cpu / key).write_text(value)
        self.state = {'profile': 'balanced', 'max_perf_pct': '100', 'no_turbo': '0',
                      'settings': {key: "'suspend'" for key in power.KEYS}}
        for name, value in [('CPU', self.cpu), ('STATE', root / 'run/state.json'),
                            ('USER', 'desktop-user'), ('PROFILE', 'power-saver'),
                            ('CPU_MAX_PERCENT', 35), ('DISABLE_TURBO', True), ('POLL_SECONDS', 2)]:
            patcher = patch.object(power, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_close_open_restores_cpu_profile_and_idle_policy(self):
        with patch.object(power, 'capture', return_value=self.state), \
             patch.object(power, 'run') as command, patch.object(power, 'desktop') as desktop:
            power.close_lid()
            self.assertEqual((self.cpu / 'max_perf_pct').read_text(), '35')
            self.assertEqual((self.cpu / 'no_turbo').read_text(), '1')
            command.assert_any_call('/usr/bin/powerprofilesctl', 'set', 'power-saver')
            for key in power.KEYS:
                desktop.assert_any_call('/usr/bin/gsettings', 'set', power.SCHEMA, key, 'nothing')
            self.assertTrue(power.STATE.exists())
            power.restore()
            self.assertEqual((self.cpu / 'max_perf_pct').read_text(), '100')
            self.assertEqual((self.cpu / 'no_turbo').read_text(), '0')
            command.assert_any_call('/usr/bin/powerprofilesctl', 'set', 'balanced')
            for key in power.KEYS:
                desktop.assert_any_call('/usr/bin/gsettings', 'set', power.SCHEMA, key, "'suspend'",
                                        user='desktop-user')
            self.assertFalse(power.STATE.exists())

    def test_partial_failure_restores_cpu_and_profile(self):
        def desktop(*args, **kwargs):
            if args[0] == '/usr/bin/gdbus':
                raise RuntimeError('Screen service unavailable')
        with patch.object(power, 'capture', return_value=self.state), \
             patch.object(power, 'run') as command, patch.object(power, 'desktop', side_effect=desktop):
            with self.assertRaisesRegex(RuntimeError, 'Screen service'):
                power.close_lid()
            self.assertEqual((self.cpu / 'max_perf_pct').read_text(), '100')
            self.assertEqual((self.cpu / 'no_turbo').read_text(), '0')
            command.assert_any_call('/usr/bin/powerprofilesctl', 'set', 'balanced')
            self.assertFalse(power.STATE.exists())

    def test_existing_lower_cpu_limit_is_preserved(self):
        self.state['max_perf_pct'] = '20'
        with patch.object(power, 'capture', return_value=self.state), \
             patch.object(power, 'run'), patch.object(power, 'desktop'):
            power.close_lid()
            self.assertEqual((self.cpu / 'max_perf_pct').read_text(), '20')
            power.restore()
            self.assertEqual((self.cpu / 'max_perf_pct').read_text(), '20')

    def test_configurable_limit_and_turbo(self):
        with patch.object(power, 'capture', return_value=self.state), \
             patch.object(power, 'run'), patch.object(power, 'desktop'), \
             patch.object(power, 'CPU_MAX_PERCENT', 50), patch.object(power, 'DISABLE_TURBO', False):
            power.close_lid()
            self.assertEqual((self.cpu / 'max_perf_pct').read_text(), '50')
            self.assertEqual((self.cpu / 'no_turbo').read_text(), '0')
            power.restore()

    def test_recovery_restores_the_original_desktop_account(self):
        self.state['user'] = 'original-user'
        power.STATE.parent.mkdir(parents=True)
        power.STATE.write_text(power.json.dumps(self.state))
        with patch.object(power, 'run'), patch.object(power, 'desktop') as desktop:
            power.restore()
            desktop.assert_any_call('/usr/bin/gsettings', 'set', power.SCHEMA,
                                    power.KEYS[0], "'suspend'", user='original-user')
            self.assertFalse(power.STATE.exists())

    def test_missing_intel_controls_does_not_prevent_profile_and_idle_changes(self):
        self.state['max_perf_pct'] = self.state['no_turbo'] = None
        for path in self.cpu.iterdir():
            path.unlink()
        with patch.object(power, 'capture', return_value=self.state), \
             patch.object(power, 'run') as command, patch.object(power, 'desktop'):
            power.close_lid()
            command.assert_any_call('/usr/bin/powerprofilesctl', 'set', 'power-saver')
            power.restore()
            self.assertFalse(power.STATE.exists())

    def test_account_configuration_is_required_and_validated(self):
        path = Path(self.tmp.name) / 'config'
        path.write_text('[LidPower]\nUser=desktop-user\nCpuMaxPercent=45\nDisableTurbo=false\n')
        with patch.object(power.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1234)):
            power.load_config(path)
            self.assertEqual(power.USER, 'desktop-user')
            self.assertEqual(power.CPU_MAX_PERCENT, 45)
            self.assertFalse(power.DISABLE_TURBO)
        path.write_text('[LidPower]\nUser=desktop-user\nCpuMaxPercent=101\n')
        with patch.object(power.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1234)):
            with self.assertRaises(ValueError):
                power.load_config(path)


if __name__ == '__main__':
    unittest.main()
