import copy


def endpoint(outbound):
    if outbound['protocol'] == 'wireguard':
        return outbound['settings']['peers'][0]['endpoint']
    node = outbound['settings']['vnext'][0]
    address = node['address']
    host = '[' + address + ']' if ':' in address and not address.startswith('[') else address
    return host + ':' + str(node['port'])


def transport_name(outbound):
    if outbound['protocol'] == 'wireguard':
        return 'WireGuard'
    stream = outbound['streamSettings']
    if stream.get('security') == 'reality':
        return 'REALITY'
    return {'ws': 'WebSocket', 'xhttp': 'XHTTP', 'tcp': 'TCP/TLS'}.get(stream.get('network'), 'VLESS')


def catalog(profiles):
    # Profiles with one id are the same connection (see profile_sources.profile); the first one's settings are used.
    by_settings = {}
    for profile in profiles:
        key = profile['id']
        if key not in by_settings:
            by_settings[key] = {'id': profile['id'], 'outbound': copy.deepcopy(profile['outbound']), 'aliases': [], 'descriptions': []}
        group = by_settings[key]
        alias = {'id': profile['id'], 'name': profile['name'], 'source': profile.get('source', '')}
        group['aliases'].append(alias)
        description = profile.get('description', '')
        if isinstance(description, str) and description and description not in group['descriptions']:
            group['descriptions'].append(description)
    groups = list(by_settings.values())
    labels = {}
    for group in groups:
        label = transport_name(group['outbound']) + ' · ' + endpoint(group['outbound'])
        labels.setdefault(label, []).append(group)
    for label, items in labels.items():
        used = set()
        for group in items:
            candidate = label
            if len(items) > 1:
                candidate += ' — ' + group['aliases'][0]['name']
            unique = candidate
            number = 2
            while unique in used:
                unique = candidate + ' (' + str(number) + ')'
                number += 1
            used.add(unique)
            group['name'] = unique
    return groups


def representative(groups, profile_id):
    for group in groups:
        if any(alias['id'] == profile_id for alias in group['aliases']):
            return group['id']
    return None
