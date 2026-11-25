import base64
import binascii
import hashlib
import http.client
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import parse_qs, unquote, urlsplit
import urllib.request

from vless_profiles import build_outbound

MAX_SIZE = 1024 * 1024
REFRESH_AFTER = 12 * 3600
RETRY_AFTER = 3600
# Providers return the plain link list only to clients they recognise; a browser-like agent gets an HTML page.
USER_AGENT = 'v2rayN/7.10'


def query(link):
    values = parse_qs(link.query, keep_blank_values=True)
    if any(len(items) != 1 for items in values.values()):
        raise ValueError('Повторяющиеся параметры ссылки.')
    return {key: items[0] for key, items in values.items()}


def reality_stream(params):
    if not params.get('sni') or not params.get('pbk'):
        raise ValueError('Неполные параметры REALITY.')
    return {'network': 'tcp', 'security': 'reality', 'realitySettings': {
        'serverName': params['sni'], 'fingerprint': params.get('fp') or 'chrome',
        'password': params['pbk'], 'shortId': params.get('sid', ''),
    }}


def websocket_stream(params, address):
    path = params.get('path') or '/'
    if '?ed=' in path:
        raise ValueError('Ранние данные WebSocket пока не поддерживаются.')
    tls = {'serverName': params.get('sni') or params.get('host') or address, 'fingerprint': params.get('fp') or 'chrome', 'allowInsecure': False}
    alpn = [item.strip() for item in params.get('alpn', '').split(',') if item.strip()]
    if alpn:
        tls['alpn'] = alpn
    ws = {'path': path}
    if params.get('host'):
        ws['host'] = params['host']
    return {'network': 'ws', 'security': 'tls', 'tlsSettings': tls, 'wsSettings': ws}


def convert_link(text):
    link = urlsplit(text)
    if link.scheme != 'vless':
        raise ValueError('Поддерживаются только ссылки VLESS.')
    params = query(link)
    if params.get('encryption', 'none') != 'none' or params.get('headerType', 'none') != 'none':
        raise ValueError('Параметры VLESS пока не поддерживаются.')
    if params.get('allowInsecure', '0') not in ('0', 'false'):
        raise ValueError('Ссылка отключает проверку TLS.')
    network, security = params.get('type', 'tcp'), params.get('security', 'none')
    if network == 'tcp' and security == 'reality':
        stream = reality_stream(params)
    elif network == 'ws' and security == 'tls':
        stream = websocket_stream(params, link.hostname)
    else:
        raise ValueError('Транспорт ссылки пока не поддерживается.')
    return build_outbound(link.hostname, link.port or 443, unquote(link.username or ''), params.get('flow', ''), stream, '')


def link_name(text):
    return ' '.join(unquote(urlsplit(text).fragment).split())[:100]


def decode(data):
    text = data.decode('utf-8', 'replace').strip()
    if '://' not in text:
        compact = ''.join(text.split())
        try:
            text = base64.b64decode(compact + '=' * (-len(compact) % 4), altchars=b'-_' if '-' in compact or '_' in compact else None).decode()
        except (binascii.Error, UnicodeDecodeError, ValueError):
            raise ValueError('Не удалось разобрать ответ подписки.') from None
    links = [line for line in text.split() if '://' in line]
    if not links:
        raise ValueError('Подписка не содержит ссылок.')
    return links


def fetch(url):
    if urlsplit(url).scheme != 'https':
        raise ValueError('Ссылка подписки должна начинаться с https://.')
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise ValueError('Ответ подписки слишком велик.')
    return decode(data)


def private_write(path, text):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.subscription-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def age(path):
    try:
        return time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return None


class Subscriptions:
    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)

    def cache(self, url):
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:16] + '.txt')

    def attempt(self, url):
        return self.cache_dir / ('.' + self.cache(url).stem + '.attempt')

    def refresh(self, url):
        private_write(self.attempt(url), '')
        private_write(self.cache(url), '\n'.join(fetch(url)) + '\n')

    def stale(self, url):
        cached, tried = age(self.cache(url)), age(self.attempt(url))
        return (cached is None or cached > REFRESH_AFTER) and (tried is None or tried > RETRY_AFTER)

    def links(self, name, url, refresh):
        errors = []
        if refresh == 'force' or (refresh == 'stale' and self.stale(url)):
            try:
                self.refresh(url)
            except (OSError, ValueError, http.client.HTTPException):
                errors.append('Подписку ' + name + ' не удалось обновить.')
        try:
            return self.cache(url).read_text().split(), errors
        except FileNotFoundError:
            return [], errors
