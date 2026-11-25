import uuid


def build_outbound(server, port, user, flow, stream, encoding):
    if not isinstance(server, str) or not server or len(server) > 253 or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Некорректный адрес профиля.')
    try:
        user = str(uuid.UUID(user))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Некорректный UUID профиля.') from None
    if flow not in ('', 'xtls-rprx-vision'):
        raise ValueError('Параметр flow профиля не поддерживается.')
    if encoding not in ('', 'xudp'):
        raise ValueError('Кодирование UDP профиля пока не поддерживается.')
    result = {
        'tag': 'proxy-primary', 'protocol': 'vless',
        'settings': {'vnext': [{'address': server, 'port': port, 'users': [{'id': user, 'encryption': 'none', 'flow': flow}]}]},
        'streamSettings': stream,
    }
    if encoding == 'xudp':
        result['mux'] = {'enabled': True, 'concurrency': -1, 'xudpConcurrency': 8}
    return result


def convert_profile(profile):
    if profile.get('type') != 'vless' or not isinstance(profile.get('outbound'), dict):
        raise ValueError('Поддерживаются только профили VLESS в формате Throne outbound.')
    source = profile['outbound']
    tls = source.get('tls', {})
    reality = tls.get('reality', {})
    utls = tls.get('utls', {})
    transport = source.get('transport', {})
    if transport.get('type') != 'tcp' or not tls.get('enabled') or not reality.get('enabled'):
        raise ValueError('Профиль должен использовать VLESS TCP и REALITY.')
    if (tls.get('insecure') or tls.get('fragment') or tls.get('record_fragment') or tls.get('ech', {}).get('enabled')
            or any(tls.get(k) for k in ('alpn', 'certificate', 'certificate_path', 'client_certificate_path',
                                        'client_key_path', 'min_version', 'max_version', 'disable_sni'))):
        raise ValueError('Параметры TLS профиля пока не поддерживаются.')
    if source.get('multiplex', {}).get('enabled') or any(source.get('dial_fields', {}).values()):
        raise ValueError('Параметры соединения профиля пока не поддерживаются.')
    if not utls.get('enabled'):
        raise ValueError('В профиле не включён uTLS.')
    server_name = tls.get('server_name')
    password = reality.get('public_key')
    short_id = reality.get('short_id', '')
    fingerprint = utls.get('fingerprint') or 'random'
    if not all(isinstance(x, str) for x in (server_name, password, short_id, fingerprint)) or not server_name or not password:
        raise ValueError('Некорректные параметры REALITY.')
    stream = {'network': 'tcp', 'security': 'reality', 'realitySettings': {
        'serverName': server_name, 'fingerprint': fingerprint, 'password': password, 'shortId': short_id,
    }}
    return build_outbound(source.get('server'), source.get('server_port'), source.get('uuid'),
                          source.get('flow', ''), stream, source.get('packet_encoding', ''))
