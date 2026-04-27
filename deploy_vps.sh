#!/bin/bash
# Деплой на VPS root@159.194.208.38 (ключ ~/.ssh/id_ed25519_vps)
set -euo pipefail

SERVER="root@159.194.208.38"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Явный SSH_KEY, иначе key/pkey1 в корне проекта, иначе ~/.ssh/id_ed25519_vps
if [ -n "${SSH_KEY:-}" ]; then
  :
elif [ -f "$SCRIPT_DIR/key/pkey1" ]; then
  SSH_KEY="$SCRIPT_DIR/key/pkey1"
else
  SSH_KEY="${HOME}/.ssh/id_ed25519_vps"
fi
REMOTE_DIR="/root/fz_parser"

SSH=(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new)
RSYNC=(rsync -avz -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new")

echo "=== 1. Сборка фронтенда ==="
cd "$(dirname "$0")/temp_frontend"
npm run build

echo "=== 2. Копирование в static ==="
cd ..
rm -rf static/assets static/index.html 2>/dev/null || true
cp -r temp_frontend/dist/* static/

echo "=== 3. Синхронизация на сервер ==="
"${RSYNC[@]}" --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='sql_app.db' --exclude='sql_app.db-wal' --exclude='sql_app.db-shm' \
  --exclude='node_modules' --exclude='temp_frontend' \
  --exclude='fz_parser 2' --exclude='.env' --exclude='.venv' --exclude='key' \
  ./ "$SERVER:$REMOTE_DIR/"

echo "=== 4. Зависимости, systemd, запуск ==="
"${SSH[@]}" "$SERVER" bash -s <<'REMOTE'
set -euo pipefail
cd /root/fz_parser
apt-get update -qq
apt-get install -y -qq python3-pip python3-venv python3-full >/dev/null 2>&1 || true
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

if [ ! -f .env ]; then
  cat > .env << 'ENVEOF'
SMTP_EMAIL=tendrix.io@yandex.ru
SMTP_PASSWORD=
SITE_BASE_URL=https://tendrix.io
ENVEOF
  echo "Создан .env (при необходимости отредактируйте)"
fi

cp -f tendrix.vps.service /etc/systemd/system/tendrix.service
cp -f tendrix-bot.vps.service /etc/systemd/system/tendrix-bot.service
systemctl daemon-reload
systemctl enable tendrix tendrix-bot
systemctl restart tendrix
sleep 2
systemctl restart tendrix-bot
sleep 1
systemctl status tendrix --no-pager || true
echo "---"
systemctl status tendrix-bot --no-pager || true
REMOTE

echo "=== Готово: https://tendrix.io (если DNS указывает на этот IP) или http://159.194.208.38:8080 ==="
