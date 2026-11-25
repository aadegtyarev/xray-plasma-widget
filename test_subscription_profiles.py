import base64
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import subscription_profiles as subscriptions

loader = importlib.machinery.SourceFileLoader('xray_profile_admin', str(Path(__file__).with_name('xray-system-profile-admin')))
spec = importlib.util.spec_from_loader(loader.name, loader)
admin = importlib.util.module_from_spec(spec)
loader.exec_module(admin)

USER = '00000000-0000-4000-8000-000000000001'
REALITY = 'vless://' + USER + '@nl.example.com:443?security=reality&encryption=none&fp=firefox&headerType=none&type=tcp&flow=xtls-rprx-vision&sni=www.example.org&pbk=public-key&sid=ab12#%F0%9F%87%B3%F0%9F%87%B1%20%D0%90%D0%BC%D1%81%D1%82%D0%B5%D1%80%D0%B4%D0%B0%D0%BC'
WEBSOCKET = 'vless://' + USER + '@de.example.com:443?security=tls&encryption=none&fp=firefox&type=ws&flow=&sni=cdn.example.org&host=cdn.example.org&path=%2Fws#Germany'


class LinkTests(unittest.TestCase):
    def test_reality_link_becomes_valid_outbound(self):
        outbound = subscriptions.convert_link(REALITY)
        self.assertEqual(subscriptions.link_name(REALITY), '🇳🇱 Амстердам')
        reality = outbound['streamSettings']['realitySettings']
        self.assertEqual((reality['serverName'], reality['fingerprint'], reality['password'], reality['shortId']), ('www.example.org', 'firefox', 'public-key', 'ab12'))
        admin.validate_outbound(outbound)

    def test_websocket_link_keeps_host_and_path(self):
        outbound = subscriptions.convert_link(WEBSOCKET)
        stream = outbound['streamSettings']
        self.assertEqual(stream['wsSettings'], {'path': '/ws', 'host': 'cdn.example.org'})
        self.assertEqual(stream['tlsSettings']['serverName'], 'cdn.example.org')
        admin.validate_outbound(outbound)

    def test_unsupported_links_are_rejected(self):
        for link in ('trojan://secret@example.com:443#x', REALITY.replace('encryption=none', 'encryption=mlkem'),
                     WEBSOCKET.replace('type=ws', 'type=ws&allowInsecure=1'), REALITY.replace('type=tcp', 'type=grpc'),
                     REALITY.replace('sid=ab12', 'sid=ab12&sid=cd34'), REALITY.replace('&pbk=public-key', '')):
            with self.subTest(link=link[:40]), self.assertRaises(ValueError):
                subscriptions.convert_link(link)

    def test_decodes_base64_and_plain_lists(self):
        plain = (REALITY + '\n' + WEBSOCKET + '\n').encode()
        self.assertEqual(subscriptions.decode(plain), [REALITY, WEBSOCKET])
        self.assertEqual(subscriptions.decode(base64.b64encode(plain)), [REALITY, WEBSOCKET])
        self.assertEqual(subscriptions.decode(base64.urlsafe_b64encode(plain).rstrip(b'=')), [REALITY, WEBSOCKET])
        for data in (b'', b'<html>login</html>'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                subscriptions.decode(data)


class SubscriptionTests(unittest.TestCase):
    URL = 'https://sub.example.com/token'

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = subscriptions.Subscriptions(Path(tmp.name) / 'cache')

    def test_first_status_fetches_then_uses_private_cache(self):
        with mock.patch.object(subscriptions, 'fetch', return_value=[REALITY, WEBSOCKET]) as fetch:
            links, errors = self.store.links('BlancVPN', self.URL, 'stale')
            again, _ = self.store.links('BlancVPN', self.URL, 'stale')
        fetch.assert_called_once_with(self.URL)
        self.assertEqual((links, again, errors), ([REALITY, WEBSOCKET], [REALITY, WEBSOCKET], []))
        cache = self.store.cache(self.URL)
        self.assertNotIn('token', cache.name)
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
        self.assertEqual(cache.parent.stat().st_mode & 0o777, 0o700)

    def test_failed_refresh_keeps_old_links_and_waits_before_retry(self):
        with mock.patch.object(subscriptions, 'fetch', return_value=[REALITY]):
            self.store.links('BlancVPN', self.URL, 'stale')
        old = time.time() - subscriptions.REFRESH_AFTER - 10
        os.utime(self.store.cache(self.URL), (old, old))
        os.utime(self.store.attempt(self.URL), (old, old))
        with mock.patch.object(subscriptions, 'fetch', side_effect=OSError('offline')) as fetch:
            links, errors = self.store.links('BlancVPN', self.URL, 'stale')
            self.store.links('BlancVPN', self.URL, 'stale')
        fetch.assert_called_once()
        self.assertEqual((links, errors), ([REALITY], ['Подписку BlancVPN не удалось обновить.']))

    def test_forced_refresh_ignores_age_and_none_reads_only_cache(self):
        with mock.patch.object(subscriptions, 'fetch', return_value=[REALITY]) as fetch:
            self.assertEqual(self.store.links('BlancVPN', self.URL, None), ([], []))
            self.store.links('BlancVPN', self.URL, 'stale')
            self.store.links('BlancVPN', self.URL, 'force')
        self.assertEqual(fetch.call_count, 2)

    def test_only_https_is_fetched(self):
        with self.assertRaises(ValueError):
            subscriptions.fetch('http://sub.example.com/token')

if __name__ == '__main__':
    unittest.main()
