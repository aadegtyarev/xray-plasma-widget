import hashlib
import json
from pathlib import Path

import profile_catalog
import subscription_profiles

MAX_FILE = 1024 * 1024

KINDS = {'vless': 'VLESS', 'wireguard': 'WireGuard', 'custom': 'Пользовательский конфиг', 'shadowsocks': 'Shadowsocks',
         'trojan': 'Trojan', 'vmess': 'VMess', 'hysteria2': 'Hysteria2', 'tuic': 'TUIC', 'socks': 'SOCKS', 'http': 'HTTP'}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def profile(name, group, outbound, key=None):
    # A saved profile is known by its settings: the same server in two groups becomes one entry and a rename keeps the choice.
    # A subscription is known by group and name instead: providers reshuffle SNI and shortId on every download,
    # and on shared entry addresses those are exactly what picks the location.
    key = key or json.dumps(outbound, sort_keys=True, separators=(',', ':'))
    return {'id': 'p-' + digest(key), 'name': name, 'source': group, 'outbound': outbound}


def unavailable(name, group, kind, reason):
    return {'id': 'n-' + digest(group + '\0' + name), 'name': name, 'source': group, 'kind': kind, 'reason': reason}


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError('Недопустимый файл профиля.')
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('Файл не читается как JSON.') from error


def folder_outbound(data):
    if not isinstance(data, dict) or data.get('protocol') not in ('vless', 'wireguard'):
        raise ValueError('Ожидается исходящее соединение Xray: VLESS или WireGuard.')
    # The tag inside the file does not matter: the system helper names the outbound after the tunnel it goes to.
    outbound = dict(data, tag='proxy-primary')
    try:
        profile_catalog.endpoint(outbound)
        profile_catalog.transport_name(outbound)
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ValueError('Не хватает адреса сервера или параметров транспорта.') from None
    return outbound


def folder_group(group, directory):
    directory = Path(directory)
    if not directory.is_dir():
        return [], [], ['Группа «' + group + '»: папка ' + str(directory) + ' не найдена.']
    errors = []
    if directory.stat().st_mode & 0o077:
        errors.append('Папка ' + str(directory) + ' доступна другим пользователям; закройте её: chmod 700.')
    found, missing = [], []
    for path in sorted(directory.glob('*.json')):
        name = ' '.join(path.stem.split())[:100] or path.name
        try:
            found.append(profile(name, group, folder_outbound(read_json(path))))
        except ValueError as error:
            missing.append(unavailable(name, group, 'Xray', str(error)))
    return found, missing, errors


def links_group(group, links, by_name=False):
    found, missing, seen = [], [], {}
    for number, text in enumerate(links, 1):
        name = subscription_profiles.link_name(text) or 'Ссылка ' + str(number)
        seen[name] = seen.get(name, 0) + 1
        key = '\0'.join([group, name, str(seen[name])]) if by_name else None
        try:
            found.append(profile(name, group, subscription_profiles.convert_link(text), key))
        except ValueError as error:
            scheme = text.split('://', 1)[0] if '://' in text else 'ссылка'
            missing.append(unavailable(name, group, KINDS.get(scheme, scheme), str(error)))
    return found, missing


def collect(groups, subscriptions, refresh=None):
    found, missing, errors = [], [], []
    for group in groups:
        if group['kind'] == 'folder':
            items, absent, problems = folder_group(group['name'], group['value'])
        else:
            subscribed = group['kind'] == 'subscription'
            links, problems = subscriptions.links(group['name'], group['value'], refresh) if subscribed else (group['value'], [])
            items, absent = links_group(group['name'], links, by_name=subscribed)
        found.extend(items)
        missing.extend(absent)
        errors.extend(problems)
    return found, missing, errors
