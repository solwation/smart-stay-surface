import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('power_install', Path(__file__).with_name('install.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def parse(self, argv):
        with patch.object(installer.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1234, pw_name='desktop-user')):
            return installer.parse_args(argv)

    def test_no_components_means_no_install(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.parse([])
        self.assertEqual(error.exception.code, 2)

    def test_components_are_independent(self):
        battery = installer.build_plan(self.parse(['--battery', '--suspend-at', '8']))
        self.assertEqual(set(battery), {installer.BATTERY_CONFIG})
        self.assertIn(b'PercentageAction=8.0', battery[installer.BATTERY_CONFIG])
        lid = installer.build_plan(self.parse(['--lid', '--user', 'desktop-user', '--cpu-max-percent', '45', '--keep-turbo']))
        self.assertNotIn(installer.BATTERY_CONFIG, lid)
        self.assertIn(b'User=desktop-user', lid[installer.LID_CONFIG])
        self.assertIn(b'CpuMaxPercent=45', lid[installer.LID_CONFIG])
        self.assertIn(b'DisableTurbo=false', lid[installer.LID_CONFIG])

    def test_invalid_thresholds_rejected_before_writing(self):
        for threshold in ('0', '15', '101', 'nan'):
            with self.subTest(threshold=threshold), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.parse(['--battery', '--suspend-at', threshold])

    def test_uninstall_does_not_require_desktop_user(self):
        args = installer.parse_args(['--lid', '--uninstall'])
        self.assertTrue(all(value is None for value in installer.build_plan(args).values()))

    def test_failed_battery_verification_restores_original_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'battery.conf'
            config.write_text('original')
            config.chmod(0o640)
            calls = []
            def command(*args):
                calls.append(args)
                return 's "PowerOff"' if args[0] == 'busctl' else ''
            args = self.parse(['--battery'])
            with patch.object(installer, 'BACKUPS', Path(tmp) / 'backups'), patch.object(installer, 'run', side_effect=command):
                with self.assertRaisesRegex(RuntimeError, 'did not select Suspend'):
                    installer.apply_plan(args, {config: b'new'})
            self.assertEqual(config.read_text(), 'original')
            self.assertEqual(config.stat().st_mode & 0o777, 0o640)
            self.assertEqual(calls.count(('systemctl', 'restart', 'upower.service')), 2)

    def test_battery_uninstall_leaves_unrelated_files_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'battery.conf'
            other = Path(tmp) / 'lid.conf'
            config.write_text('override')
            other.write_text('unchanged')
            args = self.parse(['--battery', '--uninstall'])
            with patch.object(installer, 'BACKUPS', Path(tmp) / 'backups'), patch.object(installer, 'run'), contextlib.redirect_stdout(io.StringIO()):
                installer.apply_plan(args, {config: None})
            self.assertFalse(config.exists())
            self.assertEqual(other.read_text(), 'unchanged')

    def test_failed_update_restores_existing_service_activation_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'lid.conf'
            config.write_text('old lid config')
            calls = []
            def command(*args):
                calls.append(args)
                if args[0] == 'busctl':
                    return 's "PowerOff"'
                return ''
            args = self.parse(['--lid', '--user', 'desktop-user', '--battery'])
            with patch.object(installer, 'BACKUPS', Path(tmp) / 'backups'), \
                 patch.object(installer, 'run', side_effect=command), \
                 patch.object(installer.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                with self.assertRaises(RuntimeError):
                    installer.apply_plan(args, {config: b'new config'})
            self.assertEqual(config.read_text(), 'old lid config')
            self.assertIn(('systemctl', 'stop', installer.SERVICE), calls)
            self.assertIn(('systemctl', 'enable', installer.SERVICE), calls)
            self.assertIn(('systemctl', 'start', installer.SERVICE), calls)


if __name__ == '__main__':
    unittest.main()
