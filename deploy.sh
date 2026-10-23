#!/usr/bin/env bash
# Деплой / обновление NYVA_bot на сервере (Ubuntu/Debian), запуск через nohup.
# Первый запуск:  bash deploy.sh        Обновление: тот же самый скрипт.
set -euo pipefail

REPO="https://github.com/IvanAkperov/NYVA_bot.git"
APP_DIR="/opt/NYVA_bot"
DATA_DIR="/opt/nyva_data"            # база и .env живут тут, вне git
TZ_NAME="Europe/Moscow"              # расписание бота идёт по времени сервера

echo "==> Системные пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git sqlite3 python3 python3-venv python3-pip fonts-dejavu-core ca-certificates tzdata

echo "==> Часовой пояс $TZ_NAME"
timedatectl set-timezone "$TZ_NAME" 2>/dev/null || ln -sf "/usr/share/zoneinfo/$TZ_NAME" /etc/localtime

echo "==> Python 3.10+"
PY=python3
if ! $PY -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)'; then
    if grep -qi ubuntu /etc/os-release; then
        apt-get install -y software-properties-common
        add-apt-repository -y ppa:deadsnakes/ppa
        apt-get update -y
        apt-get install -y python3.11 python3.11-venv
        PY=python3.11
    else
        echo "!! Нужен Python 3.10+, а тут $($PY --version). Обнови ОС или поставь python3.11 вручную." >&2
        exit 1
    fi
fi
echo "    $($PY --version)"

echo "==> Код"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" fetch --all
    git -C "$APP_DIR" reset --hard origin/HEAD
else
    git clone "$REPO" "$APP_DIR"
fi

echo "==> Виртуальное окружение и библиотеки"
[ -d "$APP_DIR/venv" ] || $PY -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

echo "==> База и секреты"
mkdir -p "$DATA_DIR"
if [ ! -f "$DATA_DIR/nyvaBot.db" ]; then
    if [ -f "$APP_DIR/nyvaBot.db" ]; then cp "$APP_DIR/nyvaBot.db" "$DATA_DIR/nyvaBot.db"; fi
fi
if [ ! -f "$DATA_DIR/.env" ]; then
    read -rp  "BOT_TOKEN: " BOT_TOKEN
    read -rp  "MISTRAL_API_KEY: " MISTRAL_API_KEY
    read -rp  "GROUP_CHAT_ID [-4909725043]: " GROUP_CHAT_ID; GROUP_CHAT_ID=${GROUP_CHAT_ID:--4909725043}
    read -rp  "ADMIN_ID [1197646514]: " ADMIN_ID; ADMIN_ID=${ADMIN_ID:-1197646514}
    cat > "$DATA_DIR/.env" <<ENV
BOT_TOKEN=$BOT_TOKEN
MISTRAL_API_KEY=$MISTRAL_API_KEY
GROUP_CHAT_ID=$GROUP_CHAT_ID
ADMIN_ID=$ADMIN_ID
DB_PATH=$DATA_DIR/nyvaBot.db
ENV
    chmod 600 "$DATA_DIR/.env"
fi
ln -sf "$DATA_DIR/.env" "$APP_DIR/.env"

echo "==> Таблицы (создаются/мигрируются автоматически)"
cd "$APP_DIR"
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -c "import db; db.init_db(); print('    таблиц:', db.conn.execute(\"select count(*) from sqlite_master where type='table'\").fetchone()[0])"

echo "==> Перезапуск через nohup"
pkill -f "$APP_DIR/venv/bin/python bot.py" 2>/dev/null && sleep 2 || true
PYTHONDONTWRITEBYTECODE=1 nohup "$APP_DIR/venv/bin/python" bot.py >> "$APP_DIR/bot.log" 2>&1 &
echo "    PID $!"

echo "==> Автозапуск после перезагрузки сервера (cron @reboot)"
CRON_LINE="@reboot cd $APP_DIR && PYTHONDONTWRITEBYTECODE=1 nohup $APP_DIR/venv/bin/python bot.py >> $APP_DIR/bot.log 2>&1 &"
( crontab -l 2>/dev/null | grep -v "NYVA_bot/venv/bin/python bot.py" ; echo "$CRON_LINE" ) | crontab -

sleep 6
echo "==> Последние строки лога:"
tail -n 15 "$APP_DIR/bot.log"
echo
echo "Готово. Лог: tail -f $APP_DIR/bot.log   Стоп: pkill -f '$APP_DIR/venv/bin/python bot.py'"
