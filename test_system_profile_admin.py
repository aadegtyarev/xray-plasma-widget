import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import vless_profiles
from test_vless_profiles import sample

loader = importlib.machinery.SourceFileLoader('xray_profile_admin', str(Path(__file__).with_name('xray-system-profile-admin')))
spec = importlib.util.spec_from_loader(loader.name, loader)
admin = importlib.util.module_from_spec(spec)
loader.exec_module(admin)
# The tests describe a setup that guards Xray traffic with a route mark, as system.toml can configure.
admin.ROUTE_MARK = 0x58474101


def config():
    return {
        'inbounds': [
            {'protocol': 'socks', 'listen': '127.0.0.1', 'port': 10808},
            {'protocol': 'http', 'listen': '127.0.0.1', 'port': 10809},
        ],
        'outbounds': [{'tag': 'proxy-primary', 'protocol': 'vless', 'settings': {'old': True}, 'streamSettings': {'sockopt': {'mark': 0x58474101, 'domainStrategy': 'UseIPv4'}}}, {'tag': 'direct', 'protocol': 'freedom'}],
        'routing': {'rules': [{'type': 'field', 'inboundTag': ['dns'], 'outboundTag': 'direct'}, {'type': 'field', 'network': 'tcp,udp', 'outboundTag': 'proxy-primary'}]},
        'dns': {'servers': ['127.0.0.1']},
    }


def request():
    return {'action': 'select', 'slot': 'primary', 'id': 'p-000000000001', 'outbound': vless_profiles.convert_profile(sample())}


class AdminValidationTests(unittest.TestCase):
    def test_replaces_only_vless_outbound(self):
        original = config()
        result = json.loads(admin.with_profile(json.dumps(original).encode(), 'primary', request()['outbound']))
        self.assertEqual(result['dns'], original['dns'])
        self.assertEqual(result['routing'], original['routing'])
        self.assertEqual(result['inbounds'], original['inbounds'])
        self.assertEqual(result['outbounds'][1], original['outbounds'][1])
        expected = request()['outbound']
        expected['streamSettings']['sockopt'] = original['outbounds'][0]['streamSettings']['sockopt']
        self.assertEqual(result['outbounds'][0], expected)

    def test_rejects_public_inbound_or_balancer(self):
        for change in ('inbound', 'balancer', 'last_rule', 'missing_outbound'):
            source = config()
            if change == 'inbound': source['inbounds'][0]['listen'] = '0.0.0.0'
            if change == 'balancer': source['routing']['balancers'] = [{'tag': 'other'}]
            if change == 'last_rule': source['routing']['rules'][-1]['outboundTag'] = 'direct'
            if change == 'missing_outbound': source['outbounds'] = []
            with self.subTest(change=change), self.assertRaises(ValueError):
                admin.with_profile(json.dumps(source).encode(), 'primary', request()['outbound'])

    def test_rejects_missing_or_changed_route_mark(self):
        for mark in (None, 0, 42, '1481060609'):
            source = config()
            source['outbounds'][0]['streamSettings']['sockopt']['mark'] = mark
            with self.subTest(mark=mark), self.assertRaisesRegex(ValueError, 'метка'):
                admin.with_profile(json.dumps(source).encode(), 'primary', request()['outbound'])

    def test_without_configured_mark_profiles_share_primary_socket_options(self):
        with mock.patch.object(admin, 'ROUTE_MARK', None):
            plain = config()
            del plain['outbounds'][0]['streamSettings']
            chosen = json.loads(admin.with_profile(json.dumps(plain).encode(), 'primary', request()['outbound']))
            self.assertNotIn('sockopt', chosen['outbounds'][0]['streamSettings'])
            chosen = json.loads(admin.with_profile(json.dumps(config()).encode(), 'primary', request()['outbound']))
            self.assertEqual(chosen['outbounds'][0]['streamSettings']['sockopt']['domainStrategy'], 'UseIPv4')

    def test_rejects_unknown_outbound_routing_options(self):
        source = config()
        source['outbounds'][0]['sendThrough'] = '127.0.0.1'
        with self.assertRaisesRegex(ValueError, 'маршрута'):
            admin.with_profile(json.dumps(source).encode(), 'primary', request()['outbound'])

    def test_rejects_injected_outbound_fields(self):
        outbound = request()['outbound']
        outbound['settings']['unexpected'] = {'file': '/etc/shadow'}
        with self.assertRaises(ValueError):
            admin.validate_outbound(outbound)
        outbound = request()['outbound']
        outbound['streamSettings']['realitySettings']['fingerprint'] = 'chrome;id'
        with self.assertRaises(ValueError):
            admin.validate_outbound(outbound)

    def test_validation_uses_json_extension_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(admin, 'CONFIG', Path(tmp) / 'config.json'), mock.patch.object(admin, 'config_group', return_value=1000), mock.patch.object(admin.os, 'fchown'), mock.patch.object(admin.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
            admin.validate_config(b'{}')
            filename = Path(run.call_args.args[0][-1])
            self.assertEqual(filename.suffix, '.json')
            self.assertFalse(filename.exists())

    def test_validation_error_does_not_expose_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(admin, 'CONFIG', Path(tmp) / 'config.json'), mock.patch.object(admin, 'config_group', return_value=1000), mock.patch.object(admin.os, 'fchown'), mock.patch.object(admin.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='secret-value permission denied', stderr='')):
            with self.assertRaisesRegex(ValueError, 'недостаточно прав') as error:
                admin.validate_config(b'{}')
            self.assertNotIn('secret-value', str(error.exception))

    def test_read_only_preflight_does_not_restart_or_replace_configuration(self):
        original = json.dumps(config()).encode()
        with mock.patch.object(admin, 'ensure_config_dir'), mock.patch.object(admin, 'read_regular', return_value=original), mock.patch.object(admin, 'validate_config') as validate, mock.patch.object(admin, 'atomic_write') as write, mock.patch.object(admin, 'restart_and_check') as restart:
            admin.check({'action': 'check', 'outbound': request()['outbound']})
        validate.assert_called_once()
        write.assert_not_called()
        restart.assert_not_called()

    def test_batch_preflight_checks_all_without_mutating_service(self):
        entries = [{'id': 'p-000000000001', 'outbound': request()['outbound']}, {'id': 'p-000000000004', 'outbound': request()['outbound']}]
        original = json.dumps(config()).encode()
        with mock.patch.object(admin, 'ensure_config_dir'), mock.patch.object(admin, 'read_regular', return_value=original), mock.patch.object(admin, 'validate_config', side_effect=[None, ValueError('Неверная конфигурация.')]), mock.patch.object(admin, 'atomic_write') as write, mock.patch.object(admin, 'restart_and_check') as restart:
            result = admin.check_many({'profiles': entries})
        self.assertEqual(result['checks'], [{'id': 'p-000000000001', 'ok': True}, {'id': 'p-000000000004', 'ok': False, 'error': 'Неверная конфигурация.'}])
        write.assert_not_called()
        restart.assert_not_called()

    def test_batch_preflight_rejects_duplicate_ids(self):
        entries = [{'id': 'p-000000000001', 'outbound': request()['outbound']}] * 2
        with mock.patch.object(admin, 'ensure_config_dir'), mock.patch.object(admin, 'read_regular', return_value=json.dumps(config()).encode()), mock.patch.object(admin, 'validate_config'):
            with self.assertRaises(ValueError):
                admin.check_many({'profiles': entries})

    def test_allows_websocket_and_xhttp_only_with_verified_tls(self):
        for network in ('ws', 'xhttp'):
            outbound = request()['outbound']
            stream = {'network': network, 'security': 'tls', 'tlsSettings': {'serverName': 'example.com', 'fingerprint': 'chrome', 'allowInsecure': False}}
            if network == 'ws':
                stream['wsSettings'] = {'path': '/ws', 'host': 'example.com'}
            else:
                stream['xhttpSettings'] = {'path': '/xhttp', 'host': 'example.com', 'mode': 'packet-up'}
            outbound['streamSettings'] = stream
            with self.subTest(network=network):
                admin.validate_outbound(outbound)
                bad = copy.deepcopy(outbound)
                bad['streamSettings']['tlsSettings']['allowInsecure'] = True
                with self.assertRaises(ValueError):
                    admin.validate_outbound(bad)
                bad = copy.deepcopy(outbound)
                bad['streamSettings']['sockopt'] = {'mark': 1}
                with self.assertRaises(ValueError):
                    admin.validate_outbound(bad)

    def test_rejects_duplicate_proxy_tags(self):
        c = config()
        c['outbounds'].append(copy.deepcopy(c['outbounds'][0]))
        with self.assertRaises(ValueError):
            admin.with_profile(json.dumps(c).encode(), 'primary', request()['outbound'])


def secondary_request():
    outbound = vless_profiles.convert_profile(sample())
    outbound['settings']['vnext'][0]['address'] = 'second.example.com'
    return {'action': 'select', 'slot': 'secondary', 'id': 'p-0123456789ab', 'outbound': outbound}


def wireguard_outbound():
    return {'tag': 'proxy-primary', 'protocol': 'wireguard', 'streamSettings': {}, 'settings': {
        'secretKey': 'A' * 43 + '=', 'address': ['10.66.66.2/32'], 'mtu': 1420, 'noKernelTun': True, 'domainStrategy': 'ForceIPv4',
        'peers': [{'endpoint': 'wg.example.com:3389', 'publicKey': 'B' * 43 + '=', 'preSharedKey': 'C' * 43 + '=', 'keepAlive': 16, 'allowedIPs': ['0.0.0.0/0', '::/0']}]}}


def with_secondary():
    return admin.candidate(json.dumps(config()).encode(), secondary_request())[0]


def enable(data, slot, enabled):
    return admin.candidate(data, {'action': 'enable', 'slot': slot, 'enabled': enabled})


class AdminSecondaryTests(unittest.TestCase):
    def test_adds_second_proxy_on_its_own_ports(self):
        result = json.loads(with_secondary())
        original = config()
        self.assertEqual(result['inbounds'][:2], original['inbounds'])
        self.assertEqual([(x['tag'], x['port']) for x in result['inbounds'][2:]], [('socks-secondary', 10818), ('http-secondary', 10819)])
        self.assertEqual(result['outbounds'][0], original['outbounds'][0])
        second = result['outbounds'][1]
        self.assertEqual(second['tag'], 'proxy-secondary')
        self.assertEqual(second['settings']['vnext'][0]['address'], 'second.example.com')
        self.assertEqual(second['streamSettings']['sockopt'], original['outbounds'][0]['streamSettings']['sockopt'])
        self.assertEqual(result['routing']['rules'][-2], admin.secondary_rule())
        self.assertEqual(result['routing']['rules'][-1], original['routing']['rules'][-1])

    def test_switching_one_proxy_keeps_the_other(self):
        both = with_secondary()
        primary = json.loads(admin.candidate(both, request())[0])
        self.assertEqual(primary['outbounds'][1], json.loads(both)['outbounds'][1])
        moved = secondary_request()
        moved['outbound']['settings']['vnext'][0]['address'] = 'third.example.com'
        secondary = json.loads(admin.candidate(both, moved)[0])
        self.assertEqual(secondary['outbounds'][0], json.loads(both)['outbounds'][0])
        self.assertEqual(secondary['outbounds'][1]['settings']['vnext'][0]['address'], 'third.example.com')
        self.assertEqual(len(secondary['inbounds']), 4)
        self.assertEqual(secondary['routing']['rules'].count(admin.secondary_rule()), 1)

    def test_switch_closes_ports_and_keeps_profile_for_later(self):
        both = with_secondary()
        off, checked = enable(both, 'secondary', False)
        self.assertIsNone(checked)
        self.assertEqual([x['port'] for x in json.loads(off)['inbounds']], [10808, 10809])
        self.assertEqual(json.loads(off)['outbounds'][1], json.loads(both)['outbounds'][1])
        on, checked = enable(off, 'secondary', True)
        self.assertEqual(checked, 'secondary')
        self.assertEqual(json.loads(on), json.loads(both))
        self.assertEqual(enable(off, 'secondary', False)[0], off)

    def test_primary_can_be_switched_off_and_chosen_profile_turns_it_on(self):
        off = json.loads(enable(with_secondary(), 'primary', False)[0])
        self.assertEqual(sorted(x['port'] for x in off['inbounds']), [10818, 10819])
        self.assertEqual(admin.first_enabled(json.dumps(off).encode()), 'secondary')
        back = json.loads(admin.candidate(json.dumps(off).encode(), request())[0])
        self.assertEqual(sorted(x['port'] for x in back['inbounds']), [10808, 10809, 10818, 10819])
        both_off = enable(json.dumps(off).encode(), 'secondary', False)[0]
        self.assertIsNone(admin.first_enabled(both_off))

    def test_second_proxy_needs_a_profile_before_it_can_be_enabled(self):
        with self.assertRaisesRegex(ValueError, 'Сначала выберите'):
            enable(json.dumps(config()).encode(), 'secondary', True)
        with self.assertRaises(ValueError):
            admin.candidate(json.dumps(config()).encode(), {'action': 'enable', 'slot': 'secondary', 'enabled': 1})

    def test_rejects_tampered_second_proxy(self):
        for change in ('rule', 'inbound_tag', 'inbound_missing', 'public', 'mark', 'orphan_ports'):
            source = json.loads(with_secondary())
            if change == 'rule': source['routing']['rules'][-2]['inboundTag'] = ['socks']
            if change == 'inbound_tag': source['inbounds'][3]['tag'] = 'http'
            if change == 'inbound_missing': del source['inbounds'][3]
            if change == 'public': source['inbounds'][2]['listen'] = '0.0.0.0'
            if change == 'mark': source['outbounds'][1]['streamSettings']['sockopt']['mark'] = 1
            if change == 'orphan_ports':
                del source['outbounds'][1]
                del source['routing']['rules'][-2]
            with self.subTest(change=change), self.assertRaises(ValueError):
                admin.candidate(json.dumps(source).encode(), secondary_request())

    def test_original_primary_keeps_second_proxy(self):
        baseline = json.dumps(config()).encode()
        switched = admin.candidate(with_secondary(), request())[0]
        with mock.patch.object(admin, 'read_regular', return_value=baseline):
            restored = json.loads(admin.candidate(switched, {'action': 'select', 'slot': 'primary', 'id': 'original'})[0])
        self.assertEqual(restored['outbounds'][0], config()['outbounds'][0])
        self.assertEqual(restored['outbounds'][1]['tag'], 'proxy-secondary')

    def test_invalid_slots_and_ids_are_rejected(self):
        old = json.dumps(config()).encode()
        for bad in ({'action': 'select', 'slot': 'secondary', 'id': 'original'},
                    {'action': 'select', 'slot': 'third', 'id': 'p-000000000001', 'outbound': request()['outbound']},
                    {'action': 'select', 'slot': ['primary'], 'id': 'p-000000000001', 'outbound': request()['outbound']},
                    {'action': 'select', 'slot': 'secondary', 'id': 'sub-xyz', 'outbound': request()['outbound']},
                    {'action': 'enable', 'slot': 'third', 'enabled': True}):
            with self.subTest(request=bad), self.assertRaises(ValueError):
                admin.candidate(old, bad)

    def test_wireguard_profile_is_accepted_with_route_mark(self):
        result = json.loads(admin.candidate(json.dumps(config()).encode(), dict(request(), outbound=wireguard_outbound()))[0])
        outbound = result['outbounds'][0]
        self.assertEqual(outbound['protocol'], 'wireguard')
        self.assertEqual(outbound['streamSettings'], {'sockopt': config()['outbounds'][0]['streamSettings']['sockopt']})
        admin.check_layout(result)

    def test_wireguard_rejects_unsafe_or_unknown_settings(self):
        changes = {
            'kernel_tun': lambda o: o['settings'].update(noKernelTun=False),
            'short_key': lambda o: o['settings'].update(secretKey='abc'),
            'split_routes': lambda o: o['settings']['peers'][0].update(allowedIPs=['10.0.0.0/8']),
            'two_peers': lambda o: o['settings']['peers'].append(copy.deepcopy(o['settings']['peers'][0])),
            'bad_address': lambda o: o['settings'].update(address=['not-an-ip']),
            'bad_endpoint': lambda o: o['settings']['peers'][0].update(endpoint='wg.example.com'),
            'extra_field': lambda o: o['settings'].update(reserved=[1, 2, 3]),
            'stream': lambda o: o.update(streamSettings={'sockopt': {'mark': 1}}),
            'mtu': lambda o: o['settings'].update(mtu=9000),
        }
        for name, change in changes.items():
            outbound = wireguard_outbound()
            change(outbound)
            with self.subTest(change=name), self.assertRaises(ValueError):
                admin.validate_outbound(outbound)
        without_psk = wireguard_outbound()
        del without_psk['settings']['peers'][0]['preSharedKey']
        admin.validate_outbound(without_psk)

    def test_selections_survive_only_unchanged_configuration(self):
        current = with_secondary()
        digest = admin.hashlib.sha256(current).hexdigest()
        states = [({'slots': {'primary': 'adpc-5', 'secondary': 'p-0123456789ab', 'third': 'x'}, 'config_sha256': digest}, {'primary': 'adpc-5', 'secondary': 'p-0123456789ab'}),
                  ({'selected': 'adpc-5', 'config_sha256': digest}, {'primary': 'adpc-5'}),
                  ({'slots': {'primary': 'adpc-5'}, 'config_sha256': 'other'}, {})]
        for state, expected in states:
            with self.subTest(state=state), mock.patch.object(admin, 'read_regular', return_value=json.dumps(state).encode()):
                self.assertEqual(admin.carried_selections(current), expected)
        with mock.patch.object(admin, 'read_regular', side_effect=FileNotFoundError()):
            self.assertEqual(admin.carried_selections(current), {})

    def test_reachability_check_uses_switched_proxy_port(self):
        for slot, proxy in (('primary', 'http://127.0.0.1:10809'), ('secondary', 'http://127.0.0.1:10819'), (None, None)):
            with self.subTest(slot=slot), mock.patch.object(admin, 'run', return_value=True) as run, mock.patch.object(admin, 'service_pid', return_value=7), mock.patch.object(admin.time, 'sleep'):
                admin.restart_and_check(slot)
            curls = [call.args[0] for call in run.call_args_list if call.args[0][0] == admin.CURL]
            self.assertEqual([c[c.index('--proxy') + 1] for c in curls], [proxy] if proxy else [])

class AdminRollbackTests(unittest.TestCase):
    def setUp(self):
        self.old = json.dumps(config()).encode()
        self.new = admin.candidate(self.old, request())[0]
        for name in ('ensure_config_dir', 'ensure_state_dir', 'validate_config', 'save_baseline'):
            p = mock.patch.object(admin, name)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(admin, 'carried_selections', side_effect=lambda config: {})
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(admin, 'config_group', return_value=1000)
        p.start()
        self.addCleanup(p.stop)

    def test_success_saves_baseline_restarts_and_writes_state(self):
        with mock.patch.object(admin, 'read_regular', side_effect=[self.old, self.old, self.old, self.new]), mock.patch.object(admin, 'atomic_write') as write, mock.patch.object(admin, 'restart_and_check', return_value=123), mock.patch.object(admin, 'write_state') as state:
            admin.apply(request())
        admin.save_baseline.assert_called_once_with(self.old)
        self.assertEqual(write.call_count, 1)
        self.assertEqual(state.call_args.args[:2], ({'primary': 'p-000000000001'}, 123))

    def test_failed_reachability_restores_prior_configuration(self):
        with mock.patch.object(admin, 'read_regular', side_effect=[self.old, self.old, self.old, self.new]), mock.patch.object(admin, 'atomic_write') as write, mock.patch.object(admin, 'restart_and_check', side_effect=[RuntimeError('failed'), 456]), mock.patch.object(admin, 'write_state') as state:
            with self.assertRaisesRegex(RuntimeError, 'failed.*восстановлена'):
                admin.apply(request())
        self.assertEqual(write.call_count, 2)
        self.assertEqual(write.call_args_list[-1].args[1], self.old)
        state.assert_not_called()

    def test_timeout_and_interrupt_both_roll_back(self):
        for error in (subprocess.TimeoutExpired('curl', 20), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), mock.patch.object(admin, 'read_regular', side_effect=[self.old, self.old, self.old, self.new]), mock.patch.object(admin, 'atomic_write') as write, mock.patch.object(admin, 'restart_and_check', side_effect=[error, 456]):
                with self.assertRaisesRegex(RuntimeError, 'восстановлена'):
                    admin.apply(request())
                self.assertEqual(write.call_args_list[-1].args[1], self.old)

    def test_concurrent_config_change_aborts_before_replacement(self):
        with mock.patch.object(admin, 'read_regular', side_effect=[self.old, b'changed']), mock.patch.object(admin, 'atomic_write') as write:
            with self.assertRaisesRegex(RuntimeError, 'изменилась'):
                admin.apply(request())
        write.assert_not_called()

    def test_external_change_is_not_overwritten_during_rollback(self):
        with mock.patch.object(admin, 'read_regular', side_effect=[self.old, self.old, self.old, b'external']), mock.patch.object(admin, 'atomic_write') as write, mock.patch.object(admin, 'restart_and_check', side_effect=RuntimeError('failed')):
            with self.assertRaisesRegex(RuntimeError, 'откат отменён'):
                admin.apply(request())
        self.assertEqual(write.call_count, 1)

    def test_state_write_failure_rolls_back(self):
        with mock.patch.object(admin, 'read_regular', side_effect=[self.old, self.old, self.old, self.new, self.new]), mock.patch.object(admin, 'atomic_write') as write, mock.patch.object(admin, 'restart_and_check', side_effect=[123, 456]), mock.patch.object(admin, 'write_state', side_effect=OSError('error')):
            with self.assertRaisesRegex(RuntimeError, 'восстановлена'):
                admin.apply(request())
        self.assertEqual(write.call_args_list[-1].args[1], self.old)

    def test_both_switch_and_restore_failure_are_reported(self):
        with mock.patch.object(admin, 'read_regular', side_effect=[self.old, self.old, self.old, self.new]), mock.patch.object(admin, 'atomic_write'), mock.patch.object(admin, 'restart_and_check', side_effect=[RuntimeError('new'), RuntimeError('old')]):
            with self.assertRaisesRegex(RuntimeError, 'работа прокси не подтвердилась'):
                admin.apply(request())


    def test_secondary_switch_keeps_primary_choice_and_rolls_back_by_primary_check(self):
        new = admin.candidate(self.old, secondary_request())[0]
        admin.carried_selections.side_effect = lambda config: {'primary': 'adpc-5'}
        with mock.patch.object(admin, 'read_regular', side_effect=[self.old, self.old, self.old, new]), mock.patch.object(admin, 'atomic_write'), mock.patch.object(admin, 'restart_and_check', return_value=9) as restart, mock.patch.object(admin, 'write_state') as state:
            admin.apply(secondary_request())
        restart.assert_called_once_with('secondary')
        self.assertEqual(state.call_args.args[0], {'primary': 'adpc-5', 'secondary': 'p-0123456789ab'})
        with mock.patch.object(admin, 'read_regular', side_effect=[self.old, self.old, self.old, new]), mock.patch.object(admin, 'atomic_write'), mock.patch.object(admin, 'restart_and_check', side_effect=[RuntimeError('failed'), 9]) as restart:
            with self.assertRaisesRegex(RuntimeError, 'восстановлена'):
                admin.apply(secondary_request())
        self.assertEqual(restart.call_args_list, [mock.call('secondary'), mock.call('primary')])


SETTINGS = """
service = "xray-alex-direct.service"
config = "/etc/xray-alex/config.json"
xray = "/usr/bin/env"
route_mark = 0x58474101

[ports]
primary = { socks = 20808, http = 20809 }
secondary = { socks = 20818, http = 20819 }
"""


class AdminSettingsTests(unittest.TestCase):
    def setUp(self):
        for name in ('CONFIG', 'BASELINE', 'XRAY', 'SERVICE', 'ROUTE_MARK'):
            p = mock.patch.object(admin, name, getattr(admin, name))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(admin.SLOTS, {slot: dict(value) for slot, value in admin.SLOTS.items()})
        p.start()
        self.addCleanup(p.stop)

    def load(self, text):
        with mock.patch.object(admin, 'read_regular', return_value=text.encode()):
            admin.load_settings()

    def test_settings_choose_service_paths_ports_and_mark(self):
        self.load(SETTINGS)
        self.assertEqual((admin.SERVICE, admin.CONFIG, admin.BASELINE, admin.XRAY, admin.ROUTE_MARK),
                         ('xray-alex-direct.service', Path('/etc/xray-alex/config.json'), Path('/etc/xray-alex/widget-baseline.json'), '/usr/bin/env', 0x58474101))
        self.assertEqual((admin.SLOTS['primary']['http'], admin.SLOTS['secondary']['socks']), (20809, 20818))
        self.assertEqual(admin.listeners('secondary'), [('socks', '127.0.0.1', 20818), ('http', '127.0.0.1', 20819)])
        self.load(SETTINGS.replace('route_mark = 0x58474101\n', ''))
        self.assertIsNone(admin.ROUTE_MARK)

    def test_shipped_examples_fit_the_helper(self):
        here = Path(__file__).parent
        self.load((here / 'system.example.toml').read_text().replace('/usr/local/bin/xray', '/usr/bin/env'))
        self.assertEqual((admin.SERVICE, admin.ROUTE_MARK, admin.SLOTS['secondary']['http']), ('xray.service', None, 10819))
        example = (here / 'xray-config.example.json').read_bytes()
        self.assertEqual(admin.load_config(example)[1], {'primary': True, 'secondary': None})
        chosen = admin.with_enabled(admin.with_profile(example, 'secondary', secondary_request()['outbound']), 'secondary', True)
        self.assertEqual(admin.load_config(chosen)[1], {'primary': True, 'secondary': True})

    def test_bad_settings_are_refused(self):
        for old, new in (('xray-alex-direct.service', 'x; rm.service'), ('/etc/xray-alex/config.json', 'etc/config.json'),
                         ('/etc/xray-alex/config.json', '/etc/../shadow'), ('/usr/bin/env', '/nonexistent/xray'),
                         ('/usr/bin/env', '/tmp'), ('0x58474101', '0'), ('20818', '20808'), ('20819', '80'),
                         ('http = 20809 }', 'http = 20809, extra = 1 }'), ('route_mark', 'unknown')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.load(SETTINGS.replace(old, new, 1))
        with mock.patch.object(admin, 'read_regular', side_effect=FileNotFoundError()), self.assertRaisesRegex(ValueError, 'system.example.toml'):
            admin.load_settings()


if __name__ == '__main__':
    unittest.main()
