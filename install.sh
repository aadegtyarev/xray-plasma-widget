#!/bin/sh
# Установка и обновление виджета «Прокси Xray» для системной службы Xray (Plasma 5).
#
#   ./install.sh        — поставить или обновить виджет, помощники и недостающие настройки
#
# Свои настройки скрипт не перезаписывает. Для системной части (помощник в /usr/local/libexec
# и /etc/xray-widget/system.toml) он один раз вызывает sudo; другую команду можно задать
# переменной SUDO, например SUDO="sudo -A".
set -eu
cd "$(dirname "$0")"

LIBEXEC="$HOME/.local/libexec"
BIN="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/xray-widget"
ADMIN=/usr/local/libexec/xray-widget-profile-admin
SYSTEM_DIR=/etc/xray-widget
PLUGIN=ru.adegtyarev.xray
MODULES="widget_config.py profile_sources.py profile_catalog.py subscription_profiles.py vless_profiles.py"
SUDO=${SUDO:-sudo}

fail() { echo "Ошибка: $*" >&2; exit 1; }
for tool in python3 kpackagetool5 curl pkexec systemctl; do
    command -v "$tool" >/dev/null 2>&1 || fail "не найдена программа $tool."
done
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || fail "нужен Python 3.11 или новее."

echo "Пользовательская часть"
install -d -m 700 "$LIBEXEC" "$BIN" "$CONFIG_DIR" "$CONFIG_DIR/profiles"
# shellcheck disable=SC2086
install -m 600 $MODULES "$LIBEXEC/"
install -m 700 xray-widget-system "$LIBEXEC/xray-widget-system"

wrapper=$(mktemp)
trap 'rm -f "$wrapper"' EXIT
printf '#!/bin/sh\nexec "$HOME/.local/libexec/xray-widget-system" "$@"\n' > "$wrapper"
if [ -e "$BIN/xray-widget" ] && ! cmp -s "$wrapper" "$BIN/xray-widget"; then
    backup="$BIN/xray-widget.before-install-$(date +%Y%m%d-%H%M%S)"
    mv "$BIN/xray-widget" "$backup"
    echo "  прежний $BIN/xray-widget сохранён как $backup"
fi
install -m 700 "$wrapper" "$BIN/xray-widget"

if [ ! -e "$CONFIG_DIR/config.toml" ]; then
    (umask 077; printf '%s\n' \
        '# Настройки виджета «Прокси Xray». Образец с пояснениями — config.example.toml в репозитории.' \
        '' '[[group]]' 'name = "Мои"' 'folder = "~/.config/xray-widget/profiles"' > "$CONFIG_DIR/config.toml")
    echo "  создан $CONFIG_DIR/config.toml"
fi

if kpackagetool5 --type Plasma/Applet --show "$PLUGIN" >/dev/null 2>&1; then
    kpackagetool5 --type Plasma/Applet --upgrade package >/dev/null
    echo "  виджет обновлён; чтобы панель подхватила его: systemctl --user restart plasma-plasmashell.service"
else
    kpackagetool5 --type Plasma/Applet --install package >/dev/null
    echo "  виджет установлен; добавьте на панель «Прокси Xray»"
fi

echo "Системная часть"
steps=""
what=""
if ! cmp -s xray-system-profile-admin "$ADMIN" 2>/dev/null; then
    steps="$steps install -o root -g root -m 755 xray-system-profile-admin $ADMIN;"
    what="$what $ADMIN"
fi
if [ ! -e "$SYSTEM_DIR/system.toml" ]; then
    steps="$steps install -d -o root -g root -m 755 $SYSTEM_DIR; install -o root -g root -m 644 system.example.toml $SYSTEM_DIR/system.toml;"
    what="$what $SYSTEM_DIR/system.toml"
    created_system=1
fi
if [ -n "$steps" ]; then
    echo "  нужны права администратора, чтобы записать:$what"
    $SUDO sh -c "set -e;$steps"
    echo "  готово"
else
    echo "  уже актуальна"
fi
if [ "${created_system:-}" = 1 ]; then
    echo "  создан $SYSTEM_DIR/system.toml из образца: проверьте службу, путь к конфигу и Xray, затем запустите проверку ниже"
fi

echo "Проверка"
"$BIN/xray-widget" status | python3 -I -c '
import json, sys
state = json.load(sys.stdin)
if not state.get("ok"):
    sys.exit("  " + state.get("error", "помощник не ответил"))
print("  служба:", "запущена" if state["running"] else "остановлена", "· профилей:", len(state["profiles"]))
if state.get("warning"):
    print("  предупреждение:", state["warning"])
'
