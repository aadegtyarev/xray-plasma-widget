import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import profile_sources
import adpc_profiles
from test_adpc_profiles import admin, sample as adpc_sample, wireguard_bean
from test_subscription_profiles import REALITY, WEBSOCKET
from test_vless_profiles import sample as throne_sample
import vless_profiles


class FolderGroupTests(unittest.TestCase):
    def test_each_file_is_an_xray_outbound_named_after_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            folder.chmod(0o700)
            vless = vless_profiles.convert_profile(throne_sample())
            (folder / '🇩🇪 Наш сервер.json').write_text(json.dumps(dict(vless, tag='proxy')))
            (folder / 'wg.json').write_text(json.dumps(adpc_profiles.wireguard_outbound(wireguard_bean())))
            (folder / 'notes.txt').write_text('x')
            found, missing, errors = profile_sources.folder_group('Мои', folder)
        self.assertEqual(([item['name'] for item in found], missing, errors), (['wg', '🇩🇪 Наш сервер'], [], []))
        self.assertEqual(found[1]['id'], profile_sources.profile('x', 'y', dict(vless, tag='proxy-primary'))['id'])
        for item in found:
            self.assertEqual(item['source'], 'Мои')
            admin.validate_outbound(item['outbound'])

    def test_unsupported_and_broken_files_stay_visible_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'a.json').write_text(json.dumps({'protocol': 'trojan', 'settings': {}}))
            (folder / 'b.json').write_text('{broken')
            (folder / 'c.json').write_text(json.dumps({'protocol': 'vless', 'settings': {}}))
            (folder / 'd.json').symlink_to(folder / 'a.json')
            folder.chmod(0o755)
            found, missing, errors = profile_sources.folder_group('Мои', folder)
        self.assertEqual(found, [])
        self.assertEqual([item['name'] for item in missing], ['a', 'b', 'c', 'd'])
        self.assertTrue(all(item['id'].startswith('n-') and item['reason'] for item in missing))
        self.assertIn('chmod 700', errors[0])

    def test_missing_folder_is_reported(self):
        self.assertEqual(profile_sources.folder_group('Мои', '/nonexistent/xray')[2], ['Группа «Мои»: папка /nonexistent/xray не найдена.'])


class LinksTests(unittest.TestCase):
    def test_links_become_profiles_and_unsupported_links_are_listed(self):
        found, missing = profile_sources.links_group('Друзья', [REALITY, WEBSOCKET, 'trojan://secret@example.com:443#Троян'])
        self.assertEqual([item['name'] for item in found], ['🇳🇱 Амстердам', 'Germany'])
        self.assertEqual([(item['name'], item['kind']) for item in missing], [('Троян', 'Trojan')])
        self.assertNotIn('secret', json.dumps(missing))

    def test_saved_links_are_known_by_settings(self):
        def ident(link, group='A'):
            return profile_sources.links_group(group, [link])[0][0]['id']
        self.assertEqual(ident(REALITY.split('#')[0] + '#Другое имя', 'B'), ident(REALITY))
        for other in (WEBSOCKET, REALITY.replace('sid=ab12', 'sid=cd34'), REALITY.replace('0001@', '0002@')):
            self.assertNotEqual(ident(other), ident(REALITY))

    def test_subscription_profiles_are_known_by_group_and_name(self):
        def ids(links, group='BlancVPN'):
            return [item['id'] for item in profile_sources.links_group(group, links, by_name=True)[0]]
        reshuffled = REALITY.replace('sid=ab12', 'sid=cd34').replace('sni=www.example.org', 'sni=other.example.org')
        self.assertEqual(ids([reshuffled]), ids([REALITY]))
        self.assertNotEqual(ids([REALITY], 'Другая'), ids([REALITY]))
        twins = ids([REALITY, reshuffled])
        self.assertEqual(len(set(twins)), 2)
        self.assertEqual(twins[0], ids([REALITY])[0])

    def test_collect_walks_groups_in_order_and_passes_refresh_mode(self):
        store = mock.Mock()
        store.links.return_value = ([WEBSOCKET], ['Подписку BlancVPN не удалось обновить.'])
        groups = [{'name': 'Свои', 'kind': 'links', 'value': [REALITY]},
                  {'name': 'BlancVPN', 'kind': 'subscription', 'value': 'https://sub.example.com/token'},
                  {'name': 'Мои', 'kind': 'folder', 'value': '/nonexistent/xray'}]
        found, missing, errors = profile_sources.collect(groups, store, 'force')
        store.links.assert_called_once_with('BlancVPN', 'https://sub.example.com/token', 'force')
        self.assertEqual([(item['source'], item['name']) for item in found], [('Свои', '🇳🇱 Амстердам'), ('BlancVPN', 'Germany')])
        self.assertEqual(missing, [])
        self.assertEqual(len(errors), 2)


if __name__ == '__main__':
    unittest.main()
