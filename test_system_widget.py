import importlib.machinery
import importlib.util
from pathlib import Path
import json
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from test_vless_profiles import sample
import vless_profiles

loader = importlib.machinery.SourceFileLoader('xray_widget_system', str(Path(__file__).with_name('xray-widget-system')))
spec = importlib.util.spec_from_loader(loader.name, loader)
widget = importlib.util.module_from_spec(spec)
loader.exec_module(widget)


PORTS = {'primary': {'http': 10809, 'socks': 10808}, 'secondary': {'http': 10819, 'socks': 10818}}


class SystemWidgetTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'id': 'throne-0', 'name': 'VLESS', 'source': 'Ноутбук', 'outbound': vless_profiles.convert_profile(sample())}
        groups = [{'name': name, 'kind': 'links', 'value': []} for name in ('Ноутбук', 'ПК', 'BlancVPN')]
        for obj, name, value in [(widget, 'service_pid', 123), (widget, 'read_state', {}),
                                 (widget.widget_config, 'load', (groups, {}, [])),
                                 (widget.profile_sources, 'collect', ([self.profile], [], [])),
                                 (widget.widget_config, 'load_system', ('xray-alex-direct.service', PORTS)),
                                 (widget, 'listening', True)]:
            p = mock.patch.object(obj, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(widget.PORTS, PORTS)
        p.start()
        self.addCleanup(p.stop)

    def test_status_exposes_profiles_not_credentials(self):
        with mock.patch.object(widget, 'command', return_value=0) as command:
            state = widget.main(['status'])
        self.assertTrue(state['running'])
        self.assertEqual(state['selected'], 'current')
        self.assertEqual([x['id'] for x in state['profiles']], ['throne-0'])
        self.assertNotIn('00000000-0000-4000-8000-000000000001', json.dumps(state))
        command.assert_called_once_with(['/usr/bin/systemctl', '--system', 'is-active', '--quiet', 'xray-alex-direct.service'])

    def test_selected_profile_requires_matching_service_pid(self):
        widget.read_state.return_value = {'pid': 123, 'selected': 'throne-0', 'baseline': True}
        with mock.patch.object(widget, 'command', return_value=0):
            state = widget.status('xray-alex-direct.service')
            self.assertEqual(state['selected'], 'throne-0')
            self.assertNotIn('original', [x['id'] for x in state['profiles']])
            widget.service_pid.return_value = 124
            self.assertEqual(widget.status('xray-alex-direct.service')['selected'], 'current')

    def test_active_duplicate_maps_to_one_catalog_entry(self):
        imported = {'id': 'throne-0', 'name': 'Другое имя', 'source': 'ПК', 'outbound': self.profile['outbound']}
        widget.profile_sources.collect.return_value = ([self.profile, imported], [], [])
        widget.read_state.return_value = {'pid': 123, 'selected': 'throne-0', 'baseline': True}
        with mock.patch.object(widget, 'command', return_value=0):
            state = widget.status('xray-alex-direct.service')
        self.assertEqual(state['selected'], 'throne-0')
        self.assertEqual(len(state['profiles']), 1)
        self.assertEqual(len(state['profiles'][0]['aliases']), 2)

    def test_non_vless_profiles_remain_visible_as_unavailable(self):
        missing = {'id': 'adpc-3', 'name': 'WG', 'source': 'ПК', 'kind': 'WireGuard', 'reason': 'Пока не поддерживается.'}
        widget.profile_sources.collect.return_value = ([self.profile], [missing], [])
        with mock.patch.object(widget, 'command', return_value=0):
            state = widget.status('xray-alex-direct.service')
        item = next(item for item in state['profiles'] if item['id'] == 'adpc-3')
        self.assertFalse(item['available'])
        self.assertEqual((item['title'], item['transport'], item['descriptions']), ('WG', 'WireGuard', ['Пока не поддерживается.']))
        self.assertEqual(item['aliases'][0]['source'], 'ПК')

    def test_reports_unsupported_profiles(self):
        widget.widget_config.load.return_value = ([], {}, ['Ошибка настроек.'])
        widget.profile_sources.collect.return_value = ([self.profile], [], ['Ошибка профиля.', 'Ошибка профиля.'])
        with mock.patch.object(widget, 'command', return_value=0):
            self.assertEqual(widget.status('xray-alex-direct.service')['warning'], 'Ошибка настроек. Ошибка профиля.')

    def test_stopped_service_and_status_error_are_distinct(self):
        with mock.patch.object(widget, 'command', return_value=3):
            self.assertFalse(widget.status('xray-alex-direct.service')['running'])
        with mock.patch.object(widget, 'command', return_value=1), self.assertRaises(RuntimeError):
            widget.status('xray-alex-direct.service')

    def test_restart_requests_privilege_only_when_clicked(self):
        with mock.patch.object(widget, 'command', side_effect=[0, 0]) as command:
            widget.main(['restart'])
        self.assertEqual(command.call_args_list[0], mock.call(['/usr/bin/pkexec', '/usr/bin/systemctl', 'restart', 'xray-alex-direct.service'], timeout=120))

    def test_denied_restart_is_an_error(self):
        with mock.patch.object(widget, 'command', return_value=126), self.assertRaises(RuntimeError):
            widget.main(['restart'])

    def test_selection_is_temporarily_blocked_without_elevation(self):
        with mock.patch.object(widget, 'PROFILE_SWITCH_ENABLED', False), mock.patch.object(widget.subprocess, 'run') as run, self.assertRaisesRegex(RuntimeError, 'временно отключена'):
            widget.select_profile('primary', 'throne-0')
        run.assert_not_called()

    def test_select_sends_credentials_via_stdin_not_argv(self):
        admin = mock.MagicMock()
        admin.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFREG | 0o755, st_uid=0)
        admin.__str__.return_value = '/root/helper'
        with mock.patch.object(widget, 'PROFILE_SWITCH_ENABLED', True), mock.patch.object(widget, 'ADMIN', admin), mock.patch.object(widget.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='{"ok": true}')) as run:
            widget.select_profile('primary', 'throne-0')
        self.assertNotIn('00000000-0000-4000-8000-000000000001', str(run.call_args.args))
        self.assertIn('00000000-0000-4000-8000-000000000001', run.call_args.kwargs['input'])

    def test_success_is_reported_only_for_confirmed_profile(self):
        state = {'running': True, 'selected': 'throne-0', 'profiles': []}
        with mock.patch.object(widget, 'select_profile'), mock.patch.object(widget, 'status', return_value=state):
            result = widget.main(['select', 'throne-0'])
        self.assertTrue(result['https_checked'])
        with mock.patch.object(widget, 'select_profile'), mock.patch.object(widget, 'status', return_value={'running': True, 'selected': 'current'}):
            with self.assertRaisesRegex(RuntimeError, 'не подтверждено'):
                widget.main(['select', 'throne-0'])

    def test_success_accepts_selected_alias_of_same_profile(self):
        state = {'running': True, 'selected': 'throne-0', 'profiles': [{'id': 'throne-0', 'aliases': [{'id': 'adpc-2'}]}]}
        with mock.patch.object(widget, 'select_profile'), mock.patch.object(widget, 'status', return_value=state):
            result = widget.main(['select', 'adpc-2'])
        self.assertTrue(result['https_checked'])

    def test_unknown_actions_and_missing_settings_are_rejected(self):
        for args in (['select', 'a', 'b'], ['enable', 'third', 'on'], ['stop']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                widget.main(args)
        widget.widget_config.load_system.side_effect = ValueError('Нет файла /etc/xray-widget/system.toml.')
        with self.assertRaisesRegex(ValueError, 'system.toml'):
            widget.main(['status'])

    def test_service_and_ports_come_from_system_settings(self):
        widget.widget_config.load_system.return_value = ('xray.service', {'primary': {'http': 20809, 'socks': 20808}, 'secondary': {'http': 20819, 'socks': 20818}})
        with mock.patch.object(widget, 'command', return_value=0) as command:
            state = widget.main(['status'])
        self.assertEqual(command.call_args.args[0][-1], 'xray.service')
        self.assertEqual((state['ports']['http'], state['secondary']['ports']['socks']), (20809, 20818))

    def test_timeout_is_not_silenced(self):
        with mock.patch.object(widget, 'command', side_effect=subprocess.TimeoutExpired('systemctl', 10)), self.assertRaises(subprocess.TimeoutExpired):
            widget.status('xray-alex-direct.service')


    def test_second_proxy_is_off_until_chosen_and_unknown_after_foreign_restart(self):
        widget.read_state.return_value = {'pid': 123, 'selected': 'throne-0', 'baseline': True}
        with mock.patch.object(widget, 'command', return_value=0):
            state = widget.status('xray-alex-direct.service')
            self.assertEqual(state['secondary']['selected'], 'none')
            self.assertEqual([x['id'] for x in state['secondary']['profiles']], ['throne-0'])
            self.assertEqual((state['enabled'], state['secondary']['enabled']), (True, True))
            widget.read_state.return_value = {'pid': 123, 'slots': {'primary': 'throne-0', 'secondary': 'throne-0'}, 'baseline': True}
            state = widget.status('xray-alex-direct.service')
            self.assertEqual((state['selected'], state['secondary']['selected']), ('throne-0', 'throne-0'))
            widget.service_pid.return_value = 124
            state = widget.status('xray-alex-direct.service')
            self.assertEqual((state['selected'], state['secondary']['selected']), ('current', 'current'))

    def test_subscription_profiles_join_the_catalog(self):
        subscribed = {'id': 'sub-0123456789ab', 'name': 'Амстердам', 'source': 'BlancVPN', 'outbound': vless_profiles.convert_profile(sample())}
        subscribed['outbound']['settings']['vnext'][0]['address'] = 'nl.example.com'
        widget.profile_sources.collect.return_value = ([self.profile, subscribed], [], ['Подписку BlancVPN не удалось обновить.'])
        with mock.patch.object(widget, 'command', return_value=0):
            state = widget.status('xray-alex-direct.service')
        aliases = [alias for item in state['secondary']['profiles'] for alias in item.get('aliases', [])]
        self.assertIn({'id': 'sub-0123456789ab', 'name': 'Амстердам', 'source': 'BlancVPN'}, aliases)
        self.assertIn('BlancVPN', state['warning'])

    def test_select_secondary_targets_its_slot(self):
        state = {'running': True, 'selected': 'current', 'profiles': [], 'secondary': {'selected': 'throne-0', 'profiles': []}}
        with mock.patch.object(widget, 'select_profile') as select, mock.patch.object(widget, 'status', return_value=state):
            result = widget.main(['select-secondary', 'throne-0'])
        select.assert_called_once_with('secondary', 'throne-0')
        self.assertTrue(result['https_checked'])

    def test_enable_switches_slot_and_confirms_by_open_port(self):
        state = {'running': True, 'selected': 'current', 'profiles': [], 'enabled': True, 'secondary': {'selected': 'throne-0', 'profiles': [], 'enabled': False}}
        with mock.patch.object(widget, 'run_admin') as admin, mock.patch.object(widget, 'status', return_value=state):
            result = widget.main(['enable', 'secondary', 'off'])
            admin.assert_called_once_with({'action': 'enable', 'slot': 'secondary', 'enabled': False})
            self.assertFalse(result['https_checked'])
            with self.assertRaisesRegex(RuntimeError, 'не подтверждено'):
                widget.main(['enable', 'secondary', 'on'])
        for args in (['enable', 'third', 'on'], ['enable', 'primary', 'yes']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                widget.main(args)

    def test_stopped_service_reports_both_proxies_off_without_probing(self):
        with mock.patch.object(widget, 'command', return_value=3):
            state = widget.status('xray-alex-direct.service')
        self.assertEqual((state['enabled'], state['secondary']['enabled']), (False, False))
        widget.listening.assert_not_called()

    def test_special_ids_do_not_send_outbound(self):
        admin = mock.MagicMock()
        admin.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFREG | 0o755, st_uid=0)
        admin.__str__.return_value = '/root/helper'
        with mock.patch.object(widget, 'ADMIN', admin), mock.patch.object(widget.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='{"ok": true}')) as run:
            widget.select_profile('primary', 'original')
        self.assertEqual(json.loads(run.call_args.kwargs['input']), {'action': 'select', 'slot': 'primary', 'id': 'original'})
        with mock.patch.object(widget, 'ADMIN', admin), self.assertRaises(ValueError):
            widget.select_profile('secondary', 'original')

    def make_profile(self, profile_id, name, address, source):
        item = {'id': profile_id, 'name': name, 'source': source, 'outbound': vless_profiles.convert_profile(sample())}
        item['outbound']['settings']['vnext'][0]['address'] = address
        return item

    def test_profiles_follow_group_order_from_config_and_sort_by_title(self):
        widget.profile_sources.collect.return_value = ([
            self.make_profile('p-3', 'Амстердам', 'd.example.com', 'BlancVPN'), self.make_profile('p-4', '🇦🇪 Фуджейра', 'e.example.com', 'BlancVPN'), self.make_profile('p-1', 'beta', 'c.example.com', 'ПК'),
            self.make_profile('p-0', 'zeta', 'a.example.com', 'Ноутбук'), self.make_profile('p-2', 'Alpha', 'b.example.com', 'Ноутбук'),
            self.make_profile('p-0', 'same', 'a.example.com', 'ПК')], [], [])
        with mock.patch.object(widget, 'command', return_value=0):
            state = widget.status('xray-alex-direct.service')
        rows = [(x['title'], x['aliases'][0]['source']) for x in state['profiles']]
        self.assertEqual(rows, [('Alpha', 'Ноутбук'), ('zeta', 'Ноутбук'), ('beta', 'ПК'), ('Амстердам', 'BlancVPN'), ('🇦🇪 Фуджейра', 'BlancVPN')])
        merged = state['profiles'][1]['aliases']
        self.assertEqual([(a['name'], a['source']) for a in merged], [('zeta', 'Ноутбук'), ('same', 'ПК')])

    def test_labels_rename_profiles_by_any_original_name(self):
        widget.widget_config.load.return_value = ([], {'VLESS': '🇩🇪 Наш сервер', 'unused': 'x'}, [])
        with mock.patch.object(widget, 'command', return_value=0):
            state = widget.status('xray-alex-direct.service')
        self.assertEqual(state['profiles'][0]['title'], '🇩🇪 Наш сервер')

    def test_subscriptions_refresh_when_stale_forced_or_not_at_all(self):
        with mock.patch.object(widget, 'command', return_value=0):
            widget.main(['status'])
            self.assertEqual(widget.profile_sources.collect.call_args.args[2], 'stale')
            widget.main(['refresh'])
            self.assertEqual(widget.profile_sources.collect.call_args.args[2], 'force')
        self.assertEqual(widget.load_outbound('throne-0'), self.profile['outbound'])
        self.assertIsNone(widget.profile_sources.collect.call_args.args[2])
        with self.assertRaisesRegex(ValueError, 'не найден'):
            widget.load_outbound('p-ffffffffffff')

    def test_ping_measures_google_and_reports_exit_through_tunnel_port(self):
        trace = 'fl=1\nh=www.cloudflare.com\nip=203.0.113.7\nloc=NL\n'
        with mock.patch.object(widget.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='\n@204 0.182345\n' + trace + '\n@200 0.05\n', stderr='')) as run:
            self.assertEqual(widget.ping('secondary'), {'slot': 'secondary', 'ok': True, 'ms': 182, 'ip': '203.0.113.7', 'country': 'NL'})
        args = run.call_args.args[0]
        self.assertEqual(args[args.index('--proxy') + 1], 'http://127.0.0.1:10819')
        self.assertEqual(args[-2:], ['https://www.google.com/generate_204', 'https://www.cloudflare.com/cdn-cgi/trace'])
        with mock.patch.object(widget.subprocess, 'run', return_value=SimpleNamespace(returncode=28, stdout='\n@204 0.3\n\n@000 10.0\n', stderr='')):
            self.assertEqual(widget.ping('primary'), {'slot': 'primary', 'ok': True, 'ms': 300})
        for output in ('\n@403 0.1\n', '\n@000 10.0\n\n@000 10.0\n', ''):
            with self.subTest(output=output), mock.patch.object(widget.subprocess, 'run', return_value=SimpleNamespace(returncode=28, stdout=output, stderr='')):
                self.assertEqual(widget.ping('primary'), {'slot': 'primary', 'ok': False})
        with mock.patch.object(widget, 'ping', return_value={'slot': 'primary', 'ok': True, 'ms': 5}), mock.patch.object(widget, 'command', return_value=0):
            self.assertEqual(widget.main(['ping', 'primary'])['ping']['ms'], 5)
        for args in (['ping', 'third'], ['ping']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                widget.main(args)

if __name__ == '__main__':
    unittest.main()
