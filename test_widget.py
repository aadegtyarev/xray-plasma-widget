import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

loader = importlib.machinery.SourceFileLoader('xray_widget', str(Path(__file__).with_name('xray-widget')))
spec = importlib.util.spec_from_loader(loader.name, loader)
widget = importlib.util.module_from_spec(spec)
loader.exec_module(widget)


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profiles = self.root / 'profiles'
        self.profiles.mkdir()
        self.active = self.root / 'primary.json'
        self.active.write_bytes(b'old profile secret')
        for name, value in [('ROOT', self.root), ('PROFILES', self.profiles), ('ACTIVE', self.active)]:
            patcher = mock.patch.object(widget, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_profile(self, name='new', port=20172, address='127.0.0.1', protocol='http'):
        p = self.profiles / (name + '.json')
        p.write_text(json.dumps({'inbounds': [{'listen': address, 'port': port, 'protocol': protocol}]}))
        return p

    def test_validate_requires_single_loopback_http_port_and_xray_check(self):
        with mock.patch.object(widget, 'run', return_value=True) as run:
            self.assertTrue(widget.validate_profile(self.make_profile()))
            self.assertFalse(widget.validate_profile(self.make_profile(port=9999)))
            self.assertFalse(widget.validate_profile(self.make_profile(address='0.0.0.0')))
            self.assertFalse(widget.validate_profile(self.make_profile(protocol='socks')))
            self.assertEqual(run.call_count, 1)

    def test_selection_restarts_and_preserves_private_mode(self):
        profile = self.make_profile()
        with mock.patch.object(widget, 'run', return_value=True), mock.patch.object(widget, 'restart') as restart:
            widget.select('new')
        self.assertEqual(self.active.read_bytes(), profile.read_bytes())
        self.assertEqual(self.active.stat().st_mode & 0o777, 0o600)
        restart.assert_called_once()

    def test_failure_rolls_back_and_restarts_previous_profile(self):
        self.make_profile()
        with mock.patch.object(widget, 'run', return_value=True), mock.patch.object(widget, 'restart', side_effect=[RuntimeError('failed'), None]) as restart:
            with self.assertRaisesRegex(RuntimeError, 'восстановлен'):
                widget.select('new')
        self.assertEqual(self.active.read_bytes(), b'old profile secret')
        self.assertEqual(restart.call_count, 2)

    def test_rejects_traversal_and_symlink(self):
        (self.profiles / 'evil.json').symlink_to(self.active)
        for name in ('../primary', 'evil', 'x;touch x'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                widget.select(name)

    def test_status_identifies_active_without_exposing_contents(self):
        p = self.profiles / 'active.json'
        p.write_bytes(self.active.read_bytes())
        with mock.patch.object(widget, 'run', return_value=True):
            result = widget.status()
        self.assertTrue(result['running'])
        self.assertEqual(result['selected'], 'active')
        self.assertNotIn('secret', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
