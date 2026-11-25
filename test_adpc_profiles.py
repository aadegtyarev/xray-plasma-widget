import copy
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

import adpc_profiles


def sample():
    return {
        'type': 'vless', 'bean': {
            'name': 'Первичный', 'addr': 'example.com', 'port': 443,
            'pass': '00000000-0000-4000-8000-000000000001', 'flow': '',
            'mux': 0, 'enable_brutal': False, 'c_cfg': '', 'c_out': '',
            'stream': {'net': 'tcp', 'sec': 'tls', 'sni': 'example.com', 'utls': 'chrome',
                       'pbk': 'test-public-key', 'sid': '1234', 'pac_enc': 'xudp'},
        },
    }


loader = importlib.machinery.SourceFileLoader('xray_profile_admin', str(Path(__file__).with_name('xray-system-profile-admin')))
spec = importlib.util.spec_from_loader(loader.name, loader)
admin = importlib.util.module_from_spec(spec)
loader.exec_module(admin)


def wireguard_bean():
    return {'name': 'wg', 'addr': 'wg.example.com', 'port': 3389, 'local_address': ['10.66.66.2/32'], 'mtu': 1420,
            'persistent_keepalive': 16, 'private_key': 'A' * 43 + '=', 'public_key': 'B' * 43 + '=',
            'pre_shared_key': 'C' * 43 + '=', 'enable_amnezia': False, 'worker_count': 0, 'use_system_proxy': False}


class AdpcProfilesTests(unittest.TestCase):
    def test_reality_conversion(self):
        result = adpc_profiles.convert_profile_from_adpc(sample())
        self.assertEqual(result['streamSettings']['security'], 'reality')
        self.assertEqual(result['streamSettings']['realitySettings']['fingerprint'], 'chrome')
        self.assertEqual(result['mux']['xudpConcurrency'], 8)

    def test_websocket_preserves_host_path_and_alpn(self):
        item = sample()
        stream = item['bean']['stream']
        stream.update({'net': 'ws', 'pbk': '', 'host': 'cdn.example.com', 'path': '/socket', 'alpn': 'http/1.1'})
        result = adpc_profiles.convert_profile_from_adpc(item)
        self.assertEqual(result['streamSettings']['wsSettings'], {'path': '/socket', 'host': 'cdn.example.com'})
        self.assertEqual(result['streamSettings']['tlsSettings']['alpn'], ['http/1.1'])

    def test_xhttp_uses_only_matched_saved_xray_outbound(self):
        item = sample()
        item['bean']['stream'].update({'net': 'xhttp', 'pbk': ''})
        saved = {'tag': 'proxy-primary', 'protocol': 'vless',
                 'settings': {'vnext': [{'address': 'example.com', 'port': 443,
                                         'users': [{'id': '00000000-0000-4000-8000-000000000001', 'encryption': 'none'}]}]},
                 'streamSettings': {'network': 'xhttp', 'security': 'tls',
                                    'tlsSettings': {'serverName': 'example.com', 'fingerprint': 'chrome', 'allowInsecure': False},
                                    'xhttpSettings': {'path': '/xhttp', 'host': 'example.com', 'mode': 'packet-up'}}}
        result = adpc_profiles.convert_profile_from_adpc(item, saved)
        self.assertEqual(result['streamSettings']['xhttpSettings']['path'], '/xhttp')
        self.assertNotIn('mux', result)
        bad = copy.deepcopy(saved)
        bad['settings']['vnext'][0]['address'] = 'other.example'
        with self.assertRaisesRegex(ValueError, 'не совпадает'):
            adpc_profiles.convert_profile_from_adpc(item, bad)

    def test_unsupported_extra_options_are_not_silently_dropped(self):
        for option in ('c_out', 'mux', 'insecure', 'headers'):
            item = sample()
            if option == 'c_out': item['bean']['c_out'] = '{}'
            if option == 'mux': item['bean']['mux'] = 1
            if option == 'insecure': item['bean']['stream']['insecure'] = True
            if option == 'headers': item['bean']['stream']['headers'] = 'x: y'
            with self.subTest(option=option), self.assertRaises(ValueError):
                adpc_profiles.convert_profile_from_adpc(item)

    def test_wireguard_becomes_userspace_xray_outbound(self):
        outbound = adpc_profiles.wireguard_outbound(wireguard_bean())
        self.assertEqual(outbound['protocol'], 'wireguard')
        settings = outbound['settings']
        self.assertTrue(settings['noKernelTun'])
        self.assertEqual(settings['domainStrategy'], 'ForceIPv4')
        self.assertEqual(settings['peers'][0]['endpoint'], 'wg.example.com:3389')
        self.assertEqual(settings['peers'][0]['keepAlive'], 16)
        self.assertEqual(settings['peers'][0]['preSharedKey'], 'C' * 43 + '=')
        admin.validate_outbound(outbound)
        dual = adpc_profiles.wireguard_outbound(dict(wireguard_bean(), local_address=['10.0.0.2/32', 'fd00::2/128'], pre_shared_key=''))
        self.assertEqual(dual['settings']['domainStrategy'], 'ForceIP')
        self.assertNotIn('preSharedKey', dual['settings']['peers'][0])



if __name__ == '__main__':
    unittest.main()
