from pathlib import Path
import re
import tomllib

CONFIG = Path.home() / '.config/xray-widget/config.toml'
SOURCES = ('folder', 'subscription', 'links')
MAX_SIZE = 256 * 1024


def text(value, maximum):
    return isinstance(value, str) and value.strip() != '' and len(value) <= maximum


def check_group(item, number, seen):
    where = 'Группа ' + str(number)
    if not isinstance(item, dict):
        raise ValueError(where + ': ожидается таблица [[group]].')
    if not text(item.get('name'), 64):
        raise ValueError(where + ': не задано имя name.')
    name = ' '.join(item['name'].split())
    where = 'Группа «' + name + '»'
    if name in seen:
        raise ValueError(where + ' указана дважды.')
    unknown = set(item) - {'name'} - set(SOURCES)
    if unknown:
        raise ValueError(where + ': неизвестный параметр ' + ', '.join(sorted(unknown)) + '.')
    sources = [key for key in SOURCES if key in item]
    if len(sources) != 1:
        raise ValueError(where + ': нужен ровно один источник — folder, subscription или links.')
    kind, value = sources[0], item[sources[0]]
    if kind == 'folder' and not text(value, 4096):
        raise ValueError(where + ': folder — путь к папке профилей.')
    if kind == 'subscription' and not (text(value, 4096) and value.startswith('https://')):
        raise ValueError(where + ': subscription — ссылка https://.')
    if kind == 'links' and not (isinstance(value, list) and all(text(link, 8192) for link in value)):
        raise ValueError(where + ': links — список ссылок vless://.')
    if kind == 'folder':
        value = str(Path(value).expanduser())
    if kind == 'subscription':
        value = value.strip()
    return {'name': name, 'kind': kind, 'value': value}


def check_labels(labels):
    if not isinstance(labels, dict) or not all(isinstance(key, str) and text(value, 200) for key, value in labels.items()):
        raise ValueError('Раздел [labels]: строки вида "исходное имя" = "подпись".')
    return {key: ' '.join(value.split())[:100] for key, value in labels.items()}


def load(path=CONFIG):
    path = Path(path)
    try:
        if path.stat().st_size > MAX_SIZE:
            raise ValueError('Файл настроек ' + str(path) + ' слишком велик.')
        data = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return [], {}, ['Нет файла настроек ' + str(path) + '; образец — config.example.toml.']
    except tomllib.TOMLDecodeError as error:
        return [], {}, ['Ошибка в ' + str(path) + ': ' + str(error) + '.']
    except (OSError, ValueError, UnicodeDecodeError) as error:
        return [], {}, [str(error) if isinstance(error, ValueError) else 'Не удалось прочитать ' + str(path) + '.']
    groups, errors, seen = [], [], set()
    unknown = set(data) - {'group', 'labels'}
    if unknown:
        errors.append('Неизвестный раздел ' + ', '.join(sorted(unknown)) + ' в ' + str(path) + '.')
    items = data.get('group', [])
    for number, item in enumerate(items if isinstance(items, list) else [items], 1):
        try:
            group = check_group(item, number, seen)
        except ValueError as error:
            errors.append(str(error))
            continue
        seen.add(group['name'])
        groups.append(group)
    try:
        labels = check_labels(data.get('labels', {}))
    except ValueError as error:
        labels = {}
        errors.append(str(error))
    return groups, labels, errors


SYSTEM = Path('/etc/xray-widget/system.toml')
SLOTS = ('primary', 'secondary')
SERVICE = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.@:-]*\.service\Z')


def load_system(path=SYSTEM):
    """Service and tunnel ports from the system settings; the root helper checks the same file more strictly."""
    try:
        data = tomllib.loads(Path(path).read_text())
    except FileNotFoundError:
        raise ValueError('Нет файла ' + str(path) + '; установите виджет скриптом install.sh.') from None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise ValueError('Файл ' + str(path) + ' не прочитан.') from None
    service, ports = data.get('service'), data.get('ports')
    if not isinstance(service, str) or not SERVICE.fullmatch(service):
        raise ValueError('В ' + str(path) + ' неверное имя службы.')
    try:
        ports = {slot: {'http': ports[slot]['http'], 'socks': ports[slot]['socks']} for slot in SLOTS}
    except (KeyError, TypeError):
        raise ValueError('В ' + str(path) + ' не заданы порты туннелей.') from None
    if not all(type(port) is int and 1024 <= port <= 65535 for slot in SLOTS for port in ports[slot].values()):
        raise ValueError('В ' + str(path) + ' неверные порты туннелей.')
    return service, ports
