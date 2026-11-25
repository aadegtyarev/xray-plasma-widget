import copy
import json
from pathlib import Path

from vless_profiles import build_outbound, convert_profile


def normalize_bean(profile):
    if profile.get('type') != 'vless' or not isinstance(profile.get('bean'), dict):
        raise ValueError('Ожидается профиль VLESS из Throne.')
    bean = profile['bean']
    stream = bean.get('stream', {})
    if not isinstance(stream, dict):
        raise ValueError('Некорректные параметры транспорта.')
    if bean.get('enable_brutal') or bean.get('mux') or bean.get('c_cfg') or bean.get('c_out'):
        raise ValueError('Дополнительные параметры профиля пока не поддерживаются.')
    if (stream.get('sec') != 'tls' or stream.get('insecure') or stream.get('cert')
            or stream.get('tls_frag') or stream.get('tls_record_frag') or stream.get('headers')
            or stream.get('ed_len') or stream.get('ed_name') or stream.get('h_type') or stream.get('method')):
        raise ValueError('Параметры транспорта или TLS пока не поддерживаются.')
    return bean, stream


def reality_outbound(bean, stream):
    if stream.get('alpn') or stream.get('host') or stream.get('path'):
        raise ValueError('Дополнительные параметры REALITY пока не поддерживаются.')
    normalized = {'type': 'vless', 'outbound': {
        'name': bean.get('name', ''), 'server': bean.get('addr'), 'server_port': bean.get('port'),
        'uuid': bean.get('pass'), 'flow': bean.get('flow', ''), 'packet_encoding': stream.get('pac_enc', ''),
        'transport': {'type': 'tcp'}, 'multiplex': {'enabled': False}, 'dial_fields': {},
        'tls': {'enabled': True, 'server_name': stream.get('sni'), 'insecure': False,
                'utls': {'enabled': True, 'fingerprint': stream.get('utls') or 'random'},
                'reality': {'enabled': True, 'public_key': stream.get('pbk'), 'short_id': (stream.get('sid') or '').split(',')[0]}},
    }}
    return convert_profile(normalized)


def websocket_outbound(bean, stream):
    server_name = stream.get('sni')
    fingerprint = stream.get('utls')
    path = stream.get('path') or '/'
    host = stream.get('host') or ''
    alpn = stream.get('alpn') or ''
    if not all(isinstance(x, str) for x in (server_name, fingerprint, path, host, alpn)) or not server_name or not fingerprint:
        raise ValueError('Некорректные параметры WebSocket/TLS.')
    if '?ed=' in path:
        raise ValueError('Ранние данные WebSocket пока не поддерживаются.')
    tls = {'serverName': server_name, 'fingerprint': fingerprint, 'allowInsecure': False}
    if alpn:
        tls['alpn'] = [item.strip() for item in alpn.split(',') if item.strip()]
    ws = {'path': path}
    if host:
        ws['host'] = host
    transport = {'network': 'ws', 'security': 'tls', 'tlsSettings': tls, 'wsSettings': ws}
    return build_outbound(bean.get('addr'), bean.get('port'), bean.get('pass'), bean.get('flow', ''), transport, stream.get('pac_enc', ''))


def xhttp_outbound(bean, stream, saved):
    if not isinstance(saved, dict) or saved.get('protocol') != 'vless' or saved.get('tag') != 'proxy-primary':
        raise ValueError('Для XHTTP не найден проверенный исходный конфиг Xray.')
    if set(saved) != {'tag', 'protocol', 'settings', 'streamSettings'}:
        raise ValueError('Дополнительные настройки XHTTP требуют проверки.')
    try:
        if set(saved['settings']) != {'vnext'}:
            raise ValueError('Дополнительные настройки VLESS XHTTP требуют проверки.')
        nodes = saved['settings']['vnext']
        if len(nodes) != 1 or len(nodes[0]['users']) != 1:
            raise ValueError('Ожидается один сервер XHTTP.')
        node, user, transport = nodes[0], nodes[0]['users'][0], saved['streamSettings']
        if set(node) != {'address', 'port', 'users'} or set(user) - {'id', 'encryption', 'flow'}:
            raise ValueError('Дополнительные настройки сервера XHTTP требуют проверки.')
        if (bean.get('addr'), bean.get('port'), bean.get('pass'), stream.get('sni')) != (node.get('address'), node.get('port'), user.get('id'), transport.get('tlsSettings', {}).get('serverName')):
            raise ValueError('Профиль XHTTP не совпадает с исходным конфигом Xray.')
        if transport.get('network') != 'xhttp' or transport.get('security') != 'tls' or transport.get('tlsSettings', {}).get('allowInsecure') is not False:
            raise ValueError('Параметры XHTTP требуют проверки.')
        if user.get('encryption') != 'none' or user.get('flow', '') != bean.get('flow', ''):
            raise ValueError('Параметры VLESS XHTTP не совпадают.')
        return build_outbound(bean.get('addr'), bean.get('port'), bean.get('pass'), bean.get('flow', ''), copy.deepcopy(transport), '')
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError('Повреждён исходный конфиг XHTTP.') from error


def wireguard_outbound(bean):
    if not isinstance(bean, dict):
        raise ValueError('Некорректный профиль WireGuard.')
    if bean.get('enable_amnezia'):
        raise ValueError('AmneziaWG пока не поддерживается Xray.')
    if bean.get('c_cfg') or bean.get('c_out') or bean.get('mux') or bean.get('enable_brutal') or bean.get('use_system_proxy'):
        raise ValueError('Дополнительные параметры WireGuard пока не поддерживаются.')
    server, port, addresses = bean.get('addr'), bean.get('port'), bean.get('local_address')
    if not isinstance(server, str) or not server or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Некорректный адрес узла WireGuard.')
    if not isinstance(addresses, list) or not addresses or not all(isinstance(item, str) and item for item in addresses):
        raise ValueError('В профиле WireGuard нет локального адреса.')
    keys = (bean.get('private_key'), bean.get('public_key'), bean.get('pre_shared_key', ''))
    if not all(isinstance(key, str) for key in keys) or not keys[0] or not keys[1]:
        raise ValueError('Некорректные ключи WireGuard.')
    peer = {'endpoint': ('[' + server + ']' if ':' in server else server) + ':' + str(port), 'publicKey': keys[1],
            'keepAlive': bean.get('persistent_keepalive') or 0, 'allowedIPs': ['0.0.0.0/0', '::/0']}
    if keys[2]:
        peer['preSharedKey'] = keys[2]
    families = {':' in item for item in addresses}
    # Without an address of a family, connections of that family cannot leave the tunnel, so resolve names only to the other one.
    strategy = 'ForceIP' if len(families) == 2 else ('ForceIPv6' if True in families else 'ForceIPv4')
    return {'tag': 'proxy-primary', 'protocol': 'wireguard', 'streamSettings': {}, 'settings': {
        'secretKey': keys[0], 'address': addresses, 'mtu': bean.get('mtu') or 1420, 'noKernelTun': True,
        'domainStrategy': strategy, 'peers': [peer]}}


def display_name(bean, profile_id):
    name = bean.get('name') if isinstance(bean, dict) else None
    return ' '.join(name.split())[:100] or profile_id if isinstance(name, str) else profile_id


def convert_profile_from_adpc(profile, saved_xhttp=None):
    bean, stream = normalize_bean(profile)
    network = stream.get('net')
    if network == 'tcp' and stream.get('pbk'):
        return reality_outbound(bean, stream)
    if network == 'ws' and not stream.get('pbk'):
        return websocket_outbound(bean, stream)
    if network == 'xhttp' and not stream.get('pbk'):
        return xhttp_outbound(bean, stream, saved_xhttp)
    raise ValueError('Транспорт профиля ad-pc пока не поддерживается.')


def read_json_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError('Недопустимый файл профиля.')
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError('Не удалось прочитать профиль.') from error
