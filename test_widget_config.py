from pathlib import Path
import tempfile
import unittest

import widget_config

EXAMPLE = Path(__file__).with_name('config.example.toml')


class WidgetConfigTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.toml'
            path.write_text(text)
            return widget_config.load(path)

    def test_groups_keep_their_order_and_labels_are_cleaned(self):
        groups, labels, errors = self.load('''
[[group]]
name = "Мои"
folder = "~/.config/xray-widget/profiles"

[[group]]
name = "  BlancVPN "
subscription = "https://sub.example.com/token"

[[group]]
name = "Друзья"
links = ["vless://x@example.com:443#a"]

[labels]
"alex-xhttp" = "  🇩🇪 Наш   сервер "
''')
        self.assertEqual(errors, [])
        self.assertEqual([(g['name'], g['kind']) for g in groups], [('Мои', 'folder'), ('BlancVPN', 'subscription'), ('Друзья', 'links')])
        self.assertEqual(groups[0]['value'], str(Path.home() / '.config/xray-widget/profiles'))
        self.assertEqual(labels, {'alex-xhttp': '🇩🇪 Наш сервер'})

    def test_bad_groups_are_skipped_with_a_clear_reason(self):
        groups, labels, errors = self.load('''
[[group]]
name = "Без источника"

[[group]]
name = "Два источника"
folder = "/a"
links = []

[[group]]
name = "Небезопасная"
subscription = "http://sub.example.com"

[[group]]
name = "Хорошая"
links = []

[[group]]
name = "Хорошая"
links = []

[[group]]
name = "Опечатка"
foldr = "/a"

[labels]
"x" = 1
''')
        self.assertEqual([g['name'] for g in groups], ['Хорошая'])
        self.assertEqual(labels, {})
        self.assertEqual(len(errors), 6)
        self.assertIn('Группа «Опечатка»: неизвестный параметр foldr.', errors)

    def test_missing_and_broken_files_do_not_crash(self):
        groups, labels, errors = widget_config.load('/nonexistent/config.toml')
        self.assertEqual((groups, labels), ([], {}))
        self.assertIn('config.example.toml', errors[0])
        self.assertIn('Ошибка в', self.load('[[group]\n')[2][0])

    def test_shipped_example_is_valid(self):
        groups, labels, errors = widget_config.load(EXAMPLE)
        self.assertEqual(errors, [])
        self.assertEqual([g['kind'] for g in groups], ['folder', 'subscription', 'links'])
        self.assertTrue(labels)


    def test_system_settings_give_service_and_ports(self):
        service, ports = widget_config.load_system(Path(__file__).with_name('system.example.toml'))
        self.assertEqual((service, ports['primary'], ports['secondary']['socks']), ('xray.service', {'http': 10809, 'socks': 10808}, 10818))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'system.toml'
            for text in ('service = "x;y"', 'service = "xray.service"', 'service = "xray.service"\nports = { primary = { http = 1, socks = 2 }, secondary = { http = 3, socks = 4 } }'):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    widget_config.load_system(path)
        with self.assertRaisesRegex(ValueError, 'install.sh'):
            widget_config.load_system('/nonexistent/system.toml')

if __name__ == '__main__':
    unittest.main()
