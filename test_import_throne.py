import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_adpc_profiles import sample as adpc_sample, wireguard_bean
from test_vless_profiles import sample as throne_sample

loader = importlib.machinery.SourceFileLoader('import_throne', str(Path(__file__).with_name('import-throne')))
spec = importlib.util.spec_from_loader(loader.name, loader)
tool = importlib.util.module_from_spec(spec)
loader.exec_module(tool)


class ImportThroneTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source, self.target = Path(tmp.name) / 'throne', Path(tmp.name) / 'widget' / 'profiles'
        self.source.mkdir()

    def write(self, number, data):
        (self.source / (str(number) + '.json')).write_text(json.dumps(data))

    def test_both_throne_formats_and_wireguard_become_private_xray_files(self):
        self.write(0, throne_sample())
        self.write(1, adpc_sample())
        self.write(2, {'type': 'wireguard', 'bean': wireguard_bean()})
        leftover = dict(throne_sample(), bean={'name': '', 'addr': 'old.example.com', 'port': 1080, 'stream': {'net': 'tcp'}})
        leftover['outbound']['name'] = 'Новый / Throne'
        leftover['outbound']['server'] = 'new.example.com'
        self.write(3, leftover)
        report = tool.import_folder(self.source, self.target)
        self.assertEqual([(mark, note) for mark, _, note in report],
                         [('+', 'Пример.json'), ('+', 'Первичный.json'), ('+', 'wg.json'), ('+', 'Новый - Throne.json')])
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o700)
        for path in self.target.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('tag', json.loads(path.read_text()))

    def test_repeated_import_skips_known_settings_and_keeps_existing_files(self):
        self.write(0, throne_sample())
        tool.import_folder(self.source, self.target)
        (self.target / 'Пример.json').rename(self.target / 'Мой сервер.json')
        other = throne_sample()
        other['outbound']['server'] = 'other.example.com'
        self.write(1, other)
        self.write(2, {'type': 'custom', 'bean': {'name': 'Свой'}})
        report = tool.import_folder(self.source, self.target)
        self.assertEqual([(mark, note) for mark, _, note in report],
                         [('=', 'такой профиль уже есть'), ('+', 'Пример.json'), ('-', 'тип профиля custom не поддерживается')])

    def test_output_has_no_secrets(self):
        self.write(0, throne_sample())
        with mock.patch('sys.stdout', new_callable=io.StringIO) as out:
            self.assertEqual(tool.main([str(self.source), str(self.target)]), 0)
        self.assertNotIn('00000000-0000-4000-8000-000000000001', out.getvalue())
        self.assertIn('Перенесено: 1 из 1.', out.getvalue())


if __name__ == '__main__':
    unittest.main()
