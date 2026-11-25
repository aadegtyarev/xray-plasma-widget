import copy
import unittest

from profile_catalog import catalog, representative
from vless_profiles import convert_profile
from test_vless_profiles import sample


def profile(ident, name, outbound=None, description='', source=''):
    return {'id': ident, 'name': name, 'outbound': copy.deepcopy(outbound or convert_profile(sample())), 'description': description, 'source': source}


class ProfileCatalogTests(unittest.TestCase):
    def test_one_id_merges_names_sources_and_descriptions(self):
        items = [profile('p-1', 'Первое', description='Описание 1', source='этот ПК'),
                 profile('p-1', 'Второе', description='Описание 2', source='ad-pc')]
        items[1]['outbound']['streamSettings']['realitySettings']['shortId'] = 'ffff'
        result = catalog(items)
        self.assertEqual(len(result), 1)
        self.assertEqual([x['name'] for x in result[0]['aliases']], ['Первое', 'Второе'])
        self.assertEqual([x['source'] for x in result[0]['aliases']], ['этот ПК', 'ad-pc'])
        self.assertEqual(result[0]['descriptions'], ['Описание 1', 'Описание 2'])
        self.assertEqual(representative(result, 'p-1'), 'p-1')
        self.assertIsNone(representative(result, 'p-2'))
        self.assertEqual(result[0]['outbound'], items[0]['outbound'])
        self.assertEqual(items[0]['name'], 'Первое')

    def test_different_ids_are_never_merged(self):
        one = profile('one', 'same')
        other = copy.deepcopy(one)
        other['id'] = 'two'
        other['outbound']['settings']['vnext'][0]['users'][0]['id'] = '00000000-0000-4000-8000-000000000002'
        result = catalog([one, other])
        self.assertEqual(len(result), 2)
        self.assertNotEqual(result[0]['name'], result[1]['name'])
        self.assertTrue(all('00000000' not in p['name'] for p in result))

    def test_ip_and_domain_are_not_assumed_equal(self):
        one = profile('one', 'first')
        other = copy.deepcopy(one)
        other['id'] = 'two'
        other['outbound']['settings']['vnext'][0]['address'] = '192.0.2.1'
        self.assertEqual(len(catalog([one, other])), 2)

    def test_transport_and_ipv6_are_displayed_without_secrets(self):
        item = profile('one', 'alias')
        item['outbound']['settings']['vnext'][0]['address'] = '2001:db8::1'
        result = catalog([item])[0]
        self.assertEqual(result['name'], 'REALITY · [2001:db8::1]:443')
        self.assertNotIn('test-public-key', result['name'])


if __name__ == '__main__':
    unittest.main()
