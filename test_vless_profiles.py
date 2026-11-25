import copy
import unittest

import vless_profiles as profiles


def sample():
    return {
        'type': 'vless',
        'outbound': {
            'name': 'Пример', 'server': 'example.com', 'server_port': 443,
            'uuid': '00000000-0000-4000-8000-000000000001', 'flow': 'xtls-rprx-vision',
            'packet_encoding': 'xudp', 'multiplex': {'enabled': False}, 'dial_fields': {},
            'transport': {'type': 'tcp'},
            'tls': {'enabled': True, 'server_name': 'example.com', 'insecure': False,
                    'utls': {'enabled': True, 'fingerprint': 'chrome'},
                    'reality': {'enabled': True, 'public_key': 'test-public-key', 'short_id': '1234'}},
        },
    }


class VlessProfileTests(unittest.TestCase):
    def test_converts_reality(self):
        output = profiles.convert_profile(sample())
        self.assertEqual(output['protocol'], 'vless')
        self.assertEqual(output['streamSettings']['security'], 'reality')
        self.assertEqual(output['streamSettings']['realitySettings']['fingerprint'], 'chrome')
        self.assertEqual(output['settings']['vnext'][0]['users'][0]['flow'], 'xtls-rprx-vision')
        self.assertEqual(output['mux'], {'enabled': True, 'concurrency': -1, 'xudpConcurrency': 8})

    def test_rejects_unsupported_and_invalid_without_echoing_secrets(self):
        for change in ('udp', 'insecure', 'uuid', 'flow', 'ech', 'encoding'):
            source = copy.deepcopy(sample())
            if change == 'udp': source['outbound']['transport']['type'] = 'ws'
            if change == 'insecure': source['outbound']['tls']['insecure'] = True
            if change == 'uuid': source['outbound']['uuid'] = 'secret-uuid-value'
            if change == 'flow': source['outbound']['flow'] = 'unsupported'
            if change == 'ech': source['outbound']['tls']['ech'] = {'enabled': True}
            if change == 'encoding': source['outbound']['packet_encoding'] = 'unsupported'
            with self.subTest(change=change), self.assertRaises(ValueError) as error:
                profiles.convert_profile(source)
            self.assertNotIn('secret-uuid-value', str(error.exception))



if __name__ == '__main__':
    unittest.main()
